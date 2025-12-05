import logging
import httpx
from typing import List
from langchain_core.documents import Document
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
        
        # 1. 构造请求 Payload
        # TEI API 格式: POST /rerank
        # {"query": "...", "texts": ["...", "..."], "truncate": true}
        texts = [d.page_content for d in docs]
        
        payload = {
            "query": query,
            "texts": texts,
            "truncate": True,  # 自动截断超长文本，防止报错
            # "model_id": self.model_name # TEI 单模型部署时通常不需要
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/rerank", 
                    json=payload
                )
                response.raise_for_status()
                
                # 2. 解析响应
                # 格式: [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.1}, ...]
                results = response.json()
                
                # 3. 排序逻辑
                # 虽然 TEI 通常已经排好序返回，但显式再排一次更安全
                results.sort(key=lambda x: x["score"], reverse=True)
                
                reranked_docs = []
                for item in results:
                    score = item["score"]
                    if score < target_threshold:
                        continue # 跳过低分文档

                    original_index = item["index"]
                    doc = docs[original_index]
                    doc.metadata["rerank_score"] = score
                    reranked_docs.append(doc)
                
                # 4. 截断返回
                final_docs = reranked_docs[:top_n]
                
                logger.info(f"Rerank 成功: 输入 {len(docs)} -> 输出 {len(final_docs)} (Top Score: {results[0]['score']:.4f})")
                return final_docs

        except Exception as e:
            logger.error(f"❌ Rerank 服务调用失败，降级为原始顺序: {e}")
            # 降级策略：返回原始列表的前 N 个
            return docs[:top_n]