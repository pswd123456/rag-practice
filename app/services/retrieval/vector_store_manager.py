from __future__ import annotations

import logging
from typing import Any, Dict, Optional, List

from langchain_chroma import Chroma
from langchain_core.retrievers import BaseRetriever

from app.services.ingest import build_or_get_vector_store

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """
    管理向量数据库生命周期，提供热加载与统计接口。
    """

    def __init__(self, collection_name: str, embed_model: Any, default_top_k: int = 4):
        self.collection_name = collection_name
        self.embed_model = embed_model
        self.default_top_k = default_top_k
        self._vector_store: Optional[Chroma] = None

    @property
    def vector_store(self) -> Chroma:
        if self._vector_store is None:
            logger.debug("Vector store 未加载，自动触发 ensure_collection()。")
            self.ensure_collection()
        assert self._vector_store is not None  # 类型检查
        return self._vector_store

    def ensure_collection(self, rebuild: bool = False) -> Chroma:
        """
        确保向量库已就绪，必要时重新构建。
        """
        logger.info("确保集合 %s 可用 (rebuild=%s)。", self.collection_name, rebuild)
        self._vector_store = build_or_get_vector_store(
            self.collection_name,
            embed_model=self.embed_model,
            force_rebuild=rebuild,
            auto_ingest=False
        )
        return self._vector_store

    def reload(self, force_rebuild: bool = False) -> Chroma:
        """
        显式重新加载/重建集合。
        """
        self._vector_store = None
        return self.ensure_collection(rebuild=force_rebuild)

    def as_retriever(self, search_kwargs: Optional[Dict[str, Any]] = None) -> BaseRetriever:
        """
        暴露 LangChain Retriever。
        """
        kwargs = {"search_kwargs": {"k": self.default_top_k}}
        if search_kwargs:
            kwargs["search_kwargs"].update(search_kwargs)
        return self.vector_store.as_retriever(**kwargs)

    def stats(self) -> Dict[str, Any]:
        """
        返回集合统计信息用于监控。
        """
        chroma_collection = self.vector_store._collection
        chunk_count = chroma_collection.count()
        metadata_fields: Dict[str, Any] = {}

        if chunk_count > 0:
            snapshot = chroma_collection.get(include=["metadatas"])
            metadatas = snapshot.get("metadatas")
            if metadatas and len(metadatas) > 0:
                # 取第一个元素
                first_item = metadatas[0]
                # 如果这个元素不是 None，转换成普通 dict 赋值
                if first_item:
                    metadata_fields = dict(first_item)

        return {
            "collection_name": self.collection_name,
            "chunk_count": chunk_count,
            "metadata_fields": list(metadata_fields.keys()),
        }

    def delete_vectors(self, ids: List[str]) -> bool:
        """
        根据 Chroma ID 列表从向量库中批量删除切片。
        
        :param ids: 要删除的 Chroma ID 列表
        :return: 操作是否成功 (Chroma API 通常不返回具体结果，这里简化为 True)
        """
        if not ids:
            logger.info("删除向量列表为空，跳过 Chroma 删除操作。")
            return True
        
        logger.info("正在从 Chroma 集合 %s 删除 %s 个向量...", self.collection_name, len(ids))
        try:
            # self.vector_store 继承自 LangChain Chroma，底层是 Chroma 客户端
            self.vector_store._collection.delete(ids=ids)
            logger.info("Chroma 向量删除成功。")
            return True
        except Exception as e:
            logger.error(f"从 Chroma 删除向量失败: {e}", exc_info=True)
            # 在事务中，如果这一步失败，我们会向上抛出异常，让 Postgres 事务回滚
            raise
