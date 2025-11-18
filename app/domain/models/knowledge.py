from typing import Optional
from sqlmodel import SQLModel, Field

# 定义 KnowledgeBase 模型
class KnowledgeBase(SQLModel):
    name: str = Field(index=True)

class Knowledge(KnowledgeBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class KnowledgeCreate(KnowledgeBase):
    pass

class KnowledgeRead(KnowledgeBase):
    id: int = 0

class KnowledgeUpdate(KnowledgeBase):
    name: Optional[str] = None
    
    
