# app/worker.py
import asyncio
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from sqlmodel import Session

from app.core.config import settings
from app.db.session import engine
from app.services.ingest.processor import process_document_pipeline
from app.services.knowledge_crud import delete_document_and_vectors

import logging
import logging.config
from app.core.logging_setup import get_logging_config

logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))
logging.config.dictConfig(logging_config_dict)
logger = logging.getLogger(__name__)

async def startup(ctx: Any):
    logger.info("worker startup")
    pass
async def shutdown(ctx: Any):
    logger.info("worker shutdown")
def _sync_process_wrapper(doc_id: int):
    """
    Worker 的同步包装器：负责管理 DB Session 生命周期
    """
    logger.info(f"[Worker] 开始处理任务: 文档ID {doc_id}")
    
    # Worker 负责创建 Session，确保 Service 层不用管 DB 连接的生命周期
    with Session(engine) as db:
        try:
            process_document_pipeline(db, doc_id)
        except Exception as e:
            # 异常已在 Service 内部被捕获并更新了数据库状态，
            # 这里只是为了记录 Worker 级别的日志
            logger.error(f"[Worker] 任务执行遇到异常: {e}")

def _sync_delete_knowledge_wrapper(knowledge_id: int):
    """
    Worker 的同步包装器：负责管理 DB Session 生命周期
    """
    logger.info(f"[Worker] 删除知识库: {knowledge_id}")
    
    # Worker 负责创建 Session，确保 Service 层不用管 DB 连接的生命周期
    with Session(engine) as db:
        try:
            delete_document_and_vectors(db, knowledge_id)
        except Exception as e:
            # 异常已在 Service 内部被捕获并更新了数据库状态，
            # 这里只是为了记录 Worker 级别的日志
            logger.error(f"[Worker] 删除任务执行遇到异常: {e}")

async def delete_knowledge_task(ctx: Any, knowledge_id: int):
    """
    Arq 调用的异步任务入口
    """
    await asyncio.to_thread(_sync_delete_knowledge_wrapper, knowledge_id)

async def process_document_task(ctx: Any, doc_id: int):
    """
    Arq 调用的异步任务入口
    """
    await asyncio.to_thread(_sync_process_wrapper, doc_id)


# --- Arq 配置 ---

class WorkerSettings:
    # 注册可以被执行的任务函数列表
    functions = [process_document_task, delete_knowledge_task]

    # 配置 Redis 连接
    redis_settings = RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    
    # 启动和关闭时的钩子（当前仅打印日志）
    on_startup = startup
    on_shutdown = shutdown




