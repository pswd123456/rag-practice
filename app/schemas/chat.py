from pydantic import BaseModel


class QueryRequest(BaseModel):
    """API 请求体模型"""
    query: str


class QueryResponse(BaseModel):
    """API 响应体模型"""
    answer: str