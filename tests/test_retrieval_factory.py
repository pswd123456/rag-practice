# tests/services/test_retrieval_factory.py
import pytest
from unittest.mock import MagicMock
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.retrieval.vector_store_manager import VectorStoreManager

def test_create_dense_retriever(mock_chroma):
    """
    测试默认策略 (Dense) 下 Retriever 的参数构造
    """
    # 1. Mock Manager
    manager = MagicMock(spec=VectorStoreManager)
    manager.vector_store = mock_chroma
    
    # 模拟 as_retriever 方法
    mock_chroma.as_retriever.return_value = "RetrieverInstance"

    # 2. 调用工厂
    retriever = RetrievalFactory.create_retriever(
        store_manager=manager,
        strategy="dense",
        top_k=5,
        knowledge_id=101
    )

    # 3. 验证参数透传
    # 确保调用了 manager.vector_store.as_retriever
    # 并且 search_kwargs 包含了 filter 和 k
    call_kwargs = mock_chroma.as_retriever.call_args[1]
    search_kwargs = call_kwargs["search_kwargs"]
    
    assert search_kwargs["k"] == 5
    assert search_kwargs["filter"] == {"knowledge_id": 101}
    assert retriever == "RetrieverInstance"

def test_strategy_fallback(mock_chroma):
    """
    测试未知策略回退机制 (Should fallback to Dense)
    """
    manager = MagicMock(spec=VectorStoreManager)
    manager.vector_store = mock_chroma
    
    RetrievalFactory.create_retriever(
        store_manager=manager,
        strategy="unknown_strategy_xyz", # 传入乱码策略
        top_k=3
    )
    
    # 验证是否还是调用了 as_retriever (Dense逻辑)
    assert mock_chroma.as_retriever.called