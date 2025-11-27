from typing import List, Dict, Any
from langchain_core.documents import Document

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
    if weights is None:
        weights = [1.0] * len(list_of_list_docs)
    
    # 1. 聚合分数
    # 格式: {doc_content: {"score": float, "doc": Document}}
    # 注意：这里假设 page_content 是唯一的，更严谨应该用 doc_id 或 hash
    fused_scores = {}

    for docs, weight in zip(list_of_list_docs, weights):
        for rank, doc in enumerate(docs):
            # 兼容：有些 doc 可能没有 id，用内容做 key，或者 metadata 中的 id
            doc_id = doc.metadata.get("id") or doc.page_content
            
            if doc_id not in fused_scores:
                fused_scores[doc_id] = {"score": 0.0, "doc": doc}
            
            # RRF 公式: weight * (1 / (k + rank))
            # rank 从 0 开始，所以 +1
            fused_scores[doc_id]["score"] += weight * (1 / (k + rank + 1))

    # 2. 排序
    sorted_results = sorted(
        fused_scores.values(), 
        key=lambda x: x["score"], 
        reverse=True
    )

    # 3. 还原为 Document 列表
    return [item["doc"] for item in sorted_results]