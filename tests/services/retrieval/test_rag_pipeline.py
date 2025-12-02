# tests/test_rag_pipeline.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from app.services.pipelines.rag_pipeline import RAGPipeline
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.generation.qa_service import QAService
# 🟢 [FIX] 引入 RerankService 用于 spec
from app.services.rerank.rerank_service import RerankService

@pytest.mark.asyncio
async def test_rag_pipeline_async_flow():
    """
    测试 RAG Pipeline 的完整异步调用流程：
    Input -> Retrieval -> Rerank (Passthrough) -> Context Injection -> Generation -> Output
    """
    # 1. Mock RetrievalService
    mock_retriever_svc = MagicMock(spec=RetrievalService)
    mock_docs = [
        Document(page_content="Context A", metadata={"id": 1}),
        Document(page_content="Context B", metadata={"id": 2})
    ]
    mock_retriever_svc.fetch.return_value = mock_docs
    mock_retriever_svc.afetch = AsyncMock(return_value=mock_docs)

    # 2. Mock QAService
    mock_qa_svc = MagicMock(spec=QAService)
    mock_chain = MagicMock()
    mock_qa_svc.chain = mock_chain
    mock_qa_svc.invoke.return_value = "Sync Answer"
    mock_qa_svc.ainvoke = AsyncMock(return_value="Async Answer")

    # 🟢 [FIX] 3. Mock RerankService
    mock_rerank_svc = MagicMock(spec=RerankService)
    # 模拟 Rerank 直接返回原文档 (透传)
    mock_rerank_svc.rerank_documents = AsyncMock(return_value=mock_docs)

    # 4. 构建 Pipeline
    pipeline = RAGPipeline(
        retrieval_service=mock_retriever_svc,
        qa_service=mock_qa_svc,
        rerank_service=mock_rerank_svc # 🟢 [FIX] 传入参数
    )

    # 5. 执行异步查询
    user_query = "What is X?"
    answer, docs = await pipeline.async_query(question=user_query)

    # 6. 验证断言
    assert answer == "Async Answer"
    assert len(docs) == 2
    assert docs[0].page_content == "Context A"

    # 验证 RetrievalService 被调用
    mock_retriever_svc.afetch.assert_called_once()
    
    # 🟢 [FIX] 验证 RerankService 被调用
    mock_rerank_svc.rerank_documents.assert_called_once()

    # 验证 QAService 接收到的输入
    call_inputs = mock_qa_svc.ainvoke.call_args[0][0]
    assert call_inputs["question"] == user_query
    assert "Context A" in call_inputs["context"]
    assert "Context B" in call_inputs["context"]

def test_format_docs_logic():
    """
    单元测试：文档格式化逻辑
    """
    # 🟢 [FIX] 补充第3个参数 Mock
    pipeline = RAGPipeline(MagicMock(), MagicMock(), MagicMock())
    
    docs = [
        Document(page_content="Part 1"),
        Document(page_content="Part 2")
    ]
    
    formatted = pipeline._format_docs(docs)
    assert formatted == "Part 1\n\nPart 2"