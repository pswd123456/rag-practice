# tests/domain/test_model_relationships.py
import pytest
import uuid
from sqlmodel import select
from app.domain.models import User, Knowledge, ChatSession, Message, KnowledgeStatus

@pytest.mark.asyncio
async def test_user_knowledge_relationship(db_session):
    """
    [TDD] 验证 User 与 Knowledge 的 1:N 关系
    """
    # 1. 创建用户
    user = User(email="test_kb_owner@example.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 2. 创建关联用户的知识库
    kb = Knowledge(
        name="User's KB", 
        user_id=user.id,  # 新增字段
        status=KnowledgeStatus.NORMAL
    )
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    # 3. 验证反向查询
    # 需要重新加载 user 的 knowledges 关系
    # 注意：在异步模式下，访问延迟加载的关系需要显式加载或在 session 中进行
    await db_session.refresh(user, ["knowledges"])
    
    assert len(user.knowledges) == 1
    assert user.knowledges[0].name == "User's KB"
    assert kb.user_id == user.id

@pytest.mark.asyncio
async def test_chat_session_structure(db_session):
    """
    [TDD] 验证 ChatSession 结构及其与 User/Knowledge 的关系
    """
    # 1. 准备基础数据
    user = User(email="chat_user@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    kb = Knowledge(name="Chat KB", user_id=user.id)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    # 2. 创建会话 (ChatSession)
    session_id = uuid.uuid4()
    chat_session = ChatSession(
        id=session_id,
        user_id=user.id,
        knowledge_id=kb.id,
        title="Test Conversation"
    )
    db_session.add(chat_session)
    await db_session.commit()
    await db_session.refresh(chat_session)

    # 3. 验证 UUID 主键和外键
    assert chat_session.id == session_id
    assert isinstance(chat_session.id, uuid.UUID)
    assert chat_session.user_id == user.id
    assert chat_session.knowledge_id == kb.id

@pytest.mark.asyncio
async def test_message_persistence(db_session):
    """
    [TDD] 验证 Message 持久化及 JSON 字段存储
    """
    # 准备环境 (User -> KB -> Session)
    user = User(email="msg_user@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    kb = Knowledge(name="Msg KB", user_id=user.id)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    session = ChatSession(user_id=user.id, knowledge_id=kb.id, title="Msg Test")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    # 2. 创建消息 (包含 sources JSON)
    sources_data = [{"file": "test.pdf", "page": 1, "content": "snippet"}]
    msg = Message(
        session_id=session.id,
        role="assistant",
        content="This is a RAG answer.",
        sources=sources_data,
        token_usage=150.5
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    # 3. 验证
    assert msg.role == "assistant"
    assert msg.sources[0]["file"] == "test.pdf" # 验证 JSON 自动序列化/反序列化
    
    # 验证 Session -> Messages 关系
    await db_session.refresh(session, ["messages"])
    assert len(session.messages) == 1
    assert session.messages[0].content == "This is a RAG answer."