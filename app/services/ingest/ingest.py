# -*- coding: utf-8 -*-
"""
数据摄取模块 (ingest.py)

负责协调整个数据摄取流程：
1. 加载 Embedding 模型
2. 加载和分割源文档 (PDF)
3. 设置向量数据库 (Chroma)
4. 将分割后的文档存入向量数据库
"""
import logging
from typing import Any

from app.services.retrieval import setup_vector_store

from app.services.loader import get_prepared_docs

# 获取 'core.ingest' 模块的 logger
logger = logging.getLogger(__name__)


def build_or_get_vector_store(collection_name: str, embed_model: Any, force_rebuild: bool = False):
    """
    构建（或加载）向量数据库，并将文档加载、分割、嵌入后存入。

    :param collection_name: 要使用的向量数据库集合名称
    :param embed_model: 用于生成向量的 embedding 模型
    :param force_rebuild: 是否强制重建集合
    :return: 配置好并包含文档的 Chroma 向量数据库实例
    """
    logger.info("开始构建/加载向量数据库，集合: %s", collection_name)

    vector_store = setup_vector_store(collection_name, embed_model)
    chroma_collection = vector_store._collection
    item_count = chroma_collection.count()

    if force_rebuild and item_count > 0:
        logger.warning("检测到 force_rebuild=True，正在清空集合 %s ...", collection_name)
        vector_store._client.delete_collection(name=collection_name)
        vector_store = setup_vector_store(collection_name, embed_model)
        item_count = 0

    if item_count > 0:
        logger.info("向量数据库 '%s' 已存在, 跳过构建。", collection_name)
        return vector_store

    logger.info("向量数据库 '%s' 不存在，开始构建...", collection_name)
    docs = get_prepared_docs()

    logger.info("正在将 %s 个文档块添加到 '%s' 集合中...", len(docs), collection_name)
    try:
        vector_store.add_documents(docs)
        logger.info("文档添加成功。")
    except Exception as e:
        logger.error("向向量数据库添加文档时出错: %s", e, exc_info=True)
        raise

    logger.info("向量数据库 '%s' 构建完成并准备就绪。", collection_name)
    return vector_store
