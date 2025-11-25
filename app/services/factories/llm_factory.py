from langchain_openai import ChatOpenAI
from pydantic import SecretStr
import logging
from typing import Optional, Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

def setup_llm(model_name: Optional[str] = None, **kwargs: Any) -> ChatOpenAI:
    """
    通用 LLM 工厂函数。
    根据模型名称自动路由到不同的 Provider (DashScope, ZenMux, DeepSeek)。
    
    :param model_name: 模型名称 (e.g., "qwen-plus", "deepseek-chat")
    :param kwargs: 透传给 ChatOpenAI 的其他参数 (如 max_tokens, temperature)
    """
    # 1. 确定模型名称
    default_model = settings.DEFAULT_LLM_MODEL
    if not model_name:
        model_name = default_model
    target_model = model_name
    
    logger.info(f"正在初始化 LLM: {target_model} ...")

    api_key: str = ""
    base_url: str = ""
    
    # 2. 路由逻辑
    
    # 分支 A: Gemini / ZenMux
    if "gemini" in target_model.lower() or target_model.startswith("google/"):
        logger.debug("识别为 Gemini 模型，使用 ZenMux 配置。")
        api_key = settings.ZENMUX_API_KEY
        base_url = settings.ZENMUX_BASE_URL
        
        if not api_key:
            logger.warning("ZENMUX_API_KEY 未设置")
            raise ValueError("LLM apikey is not set (ZenMux)")

    # 分支 B: DeepSeek [新增]
    elif "deepseek" in target_model.lower():
        logger.debug("识别为 DeepSeek 模型，使用 DeepSeek 配置。")
        api_key = settings.DEEPSEEK_API_KEY or ""
        base_url = settings.DEEPSEEK_BASE_URL
        
        if not api_key:
            logger.error("DEEPSEEK_API_KEY 未设置")
            raise ValueError("LLM apikey is not set (DeepSeek)")

    # 分支 C: Qwen / DashScope (默认)
    else:
        logger.debug("识别为 Qwen/默认 模型，使用 DashScope 配置。")
        api_key = settings.DASHSCOPE_API_KEY
        base_url = settings.DASHSCOPE_BASE_URL
        
        if not api_key:
            logger.error("DASHSCOPE_API_KEY 未设置")
            raise ValueError("LLM apikey is not set (DashScope)")

    # 3. 构造参数
    model_kwargs = kwargs.pop("model_kwargs", {})
    
    # Qwen 需要 stream_options 来获得 usage
    if "qwen" in target_model.lower():
        model_kwargs["stream_options"] = {"include_usage": True}
        
    # DeepSeek 有时也支持 stream_options，视具体 Provider 而定，暂不强制加

    # 4. 实例化
    llm = ChatOpenAI(
        model=target_model,
        api_key=SecretStr(api_key),
        base_url=base_url,
        model_kwargs=model_kwargs,
        streaming=kwargs.pop("streaming", True), # 默认开启流式
        **kwargs
    )
    
    logger.info(f"LLM 初始化完成 [{target_model}]")
    return llm