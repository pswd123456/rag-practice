# tests/test_retrieval_factory.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.retrieval.vector_store_manager import VectorStoreManager

def test_create_dense_retriever():
    """测试默认 (Dense) 策略"""
    manager = MagicMock(spec=VectorStoreManager)
    manager.client = MagicMock()
    manager.index_name = "test_index"
    
    mock_store = MagicMock()
    manager.get_vector_store.return_value = mock_store
    
    RetrievalFactory.create_retriever(
        store_manager=manager,
        strategy="dense",
        top_k=5,
        knowledge_id=101
    )
    
    mock_store.as_retriever.assert_called_with(
        search_type="similarity",
        search_kwargs={
            "k": 5, 
            "filter": [{"term": {"metadata.knowledge_id": 101}}]
        }
    )

def test_create_hybrid_retriever():
    """测试 Hybrid 策略 (Manual RRF)"""
    manager = MagicMock(spec=VectorStoreManager)
    manager.client = MagicMock()
    manager.index_name = "test_index"
    manager.embed_model = MagicMock()

    # [Fix] 这里的 Patch 对象改为 ESHybridRetriever
    with patch("app.services.factories.retrieval_factory.ESHybridRetriever") as MockHybrid:
        mock_retriever_instance = MockHybrid.return_value
        
        RetrievalFactory.create_retriever(
            store_manager=manager,
            strategy="hybrid",
            top_k=3,
            knowledge_id=202
        )
        
        # 验证是否实例化了 ESHybridRetriever
        MockHybrid.assert_called_once_with(
            store_manager=manager,
            top_k=3,
            knowledge_id=202
        )