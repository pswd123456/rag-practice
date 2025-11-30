# tests/services/test_rerank_service.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.documents import Document
from app.services.rerank.rerank_service import RerankService

@pytest.fixture
def mock_documents():
    return [
        Document(page_content="Doc A (Low Relevance)", metadata={"id": 1}),
        Document(page_content="Doc B (High Relevance)", metadata={"id": 2}),
        Document(page_content="Doc C (Medium Relevance)", metadata={"id": 3}),
    ]

@pytest.mark.asyncio
async def test_rerank_success(mock_documents):
    """
    [Unit] 测试 Rerank 成功场景：文档应根据分数重新排序
    """
    # 1. 模拟 TEI API 返回 (Doc B > Doc C > Doc A)
    # TEI 返回格式: List[dict] -> [{"index": 1, "score": 0.99}, ...]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"index": 1, "score": 0.99}, # Doc B
        {"index": 2, "score": 0.50}, # Doc C
        {"index": 0, "score": 0.01}, # Doc A
    ]

    # 2. Mock HTTPX Client
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        service = RerankService(base_url="http://mock-rerank", model_name="test-model")
        
        # 3. 执行 Rerank，取 Top 2
        reranked_docs = await service.rerank_documents(
            query="test", 
            docs=mock_documents, 
            top_n=2
        )
        
        # 4. 验证结果
        assert len(reranked_docs) == 2
        assert reranked_docs[0].page_content == "Doc B (High Relevance)" # 分数最高
        assert reranked_docs[1].page_content == "Doc C (Medium Relevance)" # 分数第二
        assert reranked_docs[0].metadata["rerank_score"] == 0.99
        
        # 验证调用参数
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["query"] == "test"
        assert len(payload["texts"]) == 3

@pytest.mark.asyncio
async def test_rerank_failure_fallback(mock_documents):
    """
    [Unit] 测试降级机制：如果 API 失败，应返回原始顺序的切片
    """
    # 1. 模拟 API 抛出异常
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection Refused")):
        service = RerankService(base_url="http://mock-rerank", model_name="test-model")
        
        # 2. 执行 Rerank
        reranked_docs = await service.rerank_documents(
            query="test", 
            docs=mock_documents, 
            top_n=2
        )
        
        # 3. 验证降级结果 (保持原序，只截断)
        assert len(reranked_docs) == 2
        assert reranked_docs[0].page_content == "Doc A (Low Relevance)"
        assert reranked_docs[1].page_content == "Doc B (High Relevance)"