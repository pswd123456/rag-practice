import logging
import logging.config
import os
from fastapi import FastAPI

from app.db.session import create_db_and_tables
from app.api import api_router
from app.core.config import settings
from app.core.logging_setup import get_logging_config

# --- 1. 确保日志目录存在 ---
os.makedirs(settings.LOG_DIR, exist_ok=True)

# --- 2. 配置全局日志 (从配置加载) ---
# 获取配置字典 (将 Path 转换为 str)
logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))
# 应用日志配置
logging.config.dictConfig(logging_config_dict)

# --- 3. 获取主模块 Logger ---
# (这会继承 root 配置)
logger = logging.getLogger(__name__)
async def lifespan(app: FastAPI):
    """
    在 FastAPI 应用启动时执行的异步上下文管理器。
    - 记录启动信息
    - 创建数据库表
    在应用关闭时:
    - 记录关闭信息
    """
    logger.info("API 启动中...")
    
    # --- 数据库初始化 ---
    logger.info("正在初始化数据库连接和表...")
    try:
        # 注意: create_db_and_tables() 是一个同步调用。
        # 这在启动时通常是可以接受的，因为它确保了在应用开始接受请求之前
        # 数据库是准备好的。
        # 如果它非常慢，可以考虑
        # await asyncio.to_thread(create_db_and_tables)
        create_db_and_tables()
        logger.info("数据库表初始化完成。")
    except Exception as e:
        logger.critical(f"数据库初始化失败，应用将退出: {e}", exc_info=True)
        # 抛出异常以阻止应用启动
        raise RuntimeError(f"数据库初始化失败: {e}") from e
    
    logger.info("API 已准备好接受请求。")
    
    yield
    
    # --- 'yield' 之后是关闭逻辑 ---
    logger.info("API 正在关闭...")
    # (如果需要，添加清理逻辑, e.g., app.state.my_model.close())
    logger.info("API 已停止。")


# --- 5. 创建 FastAPI 应用实例 ---
app = FastAPI(
    title=settings.PROJECT_NAME,  # 建议从 settings 加载
    description="一个用于 RAG 实验的 API", # 也可以从 settings 加载
    version="0.1.0",              # 也可以从 settings 加载
    lifespan=lifespan             # type: ignore
)

# --- 6. 包含 API 路由 ---
# 最佳实践: 添加 prefix 和 tags
app.include_router(api_router)

# --- 7. 定义根路由 ---
@app.get("/", tags=["General"])
def read_root():
    """
    根路由，用于健康检查或基本信息。
    """
    return {"message": f"欢迎使用 {settings.PROJECT_NAME}"}


# --- 8. (可选) UVicorn 运行入口 ---
# 仅在直接运行此文件时 (python app.py) 才启动 uvicorn
# 生产环境通常会使用 gunicorn + uvicorn worker
if __name__ == "__main__":
    import uvicorn
    logger.info("以开发模式直接运行 app.py (host=0.0.0.0, port=8000, reload=True)...")
    uvicorn.run(
        "app:app",  # 引用 app.py 文件中的 app 实例
        host="0.0.0.0",
        port=8000,
        reload=True,      # 开发时启用热重载
        log_level="info"  # uvicorn 自己的日志级别
    )