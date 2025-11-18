from app.core.config import settings
from app.services.util import logger
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

def setup_vector_store(collection_name: str, embedding_function: HuggingFaceEmbeddings):
    """
    配置并返回向量数据库 (Chroma) 实例。
    如果持久化目录中已存在同名集合，Chroma 会自动加载它。

    :param collection_name: 集合名称
    :param embedding_function: Embedding 函数实例
    :return: Chroma 实例
    """
    logger.info(f"正在设置向量数据库 (Chroma)...")
    logger.debug(f"  集合名称: {collection_name}")
    logger.debug(f"  持久化目录: {settings.VECTOR_DB_PERSIST_DIR}")

    vector_store = Chroma(
        collection_name = collection_name,
        embedding_function = embedding_function,
        persist_directory = settings.VECTOR_DB_PERSIST_DIR
    )
    logger.info("向量数据库 (Chroma) 设置完成。")
    return vector_store