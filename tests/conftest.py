import pytest
import pytest_asyncio
from typing import AsyncGenerator, List
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from elasticsearch import Elasticsearch

from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel.pool import StaticPool

from app.api import deps
from app.main import app
from app.core.config import settings
from app.services.file_storage import get_minio_client
from app.services.retrieval.es_client import get_es_client

# ==========================================
# 1. 数据库 Fixtures
# ==========================================

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(name="db_session")
async def db_session_fixture() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL, 
        connect_args={"check_same_thread": False}, 
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    async with session_maker() as session:
        yield session

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()

# ==========================================
# 2. Service Mocks
# ==========================================

@pytest.fixture(autouse=True)
def mock_minio():
    """全局 Mock MinIO 客户端"""
    get_minio_client.cache_clear()
    with patch("app.services.file_storage.Minio") as mock:
        client = mock.return_value
        client.bucket_exists.return_value = True
        yield client

@pytest.fixture(autouse=True)
def mock_redis():
    """全局 Mock Redis/Arq"""
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

# ==========================================
# 3. Embedding & LLM Mocks (关键修复)
# ==========================================

class FakeEmbeddings:
    """
    用于测试的伪造 Embedding 类，返回固定维度的浮点数向量。
    """
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 返回符合配置维度的向量 (e.g., 1024个 0.1)
        return [[0.1] * settings.EMBEDDING_DIM for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        return [0.1] * settings.EMBEDDING_DIM

@pytest.fixture(autouse=True)
def mock_llm_factory():
    """
    全局 Mock LLM 和 Embedding。
    强制 setup_embed_model 返回 FakeEmbeddings 实例。
    """
    with patch("app.services.factories.llm_factory.ChatOpenAI") as mock_chat, \
         patch("app.services.factories.embedding_factory.DashScopeEmbeddings") as mock_embed_cls:
        
        # [Fix] 这里的 return_value 必须是 FakeEmbeddings 的实例
        # 这样当代码调用 DashScopeEmbeddings(...) 时，就会得到这个 fake 实例
        mock_embed_cls.return_value = FakeEmbeddings()
        
        yield mock_chat, mock_embed_cls

# ==========================================
# 4. Elasticsearch Fixtures
# ==========================================

@pytest.fixture(scope="session")
def es_client():
    """连接真实 ES (用于集成测试)"""
    client = Elasticsearch(
        hosts=settings.ES_URL,
        request_timeout=5,
        max_retries=1
    )
    try:
        if not client.ping():
            pytest.skip("Elasticsearch 未运行，跳过集成测试")
    except Exception:
        pytest.skip("Elasticsearch 连接失败，跳过集成测试")
    yield client
    client.close()


# Helper
class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

@pytest_asyncio.fixture
async def async_client(db_session) -> AsyncGenerator[AsyncClient, None]: 
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

@pytest.fixture
def mock_es_client():
    get_es_client.cache_clear()
    with patch("app.services.retrieval.es_client.Elasticsearch") as mock_cls:
        client = mock_cls.return_value
        client.ping.return_value = True
        client.indices.exists.return_value = False
        yield client

@pytest.fixture(autouse=True)
def override_settings():
    """强制修改测试环境的 ES 前缀"""
    original_prefix = settings.ES_INDEX_PREFIX
    settings.ES_INDEX_PREFIX = "test_rag" # 👈 强制使用测试专用前缀
    yield
    settings.ES_INDEX_PREFIX = original_prefix

@pytest.fixture
def clean_es_index(es_client):
    """清理测试索引"""
    prefix = f"{settings.ES_INDEX_PREFIX}_*"
    es_client.indices.delete(index=prefix, ignore=[400, 404])
    yield
    es_client.indices.delete(index=prefix, ignore=[400, 404])