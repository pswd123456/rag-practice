import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api import api_router
from app.db.session import create_db_and_tables
from app.core.config import settings
from app.core.logging_setup import setup_logging
from app.services.retrieval.es_client import wait_for_es 

# --- 1. 初始化日志配置 ---
setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 {settings.PROJECT_NAME} 启动中...")
    try:
        # 1. 数据库检查
        await create_db_and_tables()
        logger.info("✅ 数据库初始化完成。")

        # 2. ES 健康检查 (Operational Risk Fix)
        # wait_for_es 是同步阻塞函数，使用 to_thread 避免阻塞事件循环
        logger.info("⏳ 正在检查 Elasticsearch 连接...")
        await asyncio.to_thread(wait_for_es)
        # wait_for_es 内部成功后会打印 Log，失败会抛出异常

    except Exception as e:
        # 统一捕获启动异常 (DB 或 ES 失败都应阻止启动)
        logger.critical(f"❌ 服务启动自检失败: {e}", exc_info=True)
        raise e
    
    logger.info("✅ API 服务已就绪 (DB & ES Connected)。")
    yield
    logger.info(f"🛑 {settings.PROJECT_NAME} 正在关闭...")

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