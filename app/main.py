# app/main.py

import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # 🟢 引入 CORS 中间件
from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.api import api_router
from app.db.session import create_db_and_tables
from app.core.config import settings
from app.core.logging_setup import setup_logging
from app.services.retrieval.es_client import close_es_client, wait_for_es 

setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 {settings.PROJECT_NAME} 启动中...")
    
    app.state.redis_pool = None
    #初始化标准 Redis 客户端用于缓存和限流
    app.state.redis = None

    try:
        await create_db_and_tables()
        logger.info("✅ 数据库初始化完成。")

        logger.info(f"正在初始化 Redis 连接池 ({settings.REDIS_HOST}:{settings.REDIS_PORT})...")
        app.state.redis_pool = await create_pool(
            RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        )
        logger.info("✅ Redis 连接池就绪。")

        app.state.redis = Redis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", 
            decode_responses=True
        )
        logger.info("✅ Redis 缓存客户端就绪。")

        logger.info("⏳ 正在检查 Elasticsearch 连接...")
        await asyncio.to_thread(wait_for_es)

    except Exception as e:
        logger.critical(f"❌ 服务启动自检失败: {e}", exc_info=True)
        if app.state.redis_pool:
            await app.state.redis_pool.close()
        if app.state.redis:
            await app.state.redis.close()
        raise e
    
    logger.info("✅ API 服务已就绪 (DB & ES & Redis Connected)。")
    yield
    
    logger.info(f"🛑 {settings.PROJECT_NAME} 正在关闭...")
    if app.state.redis_pool:
        await app.state.redis_pool.close()
        logger.info("Redis 连接池已关闭。")
    if app.state.redis: 
        await app.state.redis.close()
        
    close_es_client()
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    lifespan=lifespan
)

# 🟢 [FIX] 配置 CORS 中间件
# 允许来自前端的跨域请求 (localhost:3000, localhost:8501 等)
origins = [
    "http://localhost",
    "http://localhost:3000", # Next.js
    "http://localhost:8501", # Streamlit
    "http://127.0.0.1:3000",
    "*" # 开发阶段为了方便，允许所有源 (生产环境请改为具体域名)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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