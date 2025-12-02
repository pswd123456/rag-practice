# app/domain/models/user.py
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .knowledge import Knowledge
    from .chat import ChatSession

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    email: str = Field(unique=True, index=True, nullable=False)
    hashed_password: str = Field(nullable=False)
    
    full_name: Optional[str] = None
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    knowledges: List["Knowledge"] = Relationship(back_populates="user")
    chat_sessions: List["ChatSession"] = Relationship(back_populates="user")