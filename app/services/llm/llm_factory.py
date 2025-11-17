from app.core.config import settings
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
import os
import logging

logger = logging.getLogger(__name__)
def setup_qwen_llm(model_name: str):
    """
    配置并返回大语言模型 (LLM) 实例。

    :return: ChatOpenAI 实例
    :raises ValueError: 如果 llm api key 环境变量未设置
    """
    logger.info("正在设置 LLM...")
    # 从环境变量读取 API 密钥
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    if not dashscope_api_key:
        logger.error("llm apikey 未设置！")
        raise ValueError("LLM apikey is not set")

    base_url = settings.QWEN_BASE_URL
    logger.debug(f"LLM Base URL: {base_url}")

    llm = ChatOpenAI(
        model = model_name,
        api_key=SecretStr(dashscope_api_key), # 使用 SecretStr 避免密钥在日志中意外泄露
        base_url=base_url,
    )
    logger.info(f"LLM 设置完成 模型名称: {model_name}")
    return llm