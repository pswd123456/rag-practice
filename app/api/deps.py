from functools import lru_cache
from typing import Generator, Optional

from fastapi import Depends
from sqlmodel import Session

from app.core.config import Settings, settings
from app.db.session import get_session
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.generation import QAService
from app.services.pipelines import RAGPipeline
from app.services.retrieval import RetrievalService, VectorStoreManager
from app.domain.models import Knowledge

# ---- Model Factories ----

@lru_cache(maxsize=1)
def _get_llm():
    return setup_qwen_llm("qwen-flash")

@lru_cache(maxsize=1)
def _get_qa_service() -> QAService:
    return QAService(_get_llm())

def get_rag_pipeline_factory(
    db: Session = Depends(get_session), # <--- [新增] 注入 DB Session
    qa_service: QAService = Depends(_get_qa_service)
):
    """
    工厂函数：根据 knowledge_id 动态构建 Pipeline
    """
    def create_pipeline(knowledge_id: Optional[int], 
                        top_k: int = settings.TOP_K,
                        strategy: str = "default"
                        ):
        
        # === 🚀 [修复] 动态连接正确的向量集合 ===
        if knowledge_id:
            # 1. 查库获取配置
            knowledge = db.get(Knowledge, knowledge_id)
            if not knowledge:
                raise ValueError(f"Knowledge Base {knowledge_id} not found")
            
            # 2. 构造对应的 Manager
            collection_name = f"kb_{knowledge.id}"
            embed_model = setup_embed_model(knowledge.embed_model)
            
            manager = VectorStoreManager(
                collection_name=collection_name,
                embed_model=embed_model,
                default_top_k=top_k
            )
            # 确保连接（但不自动填充）
            manager.ensure_collection()
            
        else:
            # 兜底逻辑（比如不选知识库时的纯闲聊，或者旧逻辑）
            # 这里的行为取决于你的业务定义，暂时可以用默认配置
            embed_model = setup_embed_model("text-embedding-v4")
            manager = VectorStoreManager(settings.CHROMADB_COLLECTION_NAME, embed_model)

        # 3. 构建 Pipeline
        return RAGPipeline.build(
            store_manager=manager,
            qa_service=qa_service,
            knowledge_id=knowledge_id, # 这个参数传进去主要用于 filter，但在分库架构下其实 filter 作用变弱了
            top_k=top_k,
            strategy=strategy
        )
        
    return create_pipeline

