# app/domain/models/__init__.py
from .knowledge import Knowledge, KnowledgeCreate, KnowledgeRead, KnowledgeUpdate, KnowledgeStatus
from .document import Document, DocStatus
from .testset import Testset   
from .experiment import Experiment 
from .user import User
from .chat import ChatSession, Message
# [新增]
from .user_knowledge_link import UserKnowledgeLink, UserKnowledgeRole

__all__ = [
    "Knowledge", "KnowledgeCreate", "KnowledgeRead", "KnowledgeUpdate", "KnowledgeStatus",
    "Document", "DocStatus",
    "Testset", 
    "Experiment",
    "User",
    "ChatSession", "Message",
    "UserKnowledgeLink", "UserKnowledgeRole"
]