from pydantic import BaseModel
from typing import List, Optional


class QueryRequest(BaseModel):
    """API 请求体模型"""
    query: str
    knowledge_id: Optional[int] = None
    strategy: str = "default"
    llm_model: Optional[str] = None 

class Source(BaseModel):
    """文档来源模型，用于前端展示"""
    source_filename: str
    page_number: Optional[int]
    chunk_content: str
    chunk_id: Optional[str] = None


class QueryResponse(BaseModel):
    """API 响应体模型"""
    answer: str
    sources: List[Source]