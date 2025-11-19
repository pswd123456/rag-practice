from functools import lru_cache
from typing import Generator

from fastapi import Depends
from sqlmodel import Session

from app.core.config import Settings, settings
from app.db.session import get_session
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.generation import QAService
from app.services.pipelines import RAGPipeline
from app.services.retrieval import RetrievalService, VectorStoreManager

# ---- Settings & DB ----

#用于测试override settings, 正常来说config.py会生成一个唯一单例的settings对象
# unused
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return settings
# unused
def get_settings_dependency() -> Settings:
    return get_settings()
# unused
def get_db_session() -> Generator[Session, None, None]:
    yield from get_session()

# ---- Model Factories ----


@lru_cache(maxsize=1)
def _get_embed_model():
    return setup_embed_model("text-embedding-v4")


@lru_cache(maxsize=1)
def _get_llm():
    return setup_qwen_llm("qwen-flash")


@lru_cache(maxsize=1)
def _get_vector_store_manager() -> VectorStoreManager:
    manager = VectorStoreManager(
        collection_name=settings.CHROMADB_COLLECTION_NAME,
        embed_model=_get_embed_model(),
        default_top_k=settings.TOP_K,
    )
    manager.ensure_collection()
    return manager


def get_vector_store_manager() -> VectorStoreManager:
    return _get_vector_store_manager()


@lru_cache(maxsize=1)
def _get_qa_service() -> QAService:
    return QAService(_get_llm())


# unused
def get_retrieval_service(
    manager: VectorStoreManager = Depends(get_vector_store_manager),
) -> RetrievalService:
    retriever = manager.as_retriever()
    return RetrievalService(retriever)


@lru_cache(maxsize=1)
def _get_rag_pipeline() -> RAGPipeline:
    manager = _get_vector_store_manager()
    retriever_service = RetrievalService(manager.as_retriever())
    qa_service = _get_qa_service()
    return RAGPipeline(retriever_service, qa_service)


def get_rag_pipeline() -> RAGPipeline:
    return _get_rag_pipeline()


def reset_rag_pipeline():
    _get_rag_pipeline.cache_clear()


