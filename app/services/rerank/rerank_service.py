import logging
import httpx
import asyncio
from typing import List, Dict, Any
from langchain_core.documents import Document
from langfuse import observe, get_client 
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
        # 设置合理的超时时间，Rerank 计算量大，建议 60s 以上
        self.timeout = httpx.Timeout(60.0, connect=5.0)
        # [Fix] 设置客户端分批大小，建议小于服务端限制 (64)，例如 32
        self.batch_size = 32

    async def _process_batch(self, query: str, batch_texts: List[str], start_index: int) -> List[Dict[str, Any]]:
        """
        处理单个批次的 Rerank 请求
        返回: [{"index": global_index, "score": float}, ...]
        """
        if not batch_texts:
            return []
            
        payload = {
            "query": query,
            "texts": batch_texts,
            "truncate": True,
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/rerank", 
                json=payload
            )
            response.raise_for_status()
            batch_results = response.json()
            
            # 将批次内的相对索引转换为全局索引
            mapped_results = []
            for item in batch_results:
                mapped_results.append({
                    "index": item["index"] + start_index,
                    "score": item["score"]
                })
            return mapped_results

    @observe(name="rerank_documents", as_type="generation")
    async def rerank_documents(
        self, 
        query: str, 
        docs: List[Document], 
        top_n: int,
        threshold: float = None
    ) -> List[Document]:
        """
        对文档列表进行重排序 (支持自动分批)。
        """
        if not docs:
            return []
        
        target_threshold = threshold if threshold is not None else settings.RERANK_THRESHOLD
        
        try:
            # Langfuse Logging
            langfuse = get_client()
            langfuse.update_current_span(
                input={"query": query, "doc_count": len(docs)},
                metadata={"top_n": top_n, "threshold": target_threshold}
            )
        except Exception as e:
            logger.warning(f"Langfuse update failed: {e}")

        # 1. 准备文本列表
        all_texts = [d.page_content for d in docs]
        all_results = []

        try:
            # 2. 分批处理 (Batch Processing)
            tasks = []
            total_docs = len(all_texts)
            
            # 切分批次
            for i in range(0, total_docs, self.batch_size):
                batch_texts = all_texts[i : i + self.batch_size]
                # 创建异步任务
                tasks.append(self._process_batch(query, batch_texts, start_index=i))
            
            if len(tasks) > 1:
                logger.info(f"Rerank 数量 ({total_docs}) 较大，拆分为 {len(tasks)} 个批次并行处理...")
            
            # 并行执行所有批次
            batch_outputs = await asyncio.gather(*tasks)
            
            # 3. 合并结果
            for batch_out in batch_outputs:
                all_results.extend(batch_out)

            # 4. 排序与截断
            # 根据分数降序
            all_results.sort(key=lambda x: x["score"], reverse=True)
            
            reranked_docs = []
            for item in all_results:
                score = item["score"]
                if score < target_threshold:
                    continue 

                original_index = item["index"]
                doc = docs[original_index]
                # 注入分数
                doc.metadata["rerank_score"] = score
                reranked_docs.append(doc)
            
            final_docs = reranked_docs[:top_n]
            
            top_score = all_results[0]['score'] if all_results else 0
            logger.info(f"Rerank 成功: 输入 {len(docs)} -> 输出 {len(final_docs)} (Top Score: {top_score:.4f})")
            
            try:
                langfuse.update_current_span(
                    output={"final_count": len(final_docs), "top_score": top_score}
                )
            except Exception:
                pass
            
            return final_docs

        except Exception as e:
            logger.error(f"❌ Rerank 服务调用失败，降级为原始顺序: {e}", exc_info=True)
            # 降级策略：返回前 N 个，不排序
            return docs[:top_n]