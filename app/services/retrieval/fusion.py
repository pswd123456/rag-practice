import logging
from typing import List, Dict, Any
from langchain_core.documents import Document
from langfuse import observe
# 初始化 Logger
logger = logging.getLogger(__name__)

@observe
def rrf_fusion(
    list_of_list_docs: List[List[Document]], 
    k: int = 60, 
    weights: List[float] = None
) -> List[Document]:
    """
    倒数排名融合 (Reciprocal Rank Fusion)
    :param list_of_list_docs: 多个检索结果列表 (e.g. [vector_docs, keyword_docs])
    :param k: 平滑常数，通常 60
    :param weights: 可选，为不同路赋予权重 (e.g. [1.0, 0.5] 让向量更重要)
    """
    if not list_of_list_docs:
        logger.warning("RRF Fusion received empty input lists.")
        return []

    if weights is None:
        weights = [1.0] * len(list_of_list_docs)
    
    # [Log] 记录输入的各路召回数量
    input_stats = [len(docs) for docs in list_of_list_docs]
    logger.debug(f"Starting RRF Fusion. Input streams: {len(list_of_list_docs)} | Doc counts: {input_stats} | Weights: {weights}")

    # 1. 聚合分数
    # 格式: {doc_identifier: {"score": float, "doc": Document}}
    fused_scores: Dict[str, Dict[str, Any]] = {}

    for i, (docs, weight) in enumerate(zip(list_of_list_docs, weights)):
        for rank, doc in enumerate(docs):
            # 兼容：优先使用 metadata 中的 id (由 ES/DB 保证唯一)，其次使用 page_content
            # 注意：使用 page_content 做 key 存在风险（不同文档内容可能相同），但在 RAG 切片场景下通常可接受
            doc_id = str(doc.metadata.get("id") or doc.metadata.get("doc_id"))
            
            # 如果完全没有 ID，回退到 content hash 或原内容 (主要用于日志警告)
            if not doc_id or doc_id == "None":
                # 仅在 debug 模式下警告，避免刷屏
                logger.debug(f"Document missing ID in stream {i}, ranking {rank}. Using content hash/preview.")
                doc_id = str(hash(doc.page_content))
            
            if doc_id not in fused_scores:
                fused_scores[doc_id] = {"score": 0.0, "doc": doc}
            
            # RRF 公式: weight * (1 / (k + rank))
            # rank 从 0 开始，所以 +1
            # k = 60 weight = 1 的配置scores 范围为 [0, 0.033]
            score_increment = weight * (1 / (k + rank + 1))
            fused_scores[doc_id]["score"] += score_increment

    # 2. 排序
    sorted_results = sorted(
        fused_scores.values(), 
        key=lambda x: x["score"], 
        reverse=True
    )

    # 3. 还原为 Document 列表
    final_docs = [item["doc"] for item in sorted_results]
    
    # [Log] 记录融合结果
    logger.info(
        f"RRF Fusion completed. "
        f"Merged {sum(input_stats)} docs from {len(list_of_list_docs)} streams into {len(final_docs)} unique docs. "
        f"Top score: {sorted_results[0]['score']:.4f}" if sorted_results else "No results."
    )

    return final_docs