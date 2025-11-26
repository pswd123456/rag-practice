import os
import asyncio
import logging
from typing import Any, List
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.db.session import async_session_maker # 🟢 引入异步工厂
from app.core.logging_setup import setup_logging

from app.services.ingest.processor import process_document_pipeline
from app.services.knowledge_crud import delete_knowledge_pipeline 
from app.services.evaluation.evaluation_service import generate_testset_pipeline, run_experiment_pipeline

# --- 1. 初始化 Worker 日志 ---
setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
logger = logging.getLogger("app.worker")

async def startup(ctx: Any):
    logger.info("👷 Worker 进程启动...")

async def shutdown(ctx: Any):
    logger.info("👷 Worker 进程关闭...")

# --- Worker 任务定义 (纯异步，无 Wrapper) ---

async def process_document_task(ctx: Any, doc_id: int):
    logger.info(f"[Task] 开始处理文档: ID {doc_id}")
    async with async_session_maker() as db:
        try:
            await process_document_pipeline(db, doc_id)
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

    on_startup = startup
    on_shutdown = shutdown