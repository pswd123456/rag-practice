from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from enum import Enum

if TYPE_CHECKING:
    from .document import Document
    from .experiment import Experiment

class KnowledgeStatus(str, Enum):
    NORMAL = "NORMAL"
    DELETING = "DELETING"
    FAILED = "FAILED"  # [新增] 支持标记删除/创建失败

# 1. 基础 Schema (用于 Pydantic 验证和继承)
class KnowledgeBaseBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: Optional[str] = Field(default=None)

    # 建议不要修改
    embed_model: str = Field(default="text-embedding-v4", description="embedding 模型名称")
    chunk_size: int = Field(default=512, description="分块大小")
    chunk_overlap: int = Field(default=50, description="分块重叠大小")

# 2. 数据库表模型
class Knowledge(KnowledgeBaseBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    status: KnowledgeStatus = Field(default=KnowledgeStatus.NORMAL)
    # 添加与 Document 的一对多关系
    documents: List["Document"] = Relationship(back_populates="knowledge_base")
    
    experiments: List["Experiment"] = Relationship(back_populates="knowledge")

# 3. API 交互用的 Schema
class KnowledgeCreate(KnowledgeBaseBase):
    pass

class KnowledgeRead(KnowledgeBaseBase):
    id: int
    status: KnowledgeStatus

class KnowledgeUpdate(KnowledgeBaseBase):
    name: Optional[str] = None
    description: Optional[str] = None