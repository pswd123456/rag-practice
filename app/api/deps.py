# app/api/deps.py

import asyncio
import logging
from typing import AsyncGenerator, Optional
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
    """
    从 app.state 获取全局复用的 Redis 连接池。
    """
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
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    if token_data.sub is None:
        raise HTTPException(status_code=404, detail="User identifier not found in token")

    # 根据 sub (这里存的是 user_id) 查询用户
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
    #user: User = Depends(get_current_active_user)
):
    async def create_pipeline(
        knowledge_id: Optional[int] = None, 
        top_k: int = settings.TOP_K, # 这是 Final Top K (默认 3)
        strategy: str = "hybrid",    
        llm_model: Optional[str] = None,
        rerank_model_name: Optional[str] = None # 支持覆盖 Rerank 模型
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
        collection_name = "default_collection"
        embed_model_name = "text-embedding-v4"

        if knowledge_id:
            knowledge = await db.get(Knowledge, knowledge_id)
            if not knowledge:
                raise ValueError(f"Knowledge Base {knowledge_id} not found")
            collection_name = f"kb_{knowledge.id}"
            embed_model_name = knowledge.embed_model

        # 4. Manager
        embed_model = setup_embed_model(embed_model_name)
        manager = VectorStoreManager(collection_name, embed_model)
        await asyncio.to_thread(manager.ensure_index)

        # 5. Build Pipeline
        # 注意: 这里我们将 RECALL_TOP_K 传给 factory 构造 Retriever
        # top_k (Final K) 将在调用 pipeline.async_query 时使用，或者我们在 build 时也可以存入 pipeline
        pipeline = RAGPipeline.build(
            store_manager=manager,
            qa_service=qa_service,
            rerank_service=rerank_service,
            knowledge_id=knowledge_id,
            recall_top_k=settings.RECALL_TOP_K,
            strategy=strategy
        )
        
        # 临时将 final_top_k 绑定到 pipeline 实例上，方便某些不传参的调用 (Optional)
        pipeline.final_top_k = top_k 
        
        return pipeline
        
    return create_pipeline