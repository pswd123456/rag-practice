# app/services/retrieval/vector_store_manager.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_elasticsearch import ElasticsearchStore
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from app.core.config import settings
from app.services.retrieval.es_client import get_es_client

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """
    Elasticsearch 向量库管理器
    负责索引的创建(Mapping配置)、获取和清理。
    """

    def __init__(self, collection_name: str, embed_model: Embeddings):
        """
        :param collection_name: 对应 ES 中的 index_name
        :param embed_model: LangChain Embeddings 实例
        """
        # 统一添加前缀，避免索引名冲突
        self.index_name = f"{settings.ES_INDEX_PREFIX}_{collection_name}".lower()
        self.embed_model = embed_model
        self.client = get_es_client()

    def get_vector_store(self) -> ElasticsearchStore:
        """
        获取 LangChain 的 ElasticsearchStore 实例 (Lazy Load)
        """
        # 确保索引存在（带正确的 Mapping）
        self.ensure_index()

        return ElasticsearchStore(
            es_connection=self.client,
            index_name=self.index_name,
            embedding=self.embed_model,
            # 指定存储文本和向量的字段名，需与 ensure_index 中的 Mapping 保持一致
            query_field="text",
            vector_query_field="vector",
            # 距离策略: COSINE, EUCLIDEAN, DOT_PRODUCT
            # 注意：这里仅影响 LangChain 内部的一些逻辑，核心约束在 ES Mapping 中
            distance_strategy="COSINE" 
        )

    def ensure_index(self) -> None:
        """
        核心方法：检查索引是否存在，不存在则创建并应用 IK 分词和向量 Mapping。
        """
        if self.client.indices.exists(index=self.index_name):
            # logger.debug(f"索引 {self.index_name} 已存在，跳过创建。")
            return

        logger.info(f"正在创建 Elasticsearch 索引: {self.index_name}")
        
        # -------------------------------------------------------
        # Mapping 定义 (关键)
        # -------------------------------------------------------
        mapping_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    # 1. 文本字段：配置 IK 分词器
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",      # 索引时：细粒度分词 (e.g. "我爱吃牛肉烧卖" -> "我", "爱吃", "牛肉烧卖"...)
                        "search_analyzer": "ik_smart"   # 查询时：粗粒度分词 (e.g. "我爱吃牛肉烧卖" -> "我爱吃牛肉烧卖")
                    },
                    # 2. 向量字段：配置 Dense Vector
                    "vector": {
                        "type": "dense_vector",
                        "dims": settings.EMBEDDING_DIM, # 必须与模型维度一致
                        "index": True,                  # 开启 HNSW 索引
                        "similarity": "cosine"          # 相似度算法: cosine, l2_norm, dot_product
                    },
                    # 3. 元数据字段：LangChain 默认将 metadata 放在 metadata 字段下
                    "metadata": {
                        "type": "object",
                        "dynamic": True
                    }
                }
            }
        }

        try:
            self.client.indices.create(index=self.index_name, body=mapping_body)
            logger.info(f"索引 {self.index_name} 创建成功 (Dim: {settings.EMBEDDING_DIM}, Analyzer: IK)。")
        except Exception as e:
            logger.error(f"创建索引 {self.index_name} 失败: {e}")
            raise e

    def delete_index(self) -> bool:
        """
        删除整个索引 (用于知识库删除)
        """
        if self.client.indices.exists(index=self.index_name):
            try:
                self.client.indices.delete(index=self.index_name)
                logger.info(f"索引 {self.index_name} 已删除。")
                return True
            except Exception as e:
                logger.error(f"删除索引失败: {e}")
                return False
        return True
     
    def delete_by_doc_id(self, doc_id: int) -> bool:
        """
        利用 delete_by_query 根据 metadata.doc_id 删除向量
        """
        query = {
            "query": {
                "term": {
                    "metadata.doc_id": doc_id
                }
            }
        }
        try:
            resp = self.client.delete_by_query(index=self.index_name, body=query)
            logger.info(f"已从 ES {self.index_name} 删除文档 {doc_id} 的切片。Deleted: {resp.get('deleted')}")
            return True
        except Exception as e:
            logger.error(f"删除文档向量失败: {e}")
            raise e