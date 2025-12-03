import pytest
import pytest_asyncio
from app.domain.models import User, Knowledge, ChatSession, UserKnowledgeLink, UserKnowledgeRole, KnowledgeStatus
from app.services.chat import chat_service
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.retrieval.vector_store_manager import VectorStoreManager
from unittest.mock import MagicMock, patch

@pytest_asyncio.fixture
async def setup_data(db_session):
    user = User(email="settings_test@test.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    
    kb1 = Knowledge(name="KB 1", status=KnowledgeStatus.NORMAL)
    kb2 = Knowledge(name="KB 2", status=KnowledgeStatus.NORMAL)
    db_session.add(kb1)
    db_session.add(kb2)
    
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(kb1)
    await db_session.refresh(kb2)
    
    # Links
    db_session.add(UserKnowledgeLink(user_id=user.id, knowledge_id=kb1.id, role=UserKnowledgeRole.OWNER))
    db_session.add(UserKnowledgeLink(user_id=user.id, knowledge_id=kb2.id, role=UserKnowledgeRole.OWNER))
    await db_session.commit()
    
    return user, kb1, kb2

@pytest.mark.asyncio
async def test_update_session_settings(db_session, setup_data):
    """测试更新会话的 Icon, Title 和 Knowledge IDs"""
    user, kb1, kb2 = setup_data
    
    # 1. 创建会话
    session = await chat_service.create_session(db_session, user.id, kb1.id)
    assert session.icon == "message-square" # 默认图标
    assert session.knowledge_ids == [kb1.id] # 默认同步
    
    # 2. 更新设置
    from app.domain.schemas.chat import ChatSessionUpdate
    update_data = ChatSessionUpdate(
        title="Updated Title",
        icon="robot",
        knowledge_ids=[kb1.id, kb2.id]
    )
    
    updated_session = await chat_service.update_session(db_session, session.id, user.id, update_data)
    
    # 3. 验证
    assert updated_session.title == "Updated Title"
    assert updated_session.icon == "robot"
    assert set(updated_session.knowledge_ids) == {kb1.id, kb2.id}

def test_retrieval_factory_multi_kb():
    """测试 RetrievalFactory 构建多索引查询"""
    manager = MagicMock(spec=VectorStoreManager)
    manager.client = MagicMock()
    # 模拟 embed_model
    manager.embed_model = MagicMock()
    manager.embed_model.embed_query.return_value = [0.1] * 1024
    
    # Mock Hybrid Retriever
    with patch("app.services.factories.retrieval_factory.ESHybridRetriever") as MockHybrid:
        RetrievalFactory.create_retriever(
            store_manager=manager,
            strategy="hybrid",
            knowledge_ids=[1, 2]
        )
        
        # 验证传入 ESHybridRetriever 的参数
        call_kwargs = MockHybrid.call_args.kwargs
        assert call_kwargs['knowledge_ids'] == [1, 2]