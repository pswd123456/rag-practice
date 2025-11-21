# app/worker.py
import asyncio
from typing import Any, List
import logging
import logging.config
from datetime import datetime

from arq import create_pool
from arq.connections import RedisSettings
from sqlmodel import Session

from app.core.config import settings
from app.db.session import engine
from app.core.logging_setup import get_logging_config

from app.services.ingest.processor import process_document_pipeline
from app.services.knowledge_crud import delete_knowledge_pipeline 
from app.services.evaluation_service import generate_testset_pipeline, run_experiment_pipeline

logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))
logging.config.dictConfig(logging_config_dict)
logger = logging.getLogger(__name__)

async def startup(ctx: Any):
    logger.info("worker startup")

async def shutdown(ctx: Any):
    logger.info("worker shutdown")

def _sync_process_wrapper(doc_id: int):
    """Worker 的同步包装器：处理文档上传"""
    logger.info(f"[Worker] 开始处理文档任务: ID {doc_id}")
    with Session(engine) as db:
        try:
            process_document_pipeline(db, doc_id)
        except Exception as e:
            logger.error(f"[Worker] 文档处理任务异常: {e}", exc_info=True)

def _sync_delete_knowledge_wrapper(knowledge_id: int):
    """Worker 的同步包装器：处理知识库删除"""
    logger.info(f"[Worker] 开始删除知识库: ID {knowledge_id}")
    with Session(engine) as db:
        try:
            delete_knowledge_pipeline(db, knowledge_id)
        except Exception as e:
            logger.error(f"[Worker] 知识库删除任务异常: {e}", exc_info=True)
def _sync_generate_testset_wrapper(testset_id: int, source_doc_ids: List[int]):
    logger.info(f"[Worker] 开始生成测试集: {testset_id}")
    with Session(engine) as db:
        try:
            generate_testset_pipeline(db, testset_id, source_doc_ids)
        except Exception as e:
            logger.error(f"[Worker] 生成测试集异常: {e}", exc_info=True)

def _sync_run_experiment_wrapper(experiment_id: int):
    logger.info(f"[Worker] 开始执行实验: {experiment_id}")
    with Session(engine) as db:
        try:
            run_experiment_pipeline(db, experiment_id)
        except Exception as e:
            logger.error(f"[Worker] 实验执行异常: {e}", exc_info=True)

# ----- Worker -----

async def process_document_task(ctx: Any, doc_id: int):
    await asyncio.to_thread(_sync_process_wrapper, doc_id)

# 配置重试：处理文档可能因为网络波动（MinIO/API）失败
# 5秒重试间隔，最多3次
process_document_task.max_tries = 3 # type: ignore
process_document_task.retry_delay = 5 # type: ignore

async def delete_knowledge_task(ctx: Any, knowledge_id: int):
    await asyncio.to_thread(_sync_delete_knowledge_wrapper, knowledge_id)

# 配置重试：删除操作通常较快，给予少量重试机会
delete_knowledge_task.max_tries = 3 # type: ignore
delete_knowledge_task.retry_delay = 2 # type: ignore

async def generate_testset_task(ctx: Any, testset_id: int, source_doc_ids: List[int]):
    await asyncio.to_thread(_sync_generate_testset_wrapper, testset_id, source_doc_ids)

# 配置重试：涉及 LLM 生成，可能触发限流 (Rate Limit)，设置较长延迟
generate_testset_task.max_tries = 3 # type: ignore
generate_testset_task.retry_delay = 10 # type: ignore

async def run_experiment_task(ctx: Any, experiment_id: int):
    await asyncio.to_thread(_sync_run_experiment_wrapper, experiment_id)

# 配置重试：涉及大量 LLM 交互，同样设置较长延迟
run_experiment_task.max_tries = 3 # type: ignore
run_experiment_task.retry_delay = 10 # type: ignore
# --- Arq 配置 ---

class WorkerSettings:
    # 注册任务列表
    functions = [
        process_document_task, 
        delete_knowledge_task, 
        generate_testset_task, 
        run_experiment_task
    ]
    
    redis_settings = RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    
    on_startup = startup
    on_shutdown = shutdown