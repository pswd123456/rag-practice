import logging
from typing import Optional, Any, Dict

from langchain_core.retrievers import BaseRetriever
from app.services.retrieval.vector_store_manager import VectorStoreManager

logger = logging.getLogger(__name__)

class RetrievalFactory:
    """
    负责根据策略 (Strategy) 和配置 (Config) 组装并返回 Retriever 实例。
    """

    @staticmethod
    def create_retriever(
        store_manager: VectorStoreManager,
        strategy: str = "default",
        top_k: int = 4,
        knowledge_id: Optional[int] = None,
        **kwargs: Any
    ) -> BaseRetriever:
        """
        核心工厂方法：根据策略返回对应的 Retriever。
        
        :param store_manager: 向量库管理器 (提供基础向量检索能力)
        :param strategy: 检索策略 ("default", "dense", "hybrid", "rerank")
        :param top_k: 检索数量
        :param knowledge_id: 知识库 ID (用于 Filter)
        :param kwargs: 其他策略特定参数 (e.g. hybrid_alpha, rerank_model)
        """
        
        # 1. 构造基础查询参数
        search_kwargs: Dict[str, Any] = {"k": top_k}
        
        # 如果提供了 knowledge_id，添加 metadata 过滤
        if knowledge_id:
            search_kwargs["filter"] = {"knowledge_id": knowledge_id}
            
        logger.debug(f"构建 Retriever | 策略: {strategy} | KnowledgeID: {knowledge_id} | TopK: {top_k}")

        # 2. 根据策略分发
        if strategy in ["default", "dense", "dense_only"]:
            return RetrievalFactory._create_dense_retriever(store_manager, search_kwargs)
            
        elif strategy == "hybrid":
            return RetrievalFactory._create_hybrid_retriever(store_manager, search_kwargs, **kwargs)
            
        elif strategy == "rerank":
            return RetrievalFactory._create_rerank_retriever(store_manager, search_kwargs, **kwargs)
            
        else:
            logger.warning(f"未知策略 '{strategy}'，回退到 Dense 检索。")
            return RetrievalFactory._create_dense_retriever(store_manager, search_kwargs)

    @staticmethod
    def _create_dense_retriever(manager: VectorStoreManager, search_kwargs: dict) -> BaseRetriever:
        """
        构建纯向量检索 (LangChain Chroma 原生)
        """
        return manager.vector_store.as_retriever(search_kwargs=search_kwargs)

    @staticmethod
    def _create_hybrid_retriever(manager: VectorStoreManager, search_kwargs: dict, **kwargs) -> BaseRetriever:
        """
        TODO [V2]: 实现混合检索 (BM25 + Vector)
        目前暂时回退到 Dense，待 V2 引入 rank_bm25 后填充
        """
        logger.info("Hybrid 检索尚未完全实现，暂时使用 Dense Retriever 替代。")
        return manager.vector_store.as_retriever(search_kwargs=search_kwargs)

    @staticmethod
    def _create_rerank_retriever(manager: VectorStoreManager, search_kwargs: dict, **kwargs) -> BaseRetriever:
        """
        TODO [V2]: 实现重排序检索 (ContextualCompressionRetriever + CrossEncoder)
        目前暂时回退到 Dense，待 V2 引入 sentence-transformers 后填充
        """
        logger.info("Rerank 检索尚未完全实现，暂时使用 Dense Retriever 替代。")
        return manager.vector_store.as_retriever(search_kwargs=search_kwargs)