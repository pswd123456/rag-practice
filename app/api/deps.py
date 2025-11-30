# app/api/deps.py
import asyncio
import logging
from typing import AsyncGenerator, Optional
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.domain.models import Knowledge
from app.services.factories import setup_embed_model, setup_llm
from app.services.generation import QAService
from app.services.pipelines import RAGPipeline
from app.services.retrieval import VectorStoreManager
# [New]
from app.services.rerank.rerank_service import RerankService

logger = logging.getLogger(__name__)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session

def get_rag_pipeline_factory(
    db: AsyncSession = Depends(get_db_session),
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