import logging
from typing import Optional, Any, Dict, List

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
        **kwargs: Any
    ) -> BaseRetriever:
        
        search_kwargs: Dict[str, Any] = {"k": top_k}
        es_filter = RetrievalFactory._build_es_filter(knowledge_id)
        if es_filter:
            search_kwargs["filter"] = es_filter
            
        logger.debug(f"构建 Retriever | 策略: {strategy} | KnowledgeID: {knowledge_id} | TopK: {top_k}")

        if strategy in ["dense", "dense_only"]:
             return RetrievalFactory._create_dense_retriever(store_manager, search_kwargs)
            
        elif strategy in ["default", "hybrid", "rerank"]: 
             # Rerank 策略在 Retrieval 阶段本质上就是 Hybrid 召回
             return RetrievalFactory._create_hybrid_retriever(store_manager, search_kwargs, **kwargs)
        
        else:
             logger.warning(f"未知策略 '{strategy}'，回退到 Dense 检索。")
             return RetrievalFactory._create_dense_retriever(store_manager, search_kwargs)

    @staticmethod
    def _build_es_filter(knowledge_id: Optional[int]) -> List[Dict[str, Any]]:
        """
        构建 Elasticsearch DSL Filter。
        使用 Term 查询精确匹配 metadata.knowledge_id。
        """
        if not knowledge_id:
            return []
        
        # ES DSL 格式: [{"term": {"metadata.knowledge_id": 123}}]
        return [{"term": {"metadata.knowledge_id": knowledge_id}}]

    @staticmethod
    def _create_dense_retriever(manager: VectorStoreManager, search_kwargs: dict) -> BaseRetriever:
        """
        构建 Dense (向量) 检索
        """
        # 复用 Manager 中已缓存的 Store (默认配置即为 Dense)
        store = manager.get_vector_store()
        
        return store.as_retriever(
            search_type="similarity", # 显式指定相似度搜索
            search_kwargs=search_kwargs
        )

    @staticmethod
    def _create_hybrid_retriever(manager: VectorStoreManager, search_kwargs: dict, **kwargs) -> BaseRetriever:
        """
        构建 Hybrid (向量 + 关键词) 检索
        使用应用层 RRF 实现
        """
        top_k = search_kwargs.get("k", 4)
        
        # 解析 search_kwargs 中的 filter 提取 knowledge_id
        # 我们之前构造的是 [{"term": {"metadata.knowledge_id": 101}}]
        knowledge_id = None
        filters = search_kwargs.get("filter", [])
        if filters and isinstance(filters, list):
            # 简单的解析逻辑，假设只有一个 filter 且是 knowledge_id
            for f in filters:
                if "term" in f and "metadata.knowledge_id" in f["term"]:
                    knowledge_id = f["term"]["metadata.knowledge_id"]

        logger.info(f"初始化 Hybrid Retriever (Manual RRF), KID: {knowledge_id}")

        return ESHybridRetriever(
            store_manager=manager,
            top_k=top_k,
            knowledge_id=knowledge_id
        )

    # _create_rerank_retriever 暂时移除或合并逻辑，因为 Rerank 通常是在 Retriever 之外的逻辑，
    # 或者是一个 ContextualCompressionRetriever，这取决于具体架构。
    # 这里我们假设 Rerank 策略暂时退化为 Hybrid 召回。