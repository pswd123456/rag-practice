import logging
from functools import lru_cache
from typing import Optional

# 需要 pip install elasticsearch
from elasticsearch import Elasticsearch
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_es_client() -> Elasticsearch:
    """
    创建并缓存全局 Elasticsearch 客户端 (Sync)。
    使用 lru_cache 确保单例模式，避免重复创建连接池。
    """
    logger.info(f"正在初始化 Elasticsearch 客户端: {settings.ES_URL}")
    
    # 构造连接参数
    connect_kwargs = {
        "hosts": settings.ES_URL,
        "request_timeout": settings.ES_TIMEOUT,
        "max_retries": 3,
        "retry_on_timeout": True,
    }

    # 处理账号密码认证 (针对生产环境)
    if settings.ES_USER and settings.ES_PASSWORD:
        connect_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    
    # 初始化客户端
    try:
        client = Elasticsearch(**connect_kwargs)
        return client
    except Exception as e:
        logger.error(f"Elasticsearch 客户端初始化失败: {e}")
        raise e

@retry(
    stop=stop_after_attempt(10),       # 最多重试 10 次
    wait=wait_fixed(3),                # 每次间隔 3 秒
    retry=retry_if_exception_type(Exception), # 遇到任何异常都重试
    reraise=True                       # 最后一次失败抛出异常
)
def wait_for_es():
    """
    阻塞式等待 ES 服务就绪。
    通常在应用启动 (lifespan) 或 Worker 启动时调用。
    """
    client = get_es_client()
    try:
        # 使用 info() 接口测试连接
        info = client.info()
        version = info['version']['number']
        logger.info(f"✅ Elasticsearch 已连接! Version: {version} | Cluster: {info['cluster_name']}")
        return True
    except Exception as e:
        logger.warning(f"⏳ 等待 Elasticsearch 就绪... (Error: {str(e)})")
        raise e