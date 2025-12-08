import logging
from typing import List, Optional, Dict, Any
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.retrieval.fusion import rrf_fusion

from langfuse import observe
# 初始化 Logger
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
    rerank_service: Optional[Any] = None # 用于 Pipeline 可能需要的引用，Retriever 本身主要做 Recall

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
        
        logger.info(f"Hybrid Retrieval started. Query: '{query[:50]}...'")

        try:
            client = self.store_manager.client
            index_name = self.store_manager.index_name
            embed_model = self.store_manager.embed_model
            
            # Filter
            filter_clause = []
            if self.knowledge_ids:
                filter_clause.append({"terms": {"metadata.knowledge_id": self.knowledge_ids}})
            
            # [Optimization] _source filtering
            # 只需要 Parent 内容和 ID 用于折叠，不需要 Child 的 text 和 vector
            source_filter = {
                "includes": ["metadata.parent_content", "metadata.parent_id", "metadata.source", "metadata.page_number", "metadata.knowledge_id", "text"],
                "excludes": ["vector"] 
            }

            # -------------------------------------------------------
            # A. 向量检索 (Vector Search / KNN) - 针对 Child Chunk
            # -------------------------------------------------------
            # 扩大召回数量以便折叠 (e.g. top_k * 5)
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
            # B. 关键词检索 (BM25) - 针对 Child Chunk
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
            # C. RRF 融合 (针对 Child 进行打分)
            # -------------------------------------------------------
            fused_child_docs = rrf_fusion([vec_docs, kw_docs], k=60)
            
            # -------------------------------------------------------
            # D. [Collapse] 聚合去重：将 Child 折叠为 Parent
            # -------------------------------------------------------
            seen_parent_ids = set()
            unique_parent_docs = []
            
            for doc in fused_child_docs:
                parent_id = doc.metadata.get("parent_id")
                parent_content = doc.metadata.get("parent_content")
                
                # 如果没有 parent info，直接使用 child 本身
                if not parent_id:
                    # 使用 doc_id 或 content hash 防止重复
                    doc_id = doc.metadata.get("doc_id") or str(hash(doc.page_content))
                    if doc_id not in seen_parent_ids:
                        seen_parent_ids.add(doc_id)
                        unique_parent_docs.append(doc)
                    continue
                
                # 核心折叠逻辑
                if parent_id in seen_parent_ids:
                    continue # 跳过该 Parent 的其他 Child
                
                seen_parent_ids.add(parent_id)
                
                # 构造新的 Document，内容替换为 Parent Content
                # 保留其他元数据 (如 source, page_number) 供引用显示
                # 注意：score 是 Child 的最高分，这正好代表了该 Parent 最相关的程度
                new_doc = Document(
                    page_content=parent_content,
                    metadata=doc.metadata.copy()
                )
                # 清理 metadata，避免日志过大，且 parent_content 已经移到 page_content 了
                new_doc.metadata.pop("parent_content", None)
                
                unique_parent_docs.append(new_doc)
                
                if len(unique_parent_docs) >= self.top_k * 2: # 稍微多保留一点给 Rerank
                    break

            result = unique_parent_docs
            
            logger.info(f"Hybrid Retrieval (w/ Collapse) completed. Merged to {len(result)} parent docs.")
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
            
            # Flatten parent_content if it exists in metadata (for easier access)
            # In ES mapping, parent_content is inside metadata object
            
            # ES _source returns: {"text": "...", "metadata": {"parent_id": "...", "parent_content": "..."}}
            # So it is already in metadata dict.
            
            metadata["_es_score"] = hit.get("_score")
            
            docs.append(Document(
                page_content=source.get("text", ""), # Child text
                metadata=metadata
            ))
        return docs