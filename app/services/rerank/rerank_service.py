import logging
import httpx
from typing import List
from langchain_core.documents import Document
from langfuse import observe, get_client # 🟢 v3 Import
from app.core.config import settings

logger = logging.getLogger(__name__)

class RerankService:
    """
    Rerank 服务客户端
    封装对本地 TEI (Text Embeddings Inference) 容器的调用。
    """
    
    def __init__(self, base_url: str, model_name: str):
        """
        :param base_url: TEI 服务的 Base URL (e.g. http://rerank-service:80)
        :param model_name: 模型名称 (用于日志或多模型场景)
        """
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        # 设置合理的超时时间，Rerank 计算量大，建议 10s 以上
        self.timeout = httpx.Timeout(30.0, connect=2.0)

    @observe(name="rerank_documents", as_type="generation")
    async def rerank_documents(
        self, 
        query: str, 
        docs: List[Document], 
        top_n: int,
        threshold: float = None
    ) -> List[Document]:
        """
        对文档列表进行重排序。
        
        :param query: 用户查询
        :param docs: 候选文档列表
        :param top_n: 返回前 N 个文档
        :return: 排序后的文档列表
        """
        if not docs:
            return []
        
        target_threshold = threshold if threshold is not None else settings.RERANK_THRESHOLD
        
        try:
            langfuse = get_client()
           
            langfuse.update_current_span(
                input={"query": query, "doc_count": len(docs)},
                metadata={"top_n": top_n, "threshold": target_threshold}
            )
        except Exception as e:
            logger.warning(f"Langfuse update failed: {e}")

        # 1. 构造请求 Payload
        texts = [d.page_content for d in docs]
        
        payload = {
            "query": query,
            "texts": texts,
            "truncate": True,  
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/rerank", 
                    json=payload
                )
                response.raise_for_status()
                
                results = response.json()
                results.sort(key=lambda x: x["score"], reverse=True)
                
                reranked_docs = []
                for item in results:
                    score = item["score"]
                    if score < target_threshold:
                        continue 

                    original_index = item["index"]
                    doc = docs[original_index]
                    doc.metadata["rerank_score"] = score
                    reranked_docs.append(doc)
                
                final_docs = reranked_docs[:top_n]
                
                logger.info(f"Rerank 成功: 输入 {len(docs)} -> 输出 {len(final_docs)} (Top Score: {results[0]['score']:.4f})")
                
                try:
                    langfuse.update_current_span(
                        output={"final_count": len(final_docs), "top_score": results[0]['score'] if results else 0}
                    )
                except Exception:
                    pass
                
                return final_docs

        except Exception as e:
            logger.error(f"❌ Rerank 服务调用失败，降级为原始顺序: {e}")
            return docs[:top_n]