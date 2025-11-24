from langchain_openai import ChatOpenAI
from pydantic import SecretStr
import logging
from typing import Optional, Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

def setup_llm(model_name: Optional[str] = None, **kwargs: Any) -> ChatOpenAI:
    """
    通用 LLM 工厂函数。
    根据模型名称自动路由到不同的 Provider (DashScope 或 ZenMux/Gemini)。
    
    :param model_name: 模型名称 (e.g., "qwen-plus", "google/gemini-1.5-pro")
    :param kwargs: 透传给 ChatOpenAI 的其他参数 (如 max_tokens, temperature)
    """
    # 1. 确定模型名称 (优先使用传入参数，否则使用配置默认值)
    # 注意：getattr 是为了防止 step 1 配置未生效导致报错，生产环境应直接使用 settings.DEFAULT_LLM_MODEL
    default_model = getattr(settings, "DEFAULT_LLM_MODEL")
    target_model = model_name or default_model
    
    logger.info(f"正在初始化 LLM: {target_model} ...")

    api_key: str = ""
    base_url: str = ""
    
    # 2. 路由逻辑
    # 分支 A: Gemini / ZenMux
    if "gemini" in target_model.lower() or target_model.startswith("google/"):
        logger.debug("识别为 Gemini 模型，使用 ZenMux 配置。")
        api_key = getattr(settings, "ZENMUX_API_KEY", "")
        base_url = getattr(settings, "ZENMUX_BASE_URL", "https://zenmux.ai/api/v1")
        
        if not api_key:
            logger.warning("ZENMUX_API_KEY 未设置，Gemini 调用可能会失败。")

    # 分支 B: Qwen / DashScope (默认)
    else:
        logger.debug("识别为 Qwen/默认 模型，使用 DashScope 配置。")
        api_key = settings.DASHSCOPE_API_KEY
        base_url = settings.DASHSCOPE_BASE_URL
        
        if not api_key:
            logger.error("DASHSCOPE_API_KEY 未设置！")
            raise ValueError("LLM apikey is not set (DashScope)")

    # 3. 构造参数
    model_kwargs = kwargs.pop("model_kwargs", {})
    # Qwen 需要 stream_options 来获得 usage
    if "qwen" in target_model.lower():
        model_kwargs["stream_options"] = {"include_usage": True}

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

# --- Backward Compatibility ---
def setup_qwen_llm(model_name: str, max_tokens: Optional[int] = None) -> ChatOpenAI:
    """
    [Deprecated] 旧版工厂函数，保留以兼容旧代码 (Step 4 前)。
    """
    logger.warning("setup_qwen_llm is deprecated, please use setup_llm instead.")
    return setup_llm(model_name=model_name, max_tokens=max_tokens)