# app/domain/models/knowledge.py
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from enum import Enum

if TYPE_CHECKING:
    from .document import Document
    from .experiment import Experiment
    from .user import User
    from .chat import ChatSession 

class KnowledgeStatus(str, Enum):
    NORMAL = "NORMAL"
    DELETING = "DELETING"
    FAILED = "FAILED"

class KnowledgeBaseBase(SQLModel):
    name: str = Field(index=True) # 注意：移除了 unique=True，因为不同用户可能有同名库，或者需要在应用层做 (user_id, name) 联合唯一
    description: Optional[str] = Field(default=None)
    embed_model: str = Field(default="text-embedding-v4", description="embedding 模型名称")
    chunk_size: int = Field(default=512, description="分块大小")
    chunk_overlap: int = Field(default=50, description="分块重叠大小")

class Knowledge(KnowledgeBaseBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    

    user_id: int = Field(foreign_key="user.id", nullable=False)

    status: KnowledgeStatus = Field(default=KnowledgeStatus.NORMAL)
    
    # 关系
    documents: List["Document"] = Relationship(back_populates="knowledge_base")
    experiments: List["Experiment"] = Relationship(back_populates="knowledge")
    
    user: "User" = Relationship(back_populates="knowledges")
    chat_sessions: List["ChatSession"] = Relationship(back_populates="knowledge")

class KnowledgeCreate(KnowledgeBaseBase):
    pass

class KnowledgeRead(KnowledgeBaseBase):
    id: int
    status: KnowledgeStatus
    user_id: int # API 可能会返回 Owner ID

class KnowledgeUpdate(KnowledgeBaseBase):
    name: Optional[str] = None
    description: Optional[str] = None