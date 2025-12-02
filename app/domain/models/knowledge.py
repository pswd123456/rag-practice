# app/domain/models/knowledge.py
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from enum import Enum
from .user_knowledge_link import UserKnowledgeLink, UserKnowledgeRole

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
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None)
    embed_model: str = Field(default="text-embedding-v4", description="embedding 模型名称")
    chunk_size: int = Field(default=512, description="分块大小")
    chunk_overlap: int = Field(default=50, description="分块重叠大小")

class Knowledge(KnowledgeBaseBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # [修改] 移除了 user_id 字段
    # user_id: int = Field(foreign_key="user.id", nullable=False)

    status: KnowledgeStatus = Field(default=KnowledgeStatus.NORMAL)
    
    # 关系
    documents: List["Document"] = Relationship(back_populates="knowledge_base")
    experiments: List["Experiment"] = Relationship(back_populates="knowledge")
    
    # [修改] M:N 关系定义
    # link_model 指向中间表
    users: List["User"] = Relationship(back_populates="knowledges", link_model=UserKnowledgeLink)
    
    chat_sessions: List["ChatSession"] = Relationship(back_populates="knowledge")

class KnowledgeCreate(KnowledgeBaseBase):
    pass

class KnowledgeRead(KnowledgeBaseBase):
    id: int
    status: KnowledgeStatus
    role: UserKnowledgeRole = Field(default=UserKnowledgeRole.VIEWER)

class KnowledgeUpdate(KnowledgeBaseBase):
    name: Optional[str] = None
    description: Optional[str] = None