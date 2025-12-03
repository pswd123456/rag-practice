import logging
from typing import Optional, Any, Dict, List, Union

from langchain_core.retrievers import BaseRetriever

from app.services.retrieval.hybrid_retriever import ESHybridRetriever
from app.services.retrieval.vector_store_manager import VectorStoreManager

logger = logging.getLogger(__name__)

class RetrievalFactory:
    @staticmethod
    def create_retriever(
        store_manager: VectorStoreManager,
        strategy: str = "hybrid", 
        top_k: int = 50,          
        knowledge_id: Optional[int] = None,
        knowledge_ids: Optional[List[int]] = None, # [New]
        **kwargs: Any
    ) -> BaseRetriever:
        
        search_kwargs: Dict[str, Any] = {"k": top_k}
        
        # 兼容处理 knowledge_id 和 knowledge_ids
        target_ids = []
        if knowledge_ids:
            target_ids = knowledge_ids
        elif knowledge_id:
            target_ids = [knowledge_id]
            
        es_filter = RetrievalFactory._build_es_filter(target_ids)
        if es_filter:
            search_kwargs["filter"] = es_filter
            
        logger.debug(f"构建 Retriever | 策略: {strategy} | KBs: {target_ids} | TopK: {top_k}")

        if strategy in ["dense", "dense_only"]:
             return RetrievalFactory._create_dense_retriever(store_manager, search_kwargs)
            
        elif strategy in ["default", "hybrid", "rerank"]: 
             return RetrievalFactory._create_hybrid_retriever(store_manager, search_kwargs, knowledge_ids=target_ids, **kwargs)
        
        else:
             logger.warning(f"未知策略 '{strategy}'，回退到 Dense 检索。")
             return RetrievalFactory._create_dense_retriever(store_manager, search_kwargs)

    @staticmethod
    def _build_es_filter(knowledge_ids: List[int]) -> List[Dict[str, Any]]:
        """
        构建 Elasticsearch DSL Filter。
        """
        if not knowledge_ids:
            return []
        
        # ES DSL 格式: [{"terms": {"metadata.knowledge_id": [1, 2]}}]
        return [{"terms": {"metadata.knowledge_id": knowledge_ids}}]

    @staticmethod
    def _create_dense_retriever(manager: VectorStoreManager, search_kwargs: dict) -> BaseRetriever:
        store = manager.get_vector_store()
        return store.as_retriever(
            search_type="similarity", 
            search_kwargs=search_kwargs
        )

    @staticmethod
    def _create_hybrid_retriever(
        manager: VectorStoreManager, 
        search_kwargs: dict, 
        knowledge_ids: List[int] = None,
        **kwargs
    ) -> BaseRetriever:
        
        top_k = search_kwargs.get("k", 4)
        
        logger.info(f"初始化 Hybrid Retriever (Manual RRF), KBs: {knowledge_ids}")

        return ESHybridRetriever(
            store_manager=manager,
            top_k=top_k,
            knowledge_ids=knowledge_ids
        )