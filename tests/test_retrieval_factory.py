import pytest
from unittest.mock import MagicMock
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.retrieval.vector_store_manager import VectorStoreManager

def test_retrieval_factory_dense():
    """验证默认策略返回 Dense Retriever"""
    # Arrange
    mock_store_manager = MagicMock(spec=VectorStoreManager)
    mock_vector_store = MagicMock()
    mock_store_manager.vector_store = mock_vector_store
    
    # Act
    RetrievalFactory.create_retriever(
        store_manager=mock_store_manager,
        strategy="dense",
        top_k=5,
        knowledge_id=10
    )
    
    # Assert
    mock_vector_store.as_retriever.assert_called_once()
    call_kwargs = mock_vector_store.as_retriever.call_args.kwargs['search_kwargs']
    
    assert call_kwargs['k'] == 5
    assert call_kwargs['filter'] == {'knowledge_id': 10}

def test_retrieval_factory_fallback():
    """验证未知策略回退"""
    mock_store_manager = MagicMock(spec=VectorStoreManager)
    
    RetrievalFactory.create_retriever(
        store_manager=mock_store_manager,
        strategy="unknown_magic_strategy"
    )
    
    # 应该回退调用 as_retriever
    mock_store_manager.vector_store.as_retriever.assert_called_once()