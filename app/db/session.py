from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker 
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.domain import models

# 1. 创建异步 Engine
# [Fix] 启用 pool_pre_ping=True 以自动处理断开的连接 (InterfaceError: connection is closed)
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False, 
    future=True,
    pool_pre_ping=True
)

# 2. 创建异步 Session 工厂
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def create_db_and_tables():
    """
    异步初始化数据库表结构。
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession: # type: ignore
    async with async_session_maker() as session:
        yield session