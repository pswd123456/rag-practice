from langchain_community.embeddings import DashScopeEmbeddings
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def setup_embed_model(embed_model_name: str):
    """
    配置并返回 Embedding 模型实例 (DashScope)。

    :param model_name: DashScope 的模型名称，例如 "text-embedding-v2"
    :return: DashScopeEmbeddings 实例
    """

    logger.info(f"正在设置 Embedding 模型 (DashScope: {embed_model_name})...")

    if not settings.DASHSCOPE_API_KEY:
        raise ValueError("未找到 DASHSCOPE_API_KEY，请检查环境变量或 .env 配置")

    # 使用 DashScope
    embeddings = DashScopeEmbeddings(
        model=embed_model_name,
        dashscope_api_key=settings.DASHSCOPE_API_KEY
    )
    
    logger.info("Embedding 模型设置完成。")   

    return embeddings