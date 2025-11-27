import pytest
from unittest.mock import MagicMock, patch
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.retrieval.vector_store_manager import VectorStoreManager

def test_create_dense_retriever():
    """测试默认 (Dense) 策略"""
    # Mock Manager
    manager = MagicMock(spec=VectorStoreManager)
    # [Fix] 显式设置 client 和 index_name，防止 AttributeError
    manager.client = MagicMock()
    manager.index_name = "test_index"
    
    mock_store = MagicMock()
    manager.get_vector_store.return_value = mock_store
    
    # 调用工厂
    RetrievalFactory.create_retriever(
        store_manager=manager,
        strategy="dense",
        top_k=5,
        knowledge_id=101
    )
    
    # 验证是否调用了 store.as_retriever
    mock_store.as_retriever.assert_called_with(
        search_type="similarity",
        search_kwargs={
            "k": 5, 
            "filter": [{"term": {"metadata.knowledge_id": 101}}]
        }
    )

def test_create_hybrid_retriever():
    """测试 Hybrid 策略 (ES RRF)"""
    manager = MagicMock(spec=VectorStoreManager)
    # [Fix] 显式设置 client 和 index_name
    manager.client = MagicMock()
    manager.index_name = "test_index"
    manager.embed_model = MagicMock() # 同时也需要 embed_model

    # Hybrid 策略会实例化一个新的 ElasticsearchStore
    with patch("app.services.factories.retrieval_factory.ElasticsearchStore") as MockESStore:
        mock_hybrid_store = MockESStore.return_value
        
        RetrievalFactory.create_retriever(
            store_manager=manager,
            strategy="hybrid",
            top_k=3,
            knowledge_id=202
        )
        
        # 验证是否使用了 DenseVectorStrategy(hybrid=True)
        call_kwargs = MockESStore.call_args[1]
        strategy = call_kwargs.get("strategy")
        assert strategy is not None
        # 验证策略属性
        assert getattr(strategy, "hybrid", False) is True
        
        # 验证 filter
        mock_hybrid_store.as_retriever.assert_called()
        args = mock_hybrid_store.as_retriever.call_args[1]
        assert args["search_kwargs"]["filter"] == [{"term": {"metadata.knowledge_id": 202}}]