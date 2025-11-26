import pytest
import pytest_asyncio
import uuid
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.main import app
from app.db.session import engine

# 🟢 [优化] 更彻底的 Engine 生命周期管理
# 确保在 Loop 关闭前，Engine 已经被正确 dispose
@pytest_asyncio.fixture(scope="session", autouse=True)
async def fix_global_engine_loop():
    # Setup: 确保开始时是干净的
    await engine.dispose()
    
    yield
    
    # Teardown: 测试结束，显式关闭 Engine，防止 GC 在 Loop 关闭后尝试清理连接
    await engine.dispose()

# 1. 全局初始化 DB 表结构
@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database(fix_global_engine_loop): 
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield
    
    # Teardown: 再次清理
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

# 2. 异步数据库 Session
@pytest_asyncio.fixture(scope="function")
async def db():
    # 显式获取连接，方便控制
    connection = await engine.connect()
    transaction = await connection.begin()
    
    session = AsyncSession(bind=connection, expire_on_commit=False)
    
    yield session
    
    # 🟢 [关键] 严格的清理顺序
    await session.close()
    if transaction.is_active:
        await transaction.rollback()
    await connection.close()

# 3. 异步 Client
@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

# --- Helpers ---
def _get_random_suffix():
    return uuid.uuid4().hex[:8]

@pytest_asyncio.fixture(scope="function")
async def temp_kb(client):
    random_name = f"test_kb_{_get_random_suffix()}"
    payload = {"name": random_name, "description": "Auto-created by pytest"}
    
    response = await client.post("/knowledge/knowledges", json=payload)
    if response.status_code != 200:
        yield 0
        return

    kb_id = response.json()["id"]
    yield kb_id
    
    # Teardown
    await client.delete(f"/knowledge/knowledges/{kb_id}")