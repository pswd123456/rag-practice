from app.core.config import settings
from langchain_huggingface import HuggingFaceEmbeddings
import os
import logging

logger = logging.getLogger(__name__)


def setup_hf_embed_model(embed_model_name: str):
    """
    配置并返回 Embedding 模型实例。

    :return: HuggingFaceEmbeddings 实例
    """
    logger.info("正在设置 Embedding 模型...")

    embed_model_path = settings.EMBED_MODEL_DIR / embed_model_name

    if not embed_model_path.exists():
        logger.error(f"本地模型文件不存在: {embed_model_path}")
        raise ValueError(f"本地模型不存在: {embed_model_path}")

    logger.info(f"正在使用本地模型: {embed_model_name}")

    # 自动检测使用 'cuda' (如果可用) 或 'cpu'
    model_kwargs = {'device': 'cuda' if 'cuda' in os.getenv('DEVICE', 'cuda') else 'cpu'}

    logger.debug(f"Embedding 模型: {embed_model_name}")

    embeddings = HuggingFaceEmbeddings(
        # 使用本地路径的模型
        model_name=str(embed_model_path),
        model_kwargs=model_kwargs
    )
    logger.info("Embedding 模型设置完成。")
    return embeddings