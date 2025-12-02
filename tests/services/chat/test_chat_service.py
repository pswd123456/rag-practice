# tests/services/chat/test_chat_service.py
import pytest
import uuid
from sqlmodel import select
from app.domain.models import User, Knowledge, ChatSession, Message, KnowledgeStatus
from app.services.chat import chat_service

@pytest.fixture
async def chat_user(db_session):
    user = User(email="chat_dev@test.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def chat_kb(db_session, chat_user):
    kb = Knowledge(name="ChatDev KB", user_id=chat_user.id, status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    return kb

@pytest.mark.asyncio
async def test_session_management(db_session, chat_user, chat_kb):
    """验证会话的创建与查询"""
    # 1. 创建会话
    session = await chat_service.create_session(
        db_session, 
        user_id=chat_user.id, 
        knowledge_id=chat_kb.id,
        title="Test Chat"
    )
    assert session.id is not None
    assert session.user_id == chat_user.id
    assert session.title == "Test Chat"

    # 2. 获取列表
    sessions = await chat_service.get_user_sessions(db_session, user_id=chat_user.id)
    assert len(sessions) == 1
    assert sessions[0].id == session.id

    # 3. 验证所有权隔离 (模拟另一个用户)
    other_sessions = await chat_service.get_user_sessions(db_session, user_id=999)
    assert len(other_sessions) == 0

@pytest.mark.asyncio
async def test_message_flow(db_session, chat_user, chat_kb):
    """验证消息发送与历史记录获取"""
    # 1. 创建会话
    session = await chat_service.create_session(db_session, chat_user.id, chat_kb.id)
    
    # 2. 用户发送消息
    msg_user = await chat_service.save_message(
        db_session, 
        session_id=session.id, 
        role="user", 
        content="Hello RAG"
    )
    
    # 3. AI 回复 (带引用)
    sources = [{"file": "doc.pdf", "content": "chunk content"}]
    msg_ai = await chat_service.save_message(
        db_session,
        session_id=session.id,
        role="assistant",
        content="Hi there",
        sources=sources,
        token_usage=50
    )

    # 4. 获取历史记录
    history = await chat_service.get_session_history(db_session, session.id, user_id=chat_user.id)
    assert len(history) == 2
    assert history[0].role == "user"      # 确保顺序：旧 -> 新
    assert history[1].role == "assistant"
    assert history[1].sources[0]["file"] == "doc.pdf"

@pytest.mark.asyncio
async def test_delete_session(db_session, chat_user, chat_kb):
    """验证软删除"""
    session = await chat_service.create_session(db_session, chat_user.id, chat_kb.id)
    
    await chat_service.delete_session(db_session, session.id, chat_user.id)
    
    # 再次查询应为空 (如果 get_user_sessions 过滤了 is_deleted)
    sessions = await chat_service.get_user_sessions(db_session, chat_user.id)
    assert len(sessions) == 0
    
    # 数据库中物理记录应仍在 (软删除)
    db_obj = await db_session.get(ChatSession, session.id)
    assert db_obj.is_deleted is True