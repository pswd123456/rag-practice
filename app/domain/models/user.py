# app/domain/models/user.py
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

# 引入 Link 模型
from .user_knowledge_link import UserKnowledgeLink

if TYPE_CHECKING:
    from .knowledge import Knowledge
    from .chat import ChatSession

class UserPlan(str, Enum):
    FREE = "FREE"           
    PRO = "PRO"             
    ENTERPRISE = "ENTERPRISE"

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    email: str = Field(unique=True, index=True, nullable=False)
    hashed_password: str = Field(nullable=False)
    
    full_name: Optional[str] = None
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    daily_request_limit: int = Field(default=10, description="每日对话请求次数限制")
    daily_token_limit: int = Field(default=10000, description="每日Token消耗限制")
    plan: UserPlan = Field(default=UserPlan.FREE, description="用户订阅等级")

    knowledges: List["Knowledge"] = Relationship(back_populates="users", link_model=UserKnowledgeLink)
    chat_sessions: List["ChatSession"] = Relationship(back_populates="user")