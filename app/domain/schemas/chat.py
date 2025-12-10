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
    top_k: int 
    knowledge_id: int
    knowledge_ids: List[int]
    user_id: int
    created_at: datetime
    updated_at: datetime

class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    icon: Optional[str] = None
    knowledge_ids: Optional[List[int]] = None
    top_k: Optional[int] = None 

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
    
    # 运行时参数
    top_k: Optional[int] = None 
    llm_model: Optional[str] = None
    rerank_model_name: Optional[str] = None
    
    # 支持自定义 Prompt 名称 (对应 Langfuse 中的 Prompt Name)
    prompt_name: Optional[str] = None 
    
    # 流式标记
    stream: bool = True

class ChatResponse(BaseModel):
    """
    非流式响应
    """
    answer: str
    sources: List[Dict[str, Any]] = []