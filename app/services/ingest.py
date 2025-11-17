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
from app.services.loader import get_prepared_docs
from app.services.vector_store.vector_store import setup_vector_store

# 获取 'core.ingest' 模块的 logger
logger = logging.getLogger(__name__)

def build_or_get_vector_store(collection_name:str, embed_model):
    """
    构建（或加载）向量数据库，并将文档加载、分割、嵌入后存入。
    
    :param collection_name: 要使用的向量数据库集合名称
    :return: 配置好并包含文档的 Chroma 向量数据库实例
    """
    logger.info(f"开始构建向量数据库，集合名称: {collection_name}")
    
    # 设置 Embedding 模型
    logger.debug("设置 Embedding 模型...")
    # (日志记录在 util.setup_embed_model 内部)
    embed_model = embed_model

    # 设置向量数据库
    logger.debug("设置向量数据库 (Chroma)...")
    # (日志记录在 util.setup_vector_store 内部)
    vector_store = setup_vector_store(collection_name, embed_model)

    chroma_collection = vector_store._collection
    item_count = chroma_collection.count()

    if item_count > 0:
        logger.info(f"向量数据库 '{collection_name}' 已存在，已跳过构建步骤。")
    else:
        logger.info(f"向量数据库 '{collection_name}' 不存在，开始构建...")
         # 加载和分割文档
        logger.debug("加载和分割文档...")
        # (日志记录在 util.setup_load_docs 内部)
        docs = get_prepared_docs()
        
        # 将文档添加到向量数据库
        logger.info(f"正在将 {len(docs)} 个文档块添加到 '{collection_name}' 集合中...")
        try:
            # ChromaDB 会处理重复数据（如果 ID 一致），但这里我们是批量添加
            vector_store.add_documents(docs)
            logger.info("文档添加成功。")
        except Exception as e:
            logger.error(f"向向量数据库添加文档时出错: {e}", exc_info=True)
            raise # 重新抛出异常，让上层 (main.py) 知道失败了
        
        logger.info(f"向量数据库 '{collection_name}' 构建完成并准备就绪。")
    
    return vector_store
