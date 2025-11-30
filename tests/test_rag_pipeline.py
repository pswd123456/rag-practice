# tests/services/test_rag_pipeline.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from app.services.pipelines.rag_pipeline import RAGPipeline
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.generation.qa_service import QAService

@pytest.mark.asyncio
async def test_rag_pipeline_async_flow():
    """
    测试 RAG Pipeline 的完整异步调用流程：
    Input -> Retrieval -> Context Injection -> Generation -> Output
    """
    # 1. Mock RetrievalService
    mock_retriever_svc = MagicMock(spec=RetrievalService)
    # 模拟检索返回 2 个文档
    mock_docs = [
        Document(page_content="Context A", metadata={"id": 1}),
        Document(page_content="Context B", metadata={"id": 2})
    ]
    mock_retriever_svc.fetch.return_value = mock_docs
    mock_retriever_svc.afetch = AsyncMock(return_value=mock_docs)

    # 2. Mock QAService
    mock_qa_svc = MagicMock(spec=QAService)
    # Pipeline 初始化时需要获取 qa_service.chain
    # 这里我们 Mock chain 的 invoke/ainvoke
    mock_chain = MagicMock()
    mock_qa_svc.chain = mock_chain
    
    # 模拟 LLM 生成的答案
    mock_qa_svc.invoke.return_value = "Sync Answer"
    mock_qa_svc.ainvoke = AsyncMock(return_value="Async Answer")

    # 3. 构建 Pipeline (手动注入 Mock Service，不使用 Factory)
    pipeline = RAGPipeline(
        retrieval_service=mock_retriever_svc,
        qa_service=mock_qa_svc
    )

    # 4. 执行异步查询
    user_query = "What is X?"
    answer, docs = await pipeline.async_query(question=user_query)

    # 5. 验证断言
    assert answer == "Async Answer"
    assert len(docs) == 2
    assert docs[0].page_content == "Context A"

    # 验证 RetrievalService 被调用
    mock_retriever_svc.afetch.assert_called_once()
    
    # 验证 QAService 接收到的输入是否包含 context
    # call_args[0][0] 是第一个位置参数，即 inputs 字典
    call_inputs = mock_qa_svc.ainvoke.call_args[0][0]
    
    assert call_inputs["question"] == user_query
    # 关键：验证 Context 是否被正确拼接并注入
    assert "Context A" in call_inputs["context"]
    assert "Context B" in call_inputs["context"]

def test_format_docs_logic():
    """
    单元测试：文档格式化逻辑
    """
    # 不需要 Mock Service，直接测试 RAGPipeline 的私有方法（如果可访问）或辅助逻辑
    # 由于 Python 中私有方法可以访问，我们直接测试 _format_docs
    pipeline = RAGPipeline(MagicMock(), MagicMock())
    
    docs = [
        Document(page_content="Part 1"),
        Document(page_content="Part 2")
    ]
    
    formatted = pipeline._format_docs(docs)
    assert formatted == "Part 1\n\nPart 2"