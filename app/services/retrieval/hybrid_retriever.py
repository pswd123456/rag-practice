import logging
from typing import List, Optional, Dict, Any
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.retrieval.fusion import rrf_fusion, collapse_documents

from langfuse import observe 

logger = logging.getLogger(__name__)

class ESHybridRetriever(BaseRetriever):
    """
    应用层实现的混合检索器 (Vector + BM25 + RRF)
    支持多知识库（多索引）检索。
    支持 Parent-Child Indexing (Small-to-Big)
    """
    store_manager: VectorStoreManager
    top_k: int = 4
    knowledge_ids: Optional[List[int]] = None 
    rerank_service: Optional[Any] = None
    do_collapse: bool = True # [New] 控制是否执行父文档折叠

    @observe(name="es_search_execution", as_type="span")
    def _execute_es_search(self, client, index_name: str, body: Dict[str, Any], search_type: str) -> Dict[str, Any]:
        """
        执行 ES 搜索并被 Langfuse 追踪。
        """
        response = client.search(index=index_name, body=body)
        return response.body if hasattr(response, 'body') else response

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        
        logger.info(f"Hybrid Retrieval started. Query: '{query[:50]}...' (Collapse: {self.do_collapse})")

        try:
            client = self.store_manager.client
            index_name = self.store_manager.index_name
            embed_model = self.store_manager.embed_model
            
            # Filter
            filter_clause = []
            if self.knowledge_ids:
                filter_clause.append({"terms": {"metadata.knowledge_id": self.knowledge_ids}})
            
            # [Optimization] _source filtering
            source_filter = {
                "includes": ["metadata.parent_content", "metadata.parent_id", "metadata.source", "metadata.page_number", "metadata.knowledge_id", "text"],
                "excludes": ["vector"] 
            }

            # -------------------------------------------------------
            # A. 向量检索 (Vector Search / KNN)
            # -------------------------------------------------------
            recall_k = max(50, self.top_k * 10)
            
            query_vector = embed_model.embed_query(query)
            vector_body = {
                "knn": {
                    "field": "vector",
                    "query_vector": query_vector,
                    "k": recall_k, 
                    "num_candidates": recall_k * 2,
                    "filter": filter_clause 
                },
                "_source": source_filter
            }
            
            res_vec = self._execute_es_search(client, index_name, vector_body, "vector")
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
                                        "analyzer": "ik_smart"
                                    }
                                }
                            }
                        ],
                        "filter": filter_clause
                    }
                },
                "size": recall_k,
                "_source": source_filter
            }
            
            res_kw = self._execute_es_search(client, index_name, keyword_body, "keyword")
            kw_docs = self._parse_es_response(res_kw)

            # -------------------------------------------------------
            # C. RRF 融合
            # -------------------------------------------------------
            fused_child_docs = rrf_fusion([vec_docs, kw_docs], k=60)
            
            # -------------------------------------------------------
            # D. [Collapse] 聚合去重 (Traced) - Conditional
            # -------------------------------------------------------
            if self.do_collapse:
                # 仅在需要时折叠 (传统模式)
                # 使用 top_k * 2 作为安全边界
                result = collapse_documents(fused_child_docs, top_k=self.top_k * 2)
                logger.info(f"Hybrid Retrieval (w/ Collapse) completed. Merged to {len(result)} parent docs.")
                return result
            else:
                # 不折叠，直接返回 Child Chunks (Small-to-Big 模式)
                logger.info(f"Hybrid Retrieval (No Collapse) completed. Returning {len(fused_child_docs)} child docs.")
                return fused_child_docs

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
                
                docs.append(Document(
                    page_content=source.get("text", ""), 
                    metadata=metadata
                ))
            return docs