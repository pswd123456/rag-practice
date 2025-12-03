import logging
from typing import List, Optional, Dict, Any
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.retrieval.fusion import rrf_fusion

# 初始化 Logger
logger = logging.getLogger(__name__)

class ESHybridRetriever(BaseRetriever):
    """
    应用层实现的混合检索器 (Vector + BM25 + RRF)
    支持多知识库（多索引）检索。
    """
    store_manager: VectorStoreManager
    top_k: int = 4
    knowledge_ids: Optional[List[int]] = None # [Change] 支持 ID 列表

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        
        logger.info(f"Hybrid Retrieval started. Query: '{query[:50]}...' | TopK: {self.top_k} | KB_IDs: {self.knowledge_ids}")

        try:
            # 1. 获取底层的 ElasticsearchStore 和 Client
            client = self.store_manager.client
            index_name = self.store_manager.index_name
            embed_model = self.store_manager.embed_model
            
            # 2. 构造 Filter
            # ES 的 terms 查询支持列表: {"terms": {"metadata.knowledge_id": [1, 2]}}
            filter_clause = []
            if self.knowledge_ids:
                filter_clause.append({"terms": {"metadata.knowledge_id": self.knowledge_ids}})
            
            if filter_clause:
                logger.debug(f"Applied filters: {filter_clause}")

            # -------------------------------------------------------
            # A. 向量检索 (Vector Search / KNN)
            # -------------------------------------------------------
            query_vector = embed_model.embed_query(query)
            vector_body = {
                "knn": {
                    "field": "vector",
                    "query_vector": query_vector,
                    "k": self.top_k,
                    "num_candidates": max(50, self.top_k * 10),
                    "filter": filter_clause 
                },
                "_source": ["text", "metadata"] 
            }
            
            logger.debug(f"Executing ES Vector Search on index: {index_name}")
            # index_name 可能包含逗号 (e.g. "rag_kb_1,rag_kb_2")，ES Client 原生支持
            res_vec = client.search(index=index_name, body=vector_body)
            vec_docs = self._parse_es_response(res_vec)
            
            logger.info(f"Vector Branch returned {len(vec_docs)} docs.")

            # -------------------------------------------------------
            # B. 关键词检索 (BM25)
            # -------------------------------------------------------
            keyword_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "text": {
                                        "query": query,
                                        "analyzer": "ik_smart"
                                    }
                                }
                            }
                        ],
                        "filter": filter_clause
                    }
                },
                "size": self.top_k,
                "_source": ["text", "metadata"]
            }
            
            logger.debug(f"Executing ES Keyword Search on index: {index_name}")
            res_kw = client.search(index=index_name, body=keyword_body)
            kw_docs = self._parse_es_response(res_kw)
            
            logger.info(f"Keyword Branch returned {len(kw_docs)} docs.")

            # -------------------------------------------------------
            # C. RRF 融合
            # -------------------------------------------------------
            final_docs = rrf_fusion([vec_docs, kw_docs], k=60, weights=[1.0, 1.0])
            
            result = final_docs[:self.top_k]
            
            logger.info(f"Hybrid Retrieval completed. Final result count: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"Hybrid Retrieval Failed: {e}", exc_info=True)
            raise e

    def _parse_es_response(self, res: dict) -> List[Document]:
        docs = []
        hits = res.get("hits", {}).get("hits", [])
        
        for hit in hits:
            source = hit["_source"]
            metadata = source.get("metadata", {})
            
            if "id" not in metadata:
                 metadata["id"] = hit["_id"]
            
            metadata["_es_score"] = hit.get("_score")
            # 记录来源索引名，方便调试
            metadata["_es_index"] = hit.get("_index")

            docs.append(Document(
                page_content=source.get("text", ""),
                metadata=metadata
            ))
        return docs