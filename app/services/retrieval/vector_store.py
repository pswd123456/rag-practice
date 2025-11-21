from functools import lru_cache
import logging
import chromadb
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_chroma_client():
    """
    获取全局唯一的 Chroma HTTP 客户端实例 (单例模式)。
    使用 lru_cache 缓存结果，确保整个进程生命周期内只初始化一次连接池。
    """
    if settings.CHROMA_SERVER_HOST:
        logger.info(f"正在初始化全局 Chroma 客户端 ({settings.CHROMA_SERVER_HOST}:{settings.CHROMA_SERVER_PORT})...")
        return chromadb.HttpClient(
            host=settings.CHROMA_SERVER_HOST,
            port=settings.CHROMA_SERVER_PORT
        )
    return None

def setup_vector_store(collection_name: str, embedding_function: Embeddings):
    """
    配置并返回向量数据库 (Chroma) 实例。
    复用全局客户端连接，避免连接泄露。

    :param collection_name: 集合名称
    :param embedding_function: Embedding 函数实例
    :return: Chroma 实例
    """

    if settings.CHROMA_SERVER_HOST:
        client = get_chroma_client()
        
        vector_store = Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=embedding_function,
        )
        
    else:
        # 降级回本地模式 (兼容非 Docker 开发环境)
        # 本地模式通常用于测试，每次重新加载影响不大，但也可以考虑优化
        logger.debug(f"使用本地持久化目录: {settings.VECTOR_DB_PERSIST_DIR}")

        vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embedding_function,
            persist_directory=settings.VECTOR_DB_PERSIST_DIR
        )

    return vector_store