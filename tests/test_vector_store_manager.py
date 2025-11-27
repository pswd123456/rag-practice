# tests/services/test_vector_store_manager.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.retrieval.vector_store_manager import VectorStoreManager, _VECTOR_STORE_CACHE

@pytest.fixture(autouse=True)
def clear_cache():
    """
    每个测试执行前/后清理全局缓存，防止测试间污染
    """
    _VECTOR_STORE_CACHE.clear()
    yield
    _VECTOR_STORE_CACHE.clear()

def test_ensure_collection_caching(mock_chroma):
    """
    测试缓存命中逻辑：多次调用 ensure_collection 应该只初始化一次向量库
    """
    embed_mock = MagicMock()
    manager = VectorStoreManager(collection_name="test_cache_kb", embed_model=embed_mock)

    # 1. 第一次调用，应该触发 build_or_get_vector_store
    with patch("app.services.retrieval.vector_store_manager.build_or_get_vector_store") as mock_build:
        mock_build.return_value = mock_chroma
        
        store1 = manager.ensure_collection()
        assert mock_build.call_count == 1
        assert "test_cache_kb" in _VECTOR_STORE_CACHE

        # 2. 第二次调用，应该直接从 _VECTOR_STORE_CACHE 读取，不触发 build
        store2 = manager.ensure_collection()
        assert mock_build.call_count == 1  # 计数器不应增加
        assert store1 is store2            # 对象实例应该是同一个

def test_reload_force_rebuild(mock_chroma):
    """
    测试重载逻辑：reload 应该强制清理缓存并重新构建
    """
    embed_mock = MagicMock()
    manager = VectorStoreManager(collection_name="test_reload_kb", embed_model=embed_mock)

    # 预填充缓存
    _VECTOR_STORE_CACHE["test_reload_kb"] = MagicMock()

    with patch("app.services.retrieval.vector_store_manager.build_or_get_vector_store") as mock_build:
        mock_build.return_value = mock_chroma
        
        # 执行 Reload
        new_store = manager.reload(force_rebuild=True)
        
        # 验证缓存被更新
        assert mock_build.called
        assert _VECTOR_STORE_CACHE["test_reload_kb"] == new_store