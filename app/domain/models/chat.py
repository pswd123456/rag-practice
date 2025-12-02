# app/domain/models/chat.py
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship, Column, JSON, Text

if TYPE_CHECKING:
    from .user import User
    from .knowledge import Knowledge

class ChatSession(SQLModel, table=True):
    """
    对话会话表 (Chat Session)
    代表一个对话窗口或主题。
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    
    # 归属关系
    user_id: int = Field(foreign_key="user.id", index=True)
    knowledge_id: int = Field(foreign_key="knowledge.id", index=True)
    
    # 会话元数据
    title: str = Field(default="New Chat", max_length=255)
    is_deleted: bool = Field(default=False) # 软删除
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 关系
    user: "User" = Relationship(back_populates="chat_sessions")
    knowledge: "Knowledge" = Relationship(back_populates="chat_sessions")
    messages: List["Message"] = Relationship(back_populates="session", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Message(SQLModel, table=True):
    """
    消息表 (Message)
    存储对话中的每一条具体的问答。
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    
    session_id: uuid.UUID = Field(foreign_key="chatsession.id", index=True)
    
    role: str = Field(description="user 或 assistant")
    content: str = Field(sa_column=Column(Text)) # 使用 Text 类型存储长文本
    
    # 存储 RAG 引用源 (List[Source])
    sources: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    # 统计信息
    token_usage: float = Field(default=0.0)
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    # 关系
    session: "ChatSession" = Relationship(back_populates="messages")