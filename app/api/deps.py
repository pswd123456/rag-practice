# app/api/deps.py

import asyncio
import logging
from typing import AsyncGenerator, Optional, List
from fastapi import Depends, Request, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession
from arq import ArqRedis

from app.core.config import settings
from app.db.session import get_session
from app.domain.models import Knowledge, User 
from app.domain.schemas import TokenPayload 
from app.services.factories import setup_embed_model, setup_llm
from app.services.generation import QAService
from app.services.pipelines import RAGPipeline
from app.services.retrieval import VectorStoreManager
from app.services.rerank.rerank_service import RerankService

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl="/auth/access-token"
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session

async def get_redis_pool(request: Request) -> ArqRedis:
    if not hasattr(request.app.state, "redis_pool"):
        raise RuntimeError("Redis pool not initialized in app state")
    return request.app.state.redis_pool

async def get_current_user(
    token: str = Depends(reusable_oauth2),
    db: AsyncSession = Depends(get_db_session)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if token_data.sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User identifier not found in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, int(token_data.sub))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_rag_pipeline_factory(
    db: AsyncSession = Depends(get_db_session),
):
    async def create_pipeline(
        knowledge_ids: Optional[List[int]] = None, 
        knowledge_id: Optional[int] = None, 
        top_k: int = settings.TOP_K, 
        strategy: str = "hybrid",    
        llm_model: Optional[str] = None,
        rerank_model_name: Optional[str] = None
    ) -> RAGPipeline:
        
        # 1. LLM & QA
        llm = setup_llm(model_name=llm_model)
        qa_service = QAService(llm)
        
        # 2. Rerank Service
        target_rerank_model = rerank_model_name or settings.RERANK_MODEL_NAME
        rerank_service = RerankService(
            base_url=settings.RERANK_BASE_URL,
            model_name=target_rerank_model
        )

        # 3. Vector Store Config
        target_ids = []
        if knowledge_ids:
            target_ids = knowledge_ids
        elif knowledge_id:
            target_ids = [knowledge_id]
            
        if not target_ids:
             raise ValueError("Must provide knowledge_id or knowledge_ids")

        # 4. Collection Name Construction
        first_kb = await db.get(Knowledge, target_ids[0])
        if not first_kb:
             raise ValueError(f"Knowledge {target_ids[0]} not found")
             
        collection_names = [f"kb_{kid}" for kid in target_ids]
        collection_name_str = ",".join(collection_names)
        embed_model_name = first_kb.embed_model

        # 5. Manager
        embed_model = setup_embed_model(embed_model_name)
        
        # [Fix] 预先遍历所有知识库，确保它们的物理索引都存在
        # 这样即使某个知识库是空的，也不会导致 ES 抛出 "no such index"
        for single_name in collection_names:
            temp_manager = VectorStoreManager(single_name, embed_model)
            await asyncio.to_thread(temp_manager.ensure_index)

        manager = VectorStoreManager(collection_name_str, embed_model)
        
        # 6. Build Pipeline
        pipeline = RAGPipeline.build(
            store_manager=manager,
            qa_service=qa_service,
            rerank_service=rerank_service,
            knowledge_ids=target_ids, 
            recall_top_k=settings.RECALL_TOP_K,
            strategy=strategy
        )
        
        return pipeline
        
    return create_pipeline