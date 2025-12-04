# app/worker.py

import os
import logging
from typing import Any, List
from datetime import datetime, timedelta, timezone # 🟢 新增
from arq import cron # 🟢 新增
from arq.connections import RedisSettings
from sqlmodel import select, func, col

from app.core.config import settings
from app.db.session import async_session_maker, engine
from app.core.logging_setup import setup_logging

# Services
from app.services.ingest.ingest import process_document_pipeline
from app.services.knowledge.knowledge_crud import delete_knowledge_pipeline 
from app.services.evaluation.evaluation_service import generate_testset_pipeline, run_experiment_pipeline

# Models for State Checking
from app.domain.models import Document, DocStatus, Testset, Experiment, Knowledge, KnowledgeStatus

# --- 1. 初始化 Worker 日志 ---
setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
logger = logging.getLogger("app.worker")

# ... [保留原有的 check_and_fix_zombie_tasks 函数不变] ...
async def check_and_fix_zombie_tasks():
    # (此处代码保持原样，它是启动时的全量清理)
    """
    [Self-Healing] 检查并修复因 Worker 崩溃或重启而残留的 '僵尸任务'。
    策略升级：清理所有处于 非终态 (COMPLETED/FAILED) 且 非等待态 (PENDING) 的任务。
    这意味着 PROCESSING, GENERATING, DELETING 以及任何自定义的中间状态 (如 DOCLING_PROCESSING) 都会被重置。
    """
    logger.info("🚑 正在检查僵尸任务 (Zombie Tasks)...")
    
    docs_to_fix = []
    testsets_to_fix = []
    exps_to_fix = []
    kbs_to_fix = []

    async with async_session_maker() as db:
        try:
            # --- 诊断：打印当前文档状态分布 ---
            # 这有助于排查为什么某些文档没被检测到
            try:
                stats_stmt = select(Document.status, func.count(Document.id)).group_by(Document.status)
                stats = (await db.exec(stats_stmt)).all()
                if stats:
                    stats_dict = {str(s): c for s, c in stats}
                    logger.info(f"📊 [DB诊断] 当前文档状态分布: {stats_dict}")
            except Exception as diag_err:
                logger.warning(f"无法获取状态统计信息: {diag_err}")

            # --- 1. 修复 Documents ---
            # 逻辑：Status NOT IN [COMPLETED, FAILED, PENDING] -> 视为僵尸任务
            # 这样可以捕获 PROCESSING 以及用户可能的自定义状态 (如 DOCLING_PROCESSING)
            safe_statuses = [DocStatus.COMPLETED, DocStatus.FAILED, DocStatus.PENDING]
            # 注意：某些数据库可能需要将 Enum 转换为字符串进行比较，这里使用 col() 辅助
            stmt_doc = select(Document).where(col(Document.status).notin_(safe_statuses))
            
            docs_to_fix = (await db.exec(stmt_doc)).all()
            if docs_to_fix:
                logger.warning(f"⚠️ 发现 {len(docs_to_fix)} 个处于中间状态的文档 (非 PENDING/COMPLETED/FAILED)，正在重置...")
                for doc in docs_to_fix:
                    original_status = doc.status
                    doc.status = DocStatus.FAILED
                    doc.error_message = f"任务异常中断 (原状态: {original_status}): 服务可能发生了重启或崩溃。"
                    db.add(doc)
            
            # --- 2. 修复 Testsets ---
            # Testset 只有 COMPLETED 和 FAILED 是终态 (PENDING 是等待态? 假设 GENERATING 是中间态)
            # 原逻辑只查了 GENERATING，这里保持宽容，只重置明确的 GENERATING
            stmt_ts = select(Testset).where(Testset.status == "GENERATING")
            testsets_to_fix = (await db.exec(stmt_ts)).all()
            if testsets_to_fix:
                logger.warning(f"⚠️ 发现 {len(testsets_to_fix)} 个卡在 GENERATING 状态的测试集，正在重置...")
                for ts in testsets_to_fix:
                    ts.status = "FAILED"
                    ts.error_message = "任务异常中断: 服务可能发生了重启或崩溃。"
                    db.add(ts)

            # --- 3. 修复 Experiments ---
            stmt_exp = select(Experiment).where(Experiment.status == "RUNNING")
            exps_to_fix = (await db.exec(stmt_exp)).all()
            if exps_to_fix:
                logger.warning(f"⚠️ 发现 {len(exps_to_fix)} 个卡在 RUNNING 状态的实验，正在重置...")
                for exp in exps_to_fix:
                    exp.status = "FAILED"
                    exp.error_message = "任务异常中断: 服务可能发生了重启或崩溃。"
                    db.add(exp)
            
            # --- 4. 修复 Knowledge Deletions ---
            stmt_kb = select(Knowledge).where(Knowledge.status == KnowledgeStatus.DELETING)
            kbs_to_fix = (await db.exec(stmt_kb)).all()
            if kbs_to_fix:
                logger.warning(f"⚠️ 发现 {len(kbs_to_fix)} 个卡在 DELETING 状态的知识库，正在标记为 FAILED...")
                for kb in kbs_to_fix:
                    kb.status = KnowledgeStatus.FAILED
                    db.add(kb)

            # 提交更改
            if docs_to_fix or testsets_to_fix or exps_to_fix or kbs_to_fix:
                await db.commit()
                total_fixed = len(docs_to_fix) + len(testsets_to_fix) + len(exps_to_fix) + len(kbs_to_fix)
                logger.info(f"✅ 僵尸任务修复完成，共修复 {total_fixed} 项。")
            else:
                logger.info("✨ 未发现僵尸任务，系统状态健康。")
                
        except Exception as e:
            logger.error(f"❌ 执行僵尸任务修复时发生错误: {e}", exc_info=True)
            await db.rollback()

# -----------------------------------------------------------
# [New] 主动清理机制 (Cron Job)
# -----------------------------------------------------------
async def fix_stale_tasks(ctx: Any):
    """
    [Watchdog] 定时巡检任务。
    清理执行时间过长（超过阈值）的任务，防止任务在运行时卡死。
    """
    # 阈值设定：1 小时。即使是大文件 Docling 解析，也不应该超过 1 小时。
    TIMEOUT_HOURS = 1
    # 注意：使用 utcnow 还是 now 取决于数据库时区设置，这里假设 naive datetime 或 local time
    # 为了保险，通常建议数据库统一存 UTC，这里使用 datetime.now() 适配大多数默认配置
    threshold_time = datetime.now() - timedelta(hours=TIMEOUT_HOURS)
    
    async with async_session_maker() as db:
        try:
            # 1. 扫描超时文档 (状态为 PROCESSING 且 更新时间早于 1 小时前)
            stmt_doc = select(Document).where(
                col(Document.status).notin_([DocStatus.COMPLETED, DocStatus.FAILED, DocStatus.PENDING]),
                Document.updated_at < threshold_time
            )
            stale_docs = (await db.exec(stmt_doc)).all()
            
            for doc in stale_docs:
                logger.warning(f"⏰ 发现超时任务: 文档 {doc.id} (Status: {doc.status}) 已卡住超过 {TIMEOUT_HOURS} 小时，强制置为失败。")
                doc.status = DocStatus.FAILED
                doc.error_message = f"任务超时 (Watchdog): 执行时间超过 {TIMEOUT_HOURS} 小时。"
                db.add(doc)

            # 2. 扫描超时测试集 (Testset 没有 updated_at，使用 created_at 近似)
            stmt_ts = select(Testset).where(
                Testset.status == "GENERATING",
                Testset.created_at < threshold_time
            )
            stale_ts = (await db.exec(stmt_ts)).all()
            for ts in stale_ts:
                logger.warning(f"⏰ 发现超时任务: 测试集 {ts.id} 生成耗时过长，强制置为失败。")
                ts.status = "FAILED"
                ts.error_message = "任务超时 (Watchdog)"
                db.add(ts)

            # 3. 扫描超时实验
            stmt_exp = select(Experiment).where(
                Experiment.status == "RUNNING",
                Experiment.created_at < threshold_time
            )
            stale_exps = (await db.exec(stmt_exp)).all()
            for exp in stale_exps:
                logger.warning(f"⏰ 发现超时任务: 实验 {exp.id} 运行耗时过长，强制置为失败。")
                exp.status = "FAILED"
                exp.error_message = "任务超时 (Watchdog)"
                db.add(exp)

            if stale_docs or stale_ts or stale_exps:
                await db.commit()
                logger.info("✅ Watchdog 清理完成。")
                
        except Exception as e:
            logger.error(f"Watchdog 巡检异常: {e}", exc_info=True)
            await db.rollback()

async def startup(ctx: Any):
    logger.info("👷 Worker 进程启动...")
    # 启动时执行一次全量清理 (基于状态)
    await check_and_fix_zombie_tasks()

async def shutdown(ctx: Any):
    logger.info("👷 Worker 进程关闭...")
    await engine.dispose()

# ... [Worker 任务定义保持不变] ...
async def process_document_task(ctx: Any, doc_id: int):
    logger.info(f"[Task] 开始处理文档: ID {doc_id}")
    try:
        await process_document_pipeline(doc_id)
    except Exception as e:
        logger.error(f"[Task] 文档处理异常 (ID {doc_id}): {e}", exc_info=True)

# 增加超时时间
process_document_task.max_tries = 3 # type: ignore
process_document_task.retry_delay = 5 # type: ignore
process_document_task.timeout = 600 # type: ignore

async def delete_knowledge_task(ctx: Any, knowledge_id: int, user_id: int):
    logger.info(f"[Task] 开始删除知识库: ID {knowledge_id} (User: {user_id})")
    async with async_session_maker() as db:
        try:
            # 透传 user_id 给 pipeline
            await delete_knowledge_pipeline(db, knowledge_id, user_id)
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

run_experiment_task.max_tries = 0 # type: ignore
run_experiment_task.retry_delay = 10 # type: ignore
run_experiment_task.timeout = 6000

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
    
    # 🟢 [New] 注册定时任务
    # 每 10 分钟运行一次 fix_stale_tasks
    cron_jobs = [
        cron(fix_stale_tasks, minute={0, 10, 20, 30, 40, 50})
    ]
    
    queue_name = os.getenv("ARQ_QUEUES", settings.DEFAULT_QUEUE_NAME)
    max_jobs = 1
    on_startup = startup
    on_shutdown = shutdown