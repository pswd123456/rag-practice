from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from enum import Enum

if TYPE_CHECKING:
    from .document import Document

# 1. 基础 Schema (用于 Pydantic 验证和继承)
class KnowledgeBaseBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: Optional[str] = Field(default=None)

# 2. 数据库表模型
class Knowledge(KnowledgeBaseBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # 添加与 Document 的一对多关系
    documents: List["Document"] = Relationship(back_populates="knowledge_base")

# 3. API 交互用的 Schema (保持你原有的结构，稍微扩展)
class KnowledgeCreate(KnowledgeBaseBase):
    pass

class KnowledgeRead(KnowledgeBaseBase):
    id: int
    # 可以在读取知识库详情时，顺便返回包含的文档数，但暂不返回具体文档列表，以免太重

class KnowledgeUpdate(KnowledgeBaseBase):
    name: Optional[str] = None
    description: Optional[str] = None