# app/services/retrieval/vector_store_manager.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, List

from langchain_chroma import Chroma
from langchain_core.retrievers import BaseRetriever

from app.services.ingest import build_or_get_vector_store

logger = logging.getLogger(__name__)

# 🟢 1. 定义全局缓存 (Collection Name -> Chroma Instance)
_VECTOR_STORE_CACHE: Dict[str, Chroma] = {}

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
        增加内存缓存机制，避免重复初始化造成的网络开销。
        """
        # 🟢 2. 缓存命中检查
        # 如果不需要重建，且缓存中有，直接返回
        if not rebuild and self.collection_name in _VECTOR_STORE_CACHE:
            # logger.debug(f"⚡️ [Cache Hit] 复用向量库连接: {self.collection_name}")
            self._vector_store = _VECTOR_STORE_CACHE[self.collection_name]
            return self._vector_store

        logger.info("初始化/重建集合 %s (rebuild=%s)...", self.collection_name, rebuild)
        
        # 真正的初始化逻辑 (包含网络请求)
        store = build_or_get_vector_store(
            self.collection_name,
            embed_model=self.embed_model,
            force_rebuild=rebuild,
            auto_ingest=False
        )
        
        # 🟢 3. 更新缓存
        _VECTOR_STORE_CACHE[self.collection_name] = store
        self._vector_store = store
        
        return self._vector_store

    def reload(self, force_rebuild: bool = False) -> Chroma:
        """
        显式重新加载/重建集合。
        """
        # 🟢 4. 清理缓存 (Cache Invalidation)
        if self.collection_name in _VECTOR_STORE_CACHE:
            logger.info(f"正在清理集合缓存: {self.collection_name}")
            del _VECTOR_STORE_CACHE[self.collection_name]
        
        self._vector_store = None
        return self.ensure_collection(rebuild=force_rebuild)

    def as_retriever(self, search_kwargs: Optional[Dict[str, Any]] = None) -> BaseRetriever:
        """
        暴露 LangChain Retriever。
        """
        kwargs = {"search_kwargs": {"k": self.default_top_k}}
        if search_kwargs:
            # deep merge search_kwargs
            if "filter" in search_kwargs:
                kwargs["search_kwargs"]["filter"] = search_kwargs["filter"]
            if "k" in search_kwargs:
                kwargs["search_kwargs"]["k"] = search_kwargs["k"]
            # Handle other potential kwargs
            for k, v in search_kwargs.items():
                 if k not in ["filter", "k"]:
                     kwargs["search_kwargs"][k] = v
                     
        return self.vector_store.as_retriever(**kwargs)

    def stats(self) -> Dict[str, Any]:
        """
        返回集合统计信息用于监控。
        """
        try:
            chroma_collection = self.vector_store._collection
            chunk_count = chroma_collection.count()
            metadata_fields: Dict[str, Any] = {}

            if chunk_count > 0:
                # 优化: limit=1 减少传输
                snapshot = chroma_collection.get(limit=1, include=["metadatas"])
                metadatas = snapshot.get("metadatas")
                if metadatas and len(metadatas) > 0:
                    first_item = metadatas[0]
                    if first_item:
                        metadata_fields = dict(first_item)

            return {
                "collection_name": self.collection_name,
                "chunk_count": chunk_count,
                "metadata_fields": list(metadata_fields.keys()),
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"error": str(e)}

    def delete_vectors(self, ids: List[str]) -> bool:
        """
        根据 Chroma ID 列表从向量库中批量删除切片。
        """
        if not ids:
            return True
        
        logger.info("正在从 Chroma 集合 %s 删除 %s 个向量...", self.collection_name, len(ids))
        try:
            self.vector_store._collection.delete(ids=ids)
            logger.info("Chroma 向量删除成功。")
            return True
        except Exception as e:
            logger.error(f"从 Chroma 删除向量失败: {e}", exc_info=True)
            raise