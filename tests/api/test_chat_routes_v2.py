# tests/api/test_chat_routes_v2.py
import pytest
import pytest_asyncio # 🟢 引入
import uuid
from httpx import AsyncClient
from app.domain.models import Knowledge, User, KnowledgeStatus, UserKnowledgeLink, UserKnowledgeRole

# 🟢 改为 pytest_asyncio.fixture
@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient, db_session):
    """快速获取一个已登录用户的 Headers"""
    email = "api_test@example.com"
    password = "password"
    from app.services.user.user_service import UserService
    await UserService.create_user(db_session, email, password)
    
    resp = await async_client.post("/auth/access-token", data={"username": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# 🟢 改为 pytest_asyncio.fixture
@pytest_asyncio.fixture
async def user_knowledge(db_session):
    """创建一个属于 api_test 用户的知识库 (通过 Link)"""
    from sqlmodel import select
    result = await db_session.exec(select(User).where(User.email == "api_test@example.com"))
    user = result.first()
    
    kb = Knowledge(name="API Test KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    # 创建 Link
    link = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.OWNER)
    db_session.add(link)
    await db_session.commit()
    
    return kb

@pytest.mark.asyncio
async def test_chat_session_lifecycle(async_client, auth_headers, user_knowledge):
    """
    [Integration] 测试完整的会话生命周期
    """
    # 1. 创建会话
    payload = {"knowledge_id": user_knowledge.id, "title": "API Session"}
    resp = await async_client.post("/chat/sessions", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    session_id = data["id"]
    assert data["title"] == "API Session"
    
    # 2. 获取列表
    resp = await async_client.get("/chat/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert resp.json()[0]["id"] == session_id

    # 3. 发送消息 (Mock Pipeline)
    from unittest.mock import MagicMock, AsyncMock
    from app.api import deps
    
    mock_pipeline = MagicMock()
    mock_pipeline.async_query = AsyncMock(return_value=("Mock Answer", []))
    
    async def mock_factory(*args, **kwargs):
        return mock_pipeline
    
    from app.main import app
    app.dependency_overrides[deps.get_rag_pipeline_factory] = lambda: mock_factory

    try:
        chat_payload = {"query": "Hello API", "stream": False}
        resp = await async_client.post(f"/chat/sessions/{session_id}/completion", json=chat_payload, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["answer"] == "Mock Answer"
        
        # 4. 验证历史记录接口
        resp = await async_client.get(f"/chat/sessions/{session_id}/messages", headers=auth_headers)
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) == 2 
        assert msgs[0]["content"] == "Hello API"
        assert msgs[1]["content"] == "Mock Answer"
        
    finally:
        app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_chat_permission_denied(async_client, db_session):
    pass