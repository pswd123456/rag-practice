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
    完全兼容开源版 Elasticsearch。
    """
    store_manager: VectorStoreManager
    top_k: int = 4
    knowledge_id: Optional[int] = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        
        # [Log] 记录检索请求
        logger.info(f"Hybrid Retrieval started. Query: '{query[:50]}...' | TopK: {self.top_k} | KB_ID: {self.knowledge_id}")

        try:
            # 1. 获取底层的 ElasticsearchStore 和 Client
            client = self.store_manager.client
            index_name = self.store_manager.index_name
            embed_model = self.store_manager.embed_model
            
            # 2. 构造 Filter
            filter_clause = []
            if self.knowledge_id:
                filter_clause.append({"term": {"metadata.knowledge_id": self.knowledge_id}})
            
            # [Log] Debug Filter 结构
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
                    "k": self.top_k,# 现在有点太小了, 应用rerank后需要改成50~100
                    "num_candidates": max(50, self.top_k * 10), # HNSW的候选值
                    "filter": filter_clause 
                },
                "_source": ["text", "metadata"] 
            }
            
            # [Log] 记录开始向量检索
            logger.debug(f"Executing ES Vector Search on index: {index_name}")
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
                                        "analyzer": "ik_smart" # 查询时使用粗粒度
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
            
            # [Log] 记录开始关键词检索
            logger.debug(f"Executing ES Keyword Search on index: {index_name}")
            res_kw = client.search(index=index_name, body=keyword_body)
            kw_docs = self._parse_es_response(res_kw)
            
            logger.info(f"Keyword Branch returned {len(kw_docs)} docs.")

            # -------------------------------------------------------
            # C. RRF 融合
            # -------------------------------------------------------
            # 可以在这里调整权重，例如 vector=1.0, keyword=0.7
            final_docs = rrf_fusion([vec_docs, kw_docs], k=60, weights=[1.0, 1.0])
            
            # 截取最终的 Top K
            result = final_docs[:self.top_k]
            
            logger.info(f"Hybrid Retrieval completed. Final result count: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"Hybrid Retrieval Failed: {e}", exc_info=True)
            # 根据设计原则，Retriever 失败最好抛出异常让上层处理或降级，而不是返回空列表掩盖错误
            raise e

    def _parse_es_response(self, res: dict) -> List[Document]:
        docs = []
        hits = res.get("hits", {}).get("hits", [])
        
        for hit in hits:
            source = hit["_source"]
            metadata = source.get("metadata", {})
            
            # 必须把 _id 塞回去，因为 RRF 融合可能需要用 ID 去重
            if "id" not in metadata:
                 metadata["id"] = hit["_id"]
            
            # 保存 ES 的检索分数以供调试 (虽然 RRF 不直接用这个分数，但 Debug 很有用)
            metadata["_es_score"] = hit.get("_score")

            docs.append(Document(
                page_content=source.get("text", ""),
                metadata=metadata
            ))
        return docs