# app/services/retrieval/vector_store_manager.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from langchain_elasticsearch import ElasticsearchStore
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.services.retrieval.es_client import get_es_client

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """
    Elasticsearch 向量库管理器
    """

    def __init__(self, collection_name: str, embed_model: Embeddings):
        """
        :param collection_name: 对应 ES 中的 index_name。
                                如果包含逗号，则视为多索引查询模式。
        :param embed_model: LangChain Embeddings 实例
        """
        self.raw_collection_name = collection_name
        self.embed_model = embed_model
        self.client = get_es_client()
        
        # 处理多索引情况 (e.g., "kb_1,kb_2")
        if "," in collection_name:
            # 拼接完整索引名: rag_kb_1,rag_kb_2
            names = collection_name.split(",")
            self.index_name = ",".join([f"{settings.ES_INDEX_PREFIX}_{n}".lower() for n in names])
            self.is_multi_index = True
        else:
            self.index_name = f"{settings.ES_INDEX_PREFIX}_{collection_name}".lower()
            self.is_multi_index = False

    def get_vector_store(self) -> ElasticsearchStore:
        """
        获取 LangChain 的 ElasticsearchStore 实例 (Lazy Load)
        """
        # 仅在单索引且非查询模式下尝试创建索引
        # 如果是多索引查询，假设索引已存在
        if not self.is_multi_index:
            self.ensure_index()

        return ElasticsearchStore(
            es_connection=self.client,
            index_name=self.index_name,
            embedding=self.embed_model,
            query_field="text",
            vector_query_field="vector",
            distance_strategy="COSINE" 
        )

    def ensure_index(self) -> None:
        """
        核心方法：检查索引是否存在，不存在则创建并应用 IK 分词和向量 Mapping。
        注意：多索引模式下不执行此操作。
        """
        if self.is_multi_index:
            return

        if self.client.indices.exists(index=self.index_name):
            return

        logger.info(f"正在创建 Elasticsearch 索引: {self.index_name}")
        
        mapping_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "text": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart"
                    },
                    "vector": {
                        "type": "dense_vector",
                        "dims": settings.EMBEDDING_DIM,
                        "index": True,
                        "similarity": "cosine"
                    },
                    "metadata": {
                        "type": "object",
                        "dynamic": True
                    }
                }
            }
        }

        try:
            self.client.indices.create(index=self.index_name, body=mapping_body)
            logger.info(f"索引 {self.index_name} 创建成功。")
        except Exception as e:
            logger.error(f"创建索引 {self.index_name} 失败: {e}")
            raise e

    def delete_index(self) -> bool:
        """
        删除整个索引 (用于知识库删除)
        """
        if self.is_multi_index:
            logger.warning("尝试删除多重索引引用，操作已忽略。")
            return False

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
        if self.is_multi_index:
            return False
            
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