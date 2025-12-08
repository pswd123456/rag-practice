# tests/api/test_rate_limit.py
import pytest
import datetime
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import status
from app.api import deps
from app.domain.models import User, ChatSession
from app.main import app

# --- 1. Mock Redis Client ---
class MockRedis:
    def __init__(self):
        self.store = {}

    async def incr(self, key: str) -> int:
        val = self.store.get(key, 0) + 1
        self.store[key] = val
        return val

    async def get(self, key: str) -> str:
        val = self.store.get(key)
        return str(val) if val is not None else None

    async def expire(self, key: str, time: int):
        pass

    async def incrby(self, key: str, amount: int) -> int:
        val = self.store.get(key, 0) + amount
        self.store[key] = val
        return val

@pytest.fixture
def mock_redis_client():
    return MockRedis()

# --- 2. Shared Fixtures ---

@pytest.fixture
def mock_pipeline_factory():
    """Mock RAG Pipeline"""
    mock_pipeline = MagicMock()
    # 模拟非流式
    mock_pipeline.async_query = AsyncMock(return_value=("Mock Answer", []))
    # 模拟流式 (生成文本 + Usage)
    async def mock_stream(*args, **kwargs):
        yield "Hello"
        yield {"token_usage_payload": {"input_tokens": 10, "output_tokens": 5}}
    mock_pipeline.astream_with_sources = mock_stream
    
    async def factory(*args, **kwargs):
        return mock_pipeline
    return factory

@pytest.fixture
def mock_chat_session(user_id=1):
    """返回一个 Mock 的 ChatSession 对象"""
    return ChatSession(
        id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        user_id=user_id,
        knowledge_id=1,
        title="Test Chat",
        top_k=3
    )

# --- 3. Test Cases ---

@pytest.mark.asyncio
async def test_daily_request_limit(async_client, mock_redis_client, mock_pipeline_factory):
    """
    [Scenario] 每日请求次数限流测试
    """
    user = User(
        id=101, email="limit_req@test.com", hashed_password="pw", is_active=True,
        daily_request_limit=2, daily_token_limit=10000
    )

    # 覆盖依赖
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    app.dependency_overrides[deps.get_redis] = lambda: mock_redis_client
    app.dependency_overrides[deps.get_rag_pipeline_factory] = lambda: mock_pipeline_factory

    session_id = "00000000-0000-0000-0000-000000000000"
    url = f"/chat/sessions/{session_id}/completion"
    payload = {"query": "hi", "stream": False}

    # 🟢 [关键修复] Mock get_session_by_id 防止 404
    # 注意 path 路径要指向 chat_service 实际定义的地方
    mock_session = ChatSession(id=uuid.UUID(session_id), user_id=user.id, knowledge_id=1)
    
    with patch("app.services.chat.chat_service.get_session_by_id", new_callable=AsyncMock) as mock_get_session, \
         patch("app.services.chat.chat_service.save_message", new_callable=AsyncMock): # Mock save 以免写库报错
        
        mock_get_session.return_value = mock_session

        try:
            # Request 1 (OK)
            resp1 = await async_client.post(url, json=payload)
            assert resp1.status_code == 200, f"Req 1 failed: {resp1.text}"

            # Request 2 (OK)
            resp2 = await async_client.post(url, json=payload)
            assert resp2.status_code == 200, f"Req 2 failed: {resp2.text}"

            # Request 3 (Fail)
            resp3 = await async_client.post(url, json=payload)
            assert resp3.status_code == 429
            assert "Daily request limit exceeded" in resp3.json()["detail"]

        finally:
            app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_daily_token_limit_block(async_client, mock_redis_client, mock_pipeline_factory):
    """
    [Scenario] 每日 Token 额度超限拦截
    """
    user = User(
        id=102, email="limit_token@test.com", hashed_password="pw", is_active=True,
        daily_request_limit=100, daily_token_limit=100
    )
    
    # 预设 Redis: 已用 150
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    token_key = f"limit:token:{today}:{user.id}"
    mock_redis_client.store[token_key] = 150 

    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    app.dependency_overrides[deps.get_redis] = lambda: mock_redis_client
    app.dependency_overrides[deps.get_rag_pipeline_factory] = lambda: mock_pipeline_factory

    session_id = "00000000-0000-0000-0000-000000000000"
    mock_session = ChatSession(id=uuid.UUID(session_id), user_id=user.id, knowledge_id=1)

    # 🟢 Mock Session
    with patch("app.services.chat.chat_service.get_session_by_id", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = mock_session
        
        try:
            resp = await async_client.post(f"/chat/sessions/{session_id}/completion", json={"query": "hi"})
            # 如果这里报 200，说明 dependencies=[Depends(...)] 没生效
            assert resp.status_code == 429
            assert "Daily token quota exceeded" in resp.json()["detail"]
        finally:
            app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_token_usage_increment(async_client, mock_redis_client, mock_pipeline_factory):
    """
    [Scenario] 验证对话结束后 Token 正确回写
    """
    user = User(id=103, email="incr@test.com", is_active=True, daily_token_limit=1000, daily_request_limit=100)
    
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    app.dependency_overrides[deps.get_redis] = lambda: mock_redis_client
    app.dependency_overrides[deps.get_rag_pipeline_factory] = lambda: mock_pipeline_factory

    session_id = "00000000-0000-0000-0000-000000000000"
    mock_session = ChatSession(id=uuid.UUID(session_id), user_id=user.id, knowledge_id=1)

    # 🟢 Mock Session & Save Message
    with patch("app.services.chat.chat_service.get_session_by_id", new_callable=AsyncMock) as mock_get_session, \
         patch("app.services.chat.chat_service.save_message", new_callable=AsyncMock) as mock_save:
        
        mock_get_session.return_value = mock_session

        try:
            resp = await async_client.post(
                f"/chat/sessions/{session_id}/completion", 
                json={"query": "hi", "stream": True}
            )
            assert resp.status_code == 200
            
            # 消费流以触发回写
            async for _ in resp.aiter_bytes(): pass
            
            # 验证 Redis
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            token_key = f"limit:token:{today}:{user.id}"
            
            # input(10) + output(5) = 15
            assert mock_redis_client.store.get(token_key) == 15
            
        finally:
            app.dependency_overrides = {}