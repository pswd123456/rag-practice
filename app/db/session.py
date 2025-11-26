from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# 1. 创建异步 Engine
# echo=False 关闭 SQL 打印，避免日志过多
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

# 2. 创建异步 Session 工厂
# expire_on_commit=False 是为了让对象在 commit 后依然可用（不立即过期失效），这在异步编程中很重要
async_session_maker = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def create_db_and_tables():
    """
    异步初始化数据库表结构。
    在 main.py 的 lifespan 中调用。
    """
    async with engine.begin() as conn:
        # run_sync 允许在异步上下文中执行同步的 SQLModel create_all
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    """
    Dependency for FastAPI: Yields an AsyncSession
    """
    async with async_session_maker() as session:
        yield session