# app/main.py

import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from arq import create_pool
from arq.connections import RedisSettings

from app.api import api_router
from app.db.session import create_db_and_tables
from app.core.config import settings
from app.core.logging_setup import setup_logging
from app.services.retrieval.es_client import wait_for_es 

setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 {settings.PROJECT_NAME} 启动中...")
    
    # 初始化 Redis 连接池变量，防止清理时报错
    app.state.redis_pool = None

    try:
        # 1. 数据库检查
        await create_db_and_tables()
        logger.info("✅ 数据库初始化完成。")

        # 2. 初始化 Redis 连接池 (Global Pool)
        # 这样可以避免每次请求都建立新的连接
        logger.info(f"正在初始化 Redis 连接池 ({settings.REDIS_HOST}:{settings.REDIS_PORT})...")
        app.state.redis_pool = await create_pool(
            RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        )
        logger.info("✅ Redis 连接池就绪。")

        # 3. ES 健康检查
        logger.info("⏳ 正在检查 Elasticsearch 连接...")
        await asyncio.to_thread(wait_for_es)

    except Exception as e:
        logger.critical(f"❌ 服务启动自检失败: {e}", exc_info=True)
        # 确保即使失败也尝试清理资源
        if app.state.redis_pool:
            await app.state.redis_pool.close()
        raise e
    
    logger.info("✅ API 服务已就绪 (DB & ES & Redis Connected)。")
    yield
    
    logger.info(f"🛑 {settings.PROJECT_NAME} 正在关闭...")
    # 清理 Redis 连接池
    if app.state.redis_pool:
        await app.state.redis_pool.close()
        logger.info("Redis 连接池已关闭。")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    lifespan=lifespan
)

app.include_router(api_router)

@app.get("/", tags=["General"])
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

if __name__ == "__main__":
    import uvicorn
    logger.info("🔧 开发模式启动 (Direct Run)...")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None, 
        log_level="info"
    )