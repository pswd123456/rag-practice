# app/services/retrieval/vector_store.py
import logging
from app.services.retrieval.vector_store_manager import VectorStoreManager

logger = logging.getLogger(__name__)

def setup_vector_store(collection_name: str, embedding_function):
    """
    [Compatibility] 兼容旧接口，内部转发给 VectorStoreManager
    """
    manager = VectorStoreManager(collection_name, embedding_function)
    return manager.get_vector_store()