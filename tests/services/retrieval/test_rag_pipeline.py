# tests/services/retrieval/test_rag_pipeline.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from app.services.pipelines.rag_pipeline import RAGPipeline
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.generation.qa_service import QAService
from app.services.rerank.rerank_service import RerankService

@pytest.mark.asyncio
async def test_rag_pipeline_async_flow():
    """
    测试 RAG Pipeline 的完整异步调用流程
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
    # 注意：QAService 中 invoke 已被移除/废弃，因此 spec=QAService 时不能访问 .invoke
    mock_qa_svc = MagicMock(spec=QAService)
    
    # 🟢 [FIX] 显式 Mock chain 属性，并在 chain 上支持 __or__ (位运算)
    # 因为 RAGPipeline 初始化时会执行: self.rag_chain = ({...} | self.qa_service.chain)
    mock_chain = MagicMock()
    mock_qa_svc.chain = mock_chain
    
    # Mock 异步生成方法
    mock_qa_svc.ainvoke = AsyncMock(return_value="Async Answer")

    # 3. Mock RerankService
    mock_rerank_svc = MagicMock(spec=RerankService)
    mock_rerank_svc.rerank_documents = AsyncMock(return_value=mock_docs)

    # 4. 构建 Pipeline
    pipeline = RAGPipeline(
        retrieval_service=mock_retriever_svc,
        qa_service=mock_qa_svc,
        rerank_service=mock_rerank_svc
    )

    # 5. 执行异步查询
    user_query = "What is X?"
    answer, docs = await pipeline.async_query(question=user_query)

    # 6. 验证
    assert answer == "Async Answer"
    assert len(docs) == 2
    mock_retriever_svc.afetch.assert_called_once()
    mock_rerank_svc.rerank_documents.assert_called_once()

    # 验证 QAService 接收到的输入
    call_inputs = mock_qa_svc.ainvoke.call_args[0][0]
    assert call_inputs["question"] == user_query

def test_format_docs_logic():
    # 构造 dummy mock 即可
    pipeline = RAGPipeline(MagicMock(), MagicMock(), MagicMock()) 
    docs = [Document(page_content="Part 1"), Document(page_content="Part 2")]
    formatted = pipeline._format_docs(docs)
    assert formatted == "Part 1\n\nPart 2"