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
    """
    logger.info(f"正在初始化 Elasticsearch 客户端: {settings.ES_URL}")
    
    # 构造连接参数
    connect_kwargs = {
        "hosts": settings.ES_URL,
        "request_timeout": settings.ES_TIMEOUT,
        "max_retries": 3,
        "retry_on_timeout": True,
    }

    if settings.ES_USER and settings.ES_PASSWORD:
        connect_kwargs["basic_auth"] = (settings.ES_USER, settings.ES_PASSWORD)
    
    try:
        client = Elasticsearch(**connect_kwargs)
        return client
    except Exception as e:
        logger.error(f"Elasticsearch 客户端初始化失败: {e}")
        raise e

def _log_attempt_delay(retry_state):
    """重试前的简要日志回调"""
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        # 只打印简短错误信息，不打印堆栈
        logger.warning(
            f"⏳ Elasticsearch 尚未就绪，将在 {retry_state.next_action.sleep}s 后重试... "
            f"(Attempt {retry_state.attempt_number}) | Error: {str(exc)}"
        )

@retry(
    stop=stop_after_attempt(20),       # [Mod] 增加重试次数: 20次 * 3s = 60s
    wait=wait_fixed(3),                # 每次间隔 3 秒
    retry=retry_if_exception_type(Exception), 
    reraise=True,
    before_sleep=_log_attempt_delay    # [Mod] 使用回调机制打印日志
)
def wait_for_es():
    """
    阻塞式等待 ES 服务就绪。
    """
    client = get_es_client()
    # 直接调用，Tenacity 会自动捕获异常并重试
    info = client.info()
    version = info['version']['number']
    logger.info(f"✅ Elasticsearch 已连接! Version: {version} | Cluster: {info['cluster_name']}")
    return True