# app/services/chat/chat_service.py
import logging
import uuid
from typing import List, Optional, Dict, Any, Sequence

from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.domain.models import ChatSession, Message
from app.domain.schemas.chat import ChatSessionUpdate
from app.core.config import settings

logger = logging.getLogger(__name__)

async def create_session(
    db: AsyncSession, 
    user_id: int, 
    knowledge_id: int, 
    title: str = "新对话",
    icon: str = "message-square"
) -> ChatSession:
    """创建新的对话会话"""
    session = ChatSession(
        user_id=user_id,
        knowledge_id=knowledge_id,
        knowledge_ids=[knowledge_id], # 默认包含主 KB
        title=title,
        icon=icon,
        top_k=settings.TOP_K
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def update_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: int,
    update_data: ChatSessionUpdate
) -> ChatSession:
    """更新会话设置"""
    session = await get_session_by_id(db, session_id, user_id)
    
    if update_data.title is not None:
        session.title = update_data.title
    if update_data.icon is not None:
        session.icon = update_data.icon
    if update_data.top_k is not None: # [New]
        session.top_k = update_data.top_k
        
    if update_data.knowledge_ids is not None:
        # 确保不为空，如果为空至少保留原本的主 KB
        if not update_data.knowledge_ids:
             session.knowledge_ids = [session.knowledge_id]
        else:
             session.knowledge_ids = update_data.knowledge_ids
             # 如果原来的主ID不在新列表中，更新主ID为新列表的第一个 (保持数据一致性)
             if session.knowledge_id not in update_data.knowledge_ids:
                 session.knowledge_id = update_data.knowledge_ids[0]

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
    
    # 数据迁移兼容：如果 knowledge_ids 为空，用 knowledge_id 填充
    if not session.knowledge_ids:
        session.knowledge_ids = [session.knowledge_id]
        db.add(session)
        await db.commit()
        
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
        is_default_title = session.title in ["新对话", "New Chat"]
        # 如果是 User 第一条消息且标题未改，自动生成标题
        if role == "user" and is_default_title:
            # 截取前20字
            new_title = content.strip()[:20]
            if len(content) > 20:
                new_title += "..."
            session.title = new_title
        
        session.updated_at = message.created_at
        db.add(session)

    await db.commit()
    await db.refresh(message)
    return message

async def get_session_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: int,
    limit: int = 20 # 默认值可以稍微大一点
) -> Sequence[Message]:
    """
    获取会话最近的历史消息 (滑动窗口)。
    策略: DESC 排序取 limit -> 内存反转为 ASC
    """
    # 1. 鉴权 (确保 Session 属于该 User)
    await get_session_by_id(db, session_id, user_id)
    
    # 2. 倒序查询最近的 limit 条
    statement = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc()) # 关键：倒序
        .limit(limit)                        # 关键：限制数量
    )
    result = await db.exec(statement)
    
    # 3. 结果是 [新 -> 旧]，需要反转为 [旧 -> 新]
    # 例如：查询得到 [Msg10, Msg9, Msg8]，翻转为 [Msg8, Msg9, Msg10]
    messages = result.all()
    return list(reversed(messages))