from functools import lru_cache
from typing import Generator, Optional

from fastapi import Depends
from sqlmodel import Session

from app.core.config import settings
from app.db.session import get_session
from app.services.factories import setup_embed_model, setup_llm
from app.services.generation import QAService
from app.services.pipelines import RAGPipeline
from app.services.retrieval import VectorStoreManager
from app.domain.models import Knowledge
import logging

logger = logging.getLogger(__name__)


def get_db_session() -> Generator[Session, None, None]:
    yield from get_session()

def get_rag_pipeline_factory(
    db: Session = Depends(get_session),
):
    """
    工厂函数：返回 create_pipeline 函数
    支持动态传入 llm_model 和可选的 knowledge_id
    """
    def create_pipeline(
        knowledge_id: Optional[int] = None, 
        top_k: int = settings.TOP_K,
        strategy: str = "default",
        llm_model: Optional[str] = None
    ) -> RAGPipeline:
        
        # 1. 初始化 LLM & QA Service (支持模型动态切换)
        llm = setup_llm(model_name=llm_model)
        qa_service = QAService(llm)

        # 2. 设定默认向量库配置 (Global / Fallback)
        collection_name = "default_collection"
        embed_model_name = "text-embedding-v4" # 默认 Embedding 模型

        # 3. 如果指定了 Knowledge ID，则尝试覆盖配置
        if knowledge_id:
            knowledge = db.get(Knowledge, knowledge_id)
            if not knowledge:
                # 如果传了 ID 但找不到，抛错是合理的
                raise ValueError(f"Knowledge Base {knowledge_id} not found")
            
            # 覆盖为特定知识库的配置
            collection_name = f"kb_{knowledge.id}"
            embed_model_name = knowledge.embed_model

        else:
            logger.info(f"没有找到可用的kb, kb_id:{knowledge_id}")

        # 4. 初始化 Manager 和 Pipeline
        embed_model = setup_embed_model(embed_model_name)
        
        manager = VectorStoreManager(
            collection_name=collection_name,
            embed_model=embed_model,
            default_top_k=top_k
        )
        # 确保连接就绪
        manager.ensure_collection()

        return RAGPipeline.build(
            store_manager=manager,
            qa_service=qa_service,
            knowledge_id=knowledge_id,
            top_k=top_k,
            strategy=strategy
        )
        
    return create_pipeline