# -*- coding: utf-8 -*-
"""
这个文件属于初期开发学习的遗留, 删掉太麻烦就不删了
现在充当vectorstore的胶水代码
主要包装setup_vector_store这个函数
实际上的ingest逻辑参考processor.py
"""
import logging
from typing import Any

from app.services.retrieval import setup_vector_store

# 获取 'core.ingest' 模块的 logger
logger = logging.getLogger(__name__)


def build_or_get_vector_store(
        collection_name: str, 
        embed_model: Any, 
        force_rebuild: bool = False,
        auto_ingest: bool = False

        ):
    """
    构建（或加载）向量数据库，并将文档加载、分割、嵌入后存入。

    :param collection_name: 要使用的向量数据库集合名称
    :param embed_model: 用于生成向量的 embedding 模型
    :param force_rebuild: 是否强制重建集合
    :return: 配置好并包含文档的 Chroma 向量数据库实例
    """
    logger.info("开始构建/加载向量数据库，集合: %s", collection_name)

    vector_store = setup_vector_store(collection_name, embed_model)

    return vector_store
