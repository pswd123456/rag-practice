# app/domain/schemas/knowledge_member.py
from pydantic import BaseModel, EmailStr
from app.domain.models.user_knowledge_link import UserKnowledgeRole

class MemberAddRequest(BaseModel):
    email: EmailStr
    role: UserKnowledgeRole = UserKnowledgeRole.VIEWER

class MemberRead(BaseModel):
    user_id: int
    email: str
    full_name: str | None
    role: UserKnowledgeRole