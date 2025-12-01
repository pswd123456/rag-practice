import os
import logging
from typing import Any, List
from arq.connections import RedisSettings
from sqlmodel import select

from app.core.config import settings
from app.db.session import async_session_maker, engine
from app.core.logging_setup import setup_logging

# Services
# [Modified] 引入新的 pipeline
from app.services.ingest.ingest import process_document_pipeline
from app.services.knowledge.knowledge_crud import delete_knowledge_pipeline 
from app.services.evaluation.evaluation_service import generate_testset_pipeline, run_experiment_pipeline

# Models for State Checking
from app.domain.models import Document, DocStatus, Testset, Experiment, Knowledge, KnowledgeStatus

# --- 1. 初始化 Worker 日志 ---
setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
logger = logging.getLogger("app.worker")

async def check_and_fix_zombie_tasks():
    """
    [Self-Healing] 检查并修复因 Worker 崩溃或重启而残留的 '僵尸任务'。
    将所有处于中间状态的任务标记为 FAILED。
    """
    logger.info("🚑 正在检查僵尸任务 (Zombie Tasks)...")
    
    async with async_session_maker() as db:
        try:
            # 1. 修复 Documents (PROCESSING -> FAILED)
            stmt_doc = select(Document).where(Document.status == DocStatus.PROCESSING)
            docs = (await db.exec(stmt_doc)).all()
            if docs:
                logger.warning(f"发现 {len(docs)} 个卡在 PROCESSING 状态的文档，正在重置...")
                for doc in docs:
                    doc.status = DocStatus.FAILED
                    doc.error_message = "任务异常中断: 服务可能发生了重启或崩溃。"
                    db.add(doc)
            
            # 2. 修复 Testsets (GENERATING -> FAILED)
            stmt_ts = select(Testset).where(Testset.status == "GENERATING")
            testsets = (await db.exec(stmt_ts)).all()
            if testsets:
                logger.warning(f"发现 {len(testsets)} 个卡在 GENERATING 状态的测试集，正在重置...")
                for ts in testsets:
                    ts.status = "FAILED"
                    ts.error_message = "任务异常中断: 服务可能发生了重启或崩溃。"
                    db.add(ts)

            # 3. 修复 Experiments (RUNNING -> FAILED)
            stmt_exp = select(Experiment).where(Experiment.status == "RUNNING")
            exps = (await db.exec(stmt_exp)).all()
            if exps:
                logger.warning(f"发现 {len(exps)} 个卡在 RUNNING 状态的实验，正在重置...")
                for exp in exps:
                    exp.status = "FAILED"
                    exp.error_message = "任务异常中断: 服务可能发生了重启或崩溃。"
                    db.add(exp)
            
            # 4. 修复 Knowledge Deletions (DELETING -> FAILED)
            stmt_kb = select(Knowledge).where(Knowledge.status == KnowledgeStatus.DELETING)
            kbs = (await db.exec(stmt_kb)).all()
            if kbs:
                logger.warning(f"发现 {len(kbs)} 个卡在 DELETING 状态的知识库，正在标记为 FAILED...")
                for kb in kbs:
                    kb.status = KnowledgeStatus.FAILED
                    # Knowledge 模型没有 error_message 字段，只能通过状态传达
                    db.add(kb)

            await db.commit()
            if docs or testsets or exps or kbs:
                logger.info("✅ 僵尸任务修复完成。")
            else:
                logger.info("✨ 未发现僵尸任务，系统状态健康。")
                
        except Exception as e:
            logger.error(f"执行僵尸任务修复时发生错误: {e}", exc_info=True)
            await db.rollback()

async def startup(ctx: Any):
    logger.info("👷 Worker 进程启动...")
    # 执行自愈逻辑
    await check_and_fix_zombie_tasks()

async def shutdown(ctx: Any):
    logger.info("👷 Worker 进程关闭...")
    await engine.dispose()

# --- Worker 任务定义 (纯异步，无 Wrapper) ---

async def process_document_task(ctx: Any, doc_id: int):
    logger.info(f"[Task] 开始处理文档: ID {doc_id}")
    # [Optimization] 移除外部的 Session Context
    # 数据库连接现在由 pipeline 内部按需获取，防止 Docling 等长任务占用连接池
    try:
        await process_document_pipeline(doc_id)
    except Exception as e:
        logger.error(f"[Task] 文档处理异常 (ID {doc_id}): {e}", exc_info=True)

# 增加超时时间
process_document_task.max_tries = 3 # type: ignore
process_document_task.retry_delay = 5 # type: ignore
process_document_task.timeout = 600 # type: ignore

async def delete_knowledge_task(ctx: Any, knowledge_id: int):
    logger.info(f"[Task] 开始删除知识库: ID {knowledge_id}")
    async with async_session_maker() as db:
        try:
            await delete_knowledge_pipeline(db, knowledge_id)
        except Exception as e:
            logger.error(f"[Task] 知识库删除异常 (ID {knowledge_id}): {e}", exc_info=True)

delete_knowledge_task.max_tries = 3 # type: ignore
delete_knowledge_task.retry_delay = 2 # type: ignore

async def generate_testset_task(ctx: Any, testset_id: int, source_doc_ids: List[int], generator_model: str = "qwen-max"):
    logger.info(f"[Task] 开始生成测试集: ID {testset_id}")
    async with async_session_maker() as db:
        try:
            await generate_testset_pipeline(db, testset_id, source_doc_ids, generator_model)
        except Exception as e:
            logger.error(f"[Task] 测试集生成异常 (ID {testset_id}): {e}", exc_info=True)

generate_testset_task.max_tries = 3 # type: ignore
generate_testset_task.retry_delay = 10 # type: ignore

async def run_experiment_task(ctx: Any, experiment_id: int):
    logger.info(f"[Task] 开始运行实验: ID {experiment_id}")
    async with async_session_maker() as db:
        try:
            await run_experiment_pipeline(db, experiment_id)
        except Exception as e:
            logger.error(f"[Task] 实验运行异常 (ID {experiment_id}): {e}", exc_info=True)

run_experiment_task.max_tries = 3 # type: ignore
run_experiment_task.retry_delay = 10 # type: ignore

# --- Arq 配置 ---

class WorkerSettings:
    functions = [
        process_document_task, 
        delete_knowledge_task, 
        generate_testset_task, 
        run_experiment_task
    ]
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT
        )
    
    queue_name = os.getenv("ARQ_QUEUES", settings.DEFAULT_QUEUE_NAME)
    max_jobs = 1
    on_startup = startup
    on_shutdown = shutdown