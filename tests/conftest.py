import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.api import deps
from app.main import app

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.pool import StaticPool

# 导入需要清除缓存的函数
from app.services.file_storage import get_minio_client
from app.services.retrieval.vector_store import get_chroma_client

# 导入应用配置
from app.core.config import settings

# ==========================================
# 1. 数据库 Fixtures
# ==========================================

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(name="db_session")
async def db_session_fixture() -> AsyncGenerator[AsyncSession, None]:
    """
    创建一个连接到内存 SQLite 的临时数据库会话。
    关键点：它会覆盖 app.dependency_overrides，强制 API 使用这个测试 DB。
    """
    # 1. 在当前 Event Loop 中创建 Engine
    engine = create_async_engine(
        TEST_DATABASE_URL, 
        connect_args={"check_same_thread": False}, 
        poolclass=StaticPool,
    )
    
    # 2. 初始化表结构
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # 3. 创建 Session 工厂
    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

    # 4. 定义依赖覆盖函数
    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    # 5. 【关键】应用依赖覆盖
    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    # 6. Yield Session 给测试函数直接使用 (如果需要)
    async with session_maker() as session:
        yield session

    # 7. 清理：移除依赖覆盖，删除表，关闭引擎
    app.dependency_overrides.clear()
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()

# ==========================================
# 2. Service Mocks (拦截外部 IO)
# ==========================================

@pytest.fixture(autouse=True)
def mock_minio():
    """全局 Mock MinIO 客户端"""
    # 🟢 [关键修复] 清除 LRU 缓存，防止测试间 Mock 对象混淆
    get_minio_client.cache_clear()
    
    with patch("app.services.file_storage.Minio") as mock:
        client = mock.return_value
        client.bucket_exists.return_value = True
        yield client

@pytest.fixture(autouse=True)
def mock_chroma():
    """全局 Mock ChromaDB 客户端"""
    # 🟢 [关键修复] 清除 LRU 缓存
    get_chroma_client.cache_clear()

    with patch("app.services.retrieval.vector_store_manager.Chroma") as mock_chroma_cls, \
         patch("app.services.retrieval.vector_store.chromadb.HttpClient") as mock_http_client:
        
        store_instance = mock_chroma_cls.return_value
        store_instance._collection.count.return_value = 10
        store_instance.delete.return_value = True
        
        yield store_instance

@pytest.fixture(autouse=True)
def mock_redis():
    """全局 Mock Redis/Arq 连接池"""
    with patch("app.api.routes.knowledge.create_pool") as mock_pool_knowledge, \
         patch("app.api.routes.evaluation.create_pool") as mock_pool_eval, \
         patch("app.api.routes.evaluation.RedisSettings"), \
         patch("app.api.routes.knowledge.RedisSettings"):
        
        mock_redis_instance = MagicMock()
        mock_redis_instance.enqueue_job = AsyncMock(return_value="job_id_123")
        mock_redis_instance.close = AsyncMock()
        
        async def return_mock(*args, **kwargs):
            return mock_redis_instance
            
        mock_pool_knowledge.side_effect = return_mock
        mock_pool_eval.side_effect = return_mock
        
        yield mock_redis_instance

@pytest.fixture(autouse=True)
def mock_llm_factory():
    """全局 Mock LLM 和 Embedding 工厂"""
    with patch("app.services.factories.llm_factory.ChatOpenAI") as mock_chat, \
         patch("app.services.factories.embedding_factory.DashScopeEmbeddings") as mock_embed:
        yield mock_chat, mock_embed

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
    

@pytest_asyncio.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]: 
    """
    创建一个异步 HTTP 客户端。
    依赖 db_session 确保在 Client 发起请求前，App 的 DB 依赖已经被 Override。
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client