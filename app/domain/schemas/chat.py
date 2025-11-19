from pydantic import BaseModel
from typing import List, Optional


class QueryRequest(BaseModel):
    """API 请求体模型"""
    query: str
    knowledge_id: Optional[int] = None
    strategy: str = "default"

class Source(BaseModel):
    """文档来源模型，用于前端展示"""
    source_filename: str            # 文件名，例如: "财报 2024.pdf"
    page_number: Optional[int]      # 页码
    chunk_content: str              # 检索到的切片原文（用于显示上下文）
    chunk_id: Optional[str] = None  # ChromaDB 的 ID 或 Document 的 ID (可选)


class QueryResponse(BaseModel):
    """API 响应体模型"""
    answer: str
    sources: List[Source]           # 新增：检索到的文档来源列表