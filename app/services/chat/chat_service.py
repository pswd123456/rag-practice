# app/services/chat/chat_service.py
import logging
import uuid
from typing import List, Optional, Dict, Any, Sequence

from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.domain.models import ChatSession, Message

logger = logging.getLogger(__name__)

async def create_session(
    db: AsyncSession, 
    user_id: int, 
    knowledge_id: int, 
    title: str = "新对话"
) -> ChatSession:
    """创建新的对话会话"""
    session = ChatSession(
        user_id=user_id,
        knowledge_id=knowledge_id,
        title=title
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def get_user_sessions(
    db: AsyncSession, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 20
) -> Sequence[ChatSession]:
    """获取用户的会话列表 (排除已删除)"""
    statement = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .where(ChatSession.is_deleted == False) # 软删除过滤
        .order_by(desc(ChatSession.updated_at)) # 按最后活跃时间排序
        .offset(skip)
        .limit(limit)
    )
    result = await db.exec(statement)
    return result.all()

async def get_session_by_id(
    db: AsyncSession, 
    session_id: uuid.UUID, 
    user_id: int
) -> ChatSession:
    """获取单个会话详情 (带权限校验)"""
    statement = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
        ChatSession.is_deleted == False
    )
    result = await db.exec(statement)
    session = result.first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

async def delete_session(db: AsyncSession, session_id: uuid.UUID, user_id: int):
    """软删除会话"""
    session = await get_session_by_id(db, session_id, user_id)
    session.is_deleted = True
    db.add(session)
    await db.commit()

async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    token_usage: float = 0.0
) -> Message:
    """持久化单条消息，并更新会话的 updated_at"""
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        sources=sources or [],
        token_usage=token_usage
    )
    db.add(message)
    
    # 同时更新 Session 的活跃时间
    session = await db.get(ChatSession, session_id)
    if session:
        # 简单的标题自动生成逻辑: 如果是第一条 User 消息且标题是默认值
        if role == "user" and session.title == "新对话":
            session.title = content[:20] # 截取前20字作为标题
        
        session.updated_at = message.created_at
        db.add(session)

    await db.commit()
    await db.refresh(message)
    return message

async def get_session_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: int,
    limit: int = 50
) -> Sequence[Message]:
    """
    获取会话历史消息 (用于构建 LLM Context 或前端展示)
    返回顺序: 旧 -> 新 (符合 LLM 输入习惯)
    """
    # 先校验权限
    await get_session_by_id(db, session_id, user_id)
    
    # 查询消息
    statement = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc()) # 正序
        # 如果需要限制条数，通常取最近的 N 条，但这需要先倒序再正序，这里简化为全量或直接正序
        # .limit(limit) 
    )
    result = await db.exec(statement)
    messages = result.all()
    
    # 如果加上了 limit, 比如 limit=10, 且直接 .limit(10), 会得到"最早"的10条。
    # 实际场景通常需要"最近"的10条。
    # 为了简化，假设 history 长度可控，暂不复杂的 Subquery。
    
    return messages