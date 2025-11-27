# app/services/ingest/ingest.py
import logging
from typing import Any
from app.services.retrieval.vector_store_manager import VectorStoreManager

logger = logging.getLogger(__name__)

def build_or_get_vector_store(
    collection_name: str, 
    embed_model: Any, 
    force_rebuild: bool = False, # ES 中通常不建议轻易 rebuild，因为涉及 Mapping
    auto_ingest: bool = False
):
    """
    [适配层] 获取配置好的 ElasticsearchStore 实例。
    """
    manager = VectorStoreManager(collection_name, embed_model)
    
    if force_rebuild:
        logger.warning(f"触发强制重建索引: {collection_name}")
        manager.delete_index()
    
    # 这一步会自动处理 ensure_index
    return manager.get_vector_store()