# app/domain/models/user_knowledge_link.py
from enum import Enum
from typing import Optional
from sqlmodel import SQLModel, Field

class UserKnowledgeRole(str, Enum):
    OWNER = "OWNER"   # 拥有者：完全控制
    EDITOR = "EDITOR" # 编辑者：可上传/删除文档，不可删除库
    VIEWER = "VIEWER" # 观察者：仅可对话/检索

class UserKnowledgeLink(SQLModel, table=True):
    """
    User 与 Knowledge 的多对多关联表，包含角色权限。
    """
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    knowledge_id: int = Field(foreign_key="knowledge.id", primary_key=True)
    
    role: UserKnowledgeRole = Field(default=UserKnowledgeRole.VIEWER)