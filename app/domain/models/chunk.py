from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .document import Document

class Chunk(SQLModel, table=True): 
    id: Optional[int] = Field(default=None, primary_key=True)

    # 核心映射字段
    document_id: int = Field(foreign_key="document.id")
    chroma_id: str = Field(index=True, description="corresponding id in chromadb")


    # 辅助字段 用于前端展示引用来源
    chunk_index: int = Field(description="index of chunk in document")
    content: str = Field(description="chunk content")
    page_number: Optional[int] = Field(default=None, description="page_number of chunk")

    document: "Document" = Relationship(back_populates="chunks") 