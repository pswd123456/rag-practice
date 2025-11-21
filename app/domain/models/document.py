from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from enum import Enum

if TYPE_CHECKING:
    from .knowledge import Knowledge
    from .chunk import Chunk

class DocStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # 归属关系
    knowledge_base_id: int = Field(foreign_key="knowledge.id")

    #文件metadata
    filename: str
    file_path: str = Field(description= "MinIO 文件路径")
    file_hash: Optional[str] = Field(default=None, description="文件MD5 用于去重")

    # 任务状态
    status: DocStatus = Field(default=DocStatus.PENDING)
    error_message: Optional[str] = Field(default=None)

    # 关于文档的信息, 比如页数和作者, 使用JSON 存储
    meta_info: Optional[Dict[str, Any]] = Field(default=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # 关系定义
    knowledge_base: "Knowledge" = Relationship(back_populates="documents")
    chunks: List["Chunk"] = Relationship(back_populates="document")

