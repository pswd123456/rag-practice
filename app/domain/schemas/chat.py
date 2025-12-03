# app/domain/schemas/chat.py
from typing import List, Optional, Dict, Any, Union
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

# --- Session Schemas ---

class ChatSessionCreate(BaseModel):
    knowledge_id: int
    title: Optional[str] = "New Chat"
    icon: Optional[str] = "message-square"

class ChatSessionRead(BaseModel):
    id: UUID
    title: str
    icon: str
    knowledge_id: int
    knowledge_ids: List[int]
    user_id: int
    created_at: datetime
    updated_at: datetime

class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    icon: Optional[str] = None
    knowledge_ids: Optional[List[int]] = None

# --- Message Schemas ---

class MessageRead(BaseModel):
    id: int
    role: str
    content: str
    sources: List[Dict[str, Any]] = []
    created_at: datetime

# --- Chat Interaction Schemas ---

class ChatRequest(BaseModel):
    """
    用户发送的消息请求
    """
    query: str
    
    # 运行时参数 (可选覆盖默认值)
    top_k: int = 5
    llm_model: Optional[str] = None
    rerank_model_name: Optional[str] = None
    
    # 流式标记 (可选，部分客户端可能喜欢显式指定)
    stream: bool = True

class ChatResponse(BaseModel):
    """
    非流式响应
    """
    answer: str
    sources: List[Dict[str, Any]] = []