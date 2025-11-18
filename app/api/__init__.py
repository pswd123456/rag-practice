from fastapi import APIRouter

from .routes import chat, knowledge

api_router = APIRouter()
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])

