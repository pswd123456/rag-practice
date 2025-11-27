from typing import List, Optional
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.retrieval.fusion import rrf_fusion

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
        
        # 1. 获取底层的 ElasticsearchStore 和 Client
        # 我们不直接用 LangChain 的 search 接口，因为灵活性不够
        client = self.store_manager.client
        index_name = self.store_manager.index_name
        embed_model = self.store_manager.embed_model
        
        # 2. 构造 Filter
        filter_clause = []
        if self.knowledge_id:
            filter_clause.append({"term": {"metadata.knowledge_id": self.knowledge_id}})
        
        bool_filter = {"bool": {"filter": filter_clause}} if filter_clause else None

        # -------------------------------------------------------
        # A. 向量检索 (Vector Search / KNN)
        # -------------------------------------------------------
        query_vector = embed_model.embed_query(query)
        vector_body = {
            "knn": {
                "field": "vector",
                "query_vector": query_vector,
                "k": self.top_k,
                "num_candidates": self.top_k * 10,
                "filter": filter_clause # KNN 的 filter 写法略有不同，直接传 list
            },
            "_source": ["text", "metadata"] # 只取需要的字段
        }
        res_vec = client.search(index=index_name, body=vector_body)
        vec_docs = self._parse_es_response(res_vec)

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
        res_kw = client.search(index=index_name, body=keyword_body)
        kw_docs = self._parse_es_response(res_kw)

        # -------------------------------------------------------
        # C. RRF 融合
        # -------------------------------------------------------
        final_docs = rrf_fusion([vec_docs, kw_docs], k=60)
        
        # 截取最终的 Top K
        return final_docs[:self.top_k]

    def _parse_es_response(self, res: dict) -> List[Document]:
        docs = []
        for hit in res["hits"]["hits"]:
            source = hit["_source"]
            # 必须把 _id 塞回去，因为 RRF 融合可能需要用 ID 去重
            metadata = source.get("metadata", {})
            # 如果 metadata 里没有 id，我们就把 ES 的 _id 塞进去辅助去重
            if "id" not in metadata:
                 metadata["id"] = hit["_id"]
            
            docs.append(Document(
                page_content=source.get("text", ""),
                metadata=metadata
            ))
        return docs