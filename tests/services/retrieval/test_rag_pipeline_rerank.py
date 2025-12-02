# tests/services/test_rag_pipeline_rerank.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from app.services.pipelines.rag_pipeline import RAGPipeline
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.rerank.rerank_service import RerankService
from app.services.generation.qa_service import QAService

@pytest.mark.asyncio
async def test_rag_pipeline_with_rerank_flow():
    """
    [Integration] 测试 RAG Pipeline 集成 Rerank 流程:
    Recall (50) -> Rerank (3) -> Generation
    """
    # 1. Mock RetrievalService (Recall Stage)
    mock_recall_docs = [
        Document(page_content="Doc 1 (Noise)", metadata={"id": 1}),
        Document(page_content="Doc 2 (Answer)", metadata={"id": 2}),
        Document(page_content="Doc 3 (Noise)", metadata={"id": 3}),
        Document(page_content="Doc 4 (Context)", metadata={"id": 4}),
        Document(page_content="Doc 5 (Noise)", metadata={"id": 5}),
    ]
    mock_retriever_svc = MagicMock(spec=RetrievalService)
    mock_retriever_svc.afetch = AsyncMock(return_value=mock_recall_docs)

    # 2. Mock RerankService (Precision Stage)
    mock_reranked_docs = [
        Document(page_content="Doc 2 (Answer)", metadata={"id": 2, "rerank_score": 0.9}),
        Document(page_content="Doc 4 (Context)", metadata={"id": 4, "rerank_score": 0.8}),
    ]
    mock_rerank_svc = MagicMock(spec=RerankService)
    mock_rerank_svc.rerank_documents = AsyncMock(return_value=mock_reranked_docs)

    # 3. Mock QAService (Generation Stage)
    mock_qa_svc = MagicMock(spec=QAService)
    # 🟢 [FIX] 必须 Mock chain 属性，因为 RAGPipeline.__init__ 会访问它
    mock_qa_svc.chain = MagicMock() 
    mock_qa_svc.ainvoke = AsyncMock(return_value="Final Answer")

    # 4. 构建 Pipeline
    pipeline = RAGPipeline(
        retrieval_service=mock_retriever_svc,
        qa_service=mock_qa_svc,
        rerank_service=mock_rerank_svc
    )

    # 5. 执行查询 (请求 Top 2)
    query = "test query"
    answer, final_docs = await pipeline.async_query(query, top_k=2)

    # 6. 验证流程
    mock_retriever_svc.afetch.assert_called_once()
    
    mock_rerank_svc.rerank_documents.assert_called_once()
    call_args = mock_rerank_svc.rerank_documents.call_args
    assert call_args.kwargs['query'] == query
    assert call_args.kwargs['docs'] == mock_recall_docs 
    assert call_args.kwargs['top_n'] == 2              
    
    # 验证 Generation 接收到的 Context
    gen_call_inputs = mock_qa_svc.ainvoke.call_args[0][0]
    context = gen_call_inputs["context"]
    assert "Doc 2 (Answer)" in context
    assert "Doc 4 (Context)" in context
    assert "Doc 1 (Noise)" not in context 
    
    assert answer == "Final Answer"
    assert len(final_docs) == 2