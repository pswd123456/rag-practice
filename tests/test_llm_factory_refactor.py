import pytest
from unittest.mock import patch, MagicMock
from app.services.factories.llm_factory import setup_llm

@patch("app.services.factories.llm_factory.settings")
def test_setup_llm_routing(mock_settings):
    """
    测试 setup_llm 是否根据模型名称正确路由到不同的 Provider配置
    """
    # 1. 配置 Mock Settings
    mock_settings.DASHSCOPE_API_KEY = "sk-qwen-test"
    mock_settings.DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    mock_settings.ZENMUX_API_KEY = "sk-zenmux-test"
    mock_settings.ZENMUX_BASE_URL = "https://zenmux.ai/api/v1"
    
    # 为了防止实例化 ChatOpenAI 时真的发起网络连接或校验 Key，
    # 我们 Mock 掉 ChatOpenAI 类
    with patch("app.services.factories.llm_factory.ChatOpenAI") as MockChatOpenAI:
        
        # Case A: Qwen Model (Default path)
        setup_llm("qwen-plus")
        
        # 验证调用参数
        call_args_qwen = MockChatOpenAI.call_args_list[0]
        _, kwargs_qwen = call_args_qwen
        
        assert kwargs_qwen["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert kwargs_qwen["api_key"].get_secret_value() == "sk-qwen-test"
        
        # Case B: Gemini Model (ZenMux path)
        setup_llm("google/gemini-pro")
        
        call_args_gemini = MockChatOpenAI.call_args_list[1]
        _, kwargs_gemini = call_args_gemini
        
        assert kwargs_gemini["base_url"] == "https://zenmux.ai/api/v1"
        assert kwargs_gemini["api_key"].get_secret_value() == "sk-zenmux-test"

@patch("app.services.factories.llm_factory.settings")
def test_setup_llm_fallback(mock_settings):
    """
    测试默认参数
    """
    mock_settings.DASHSCOPE_API_KEY = "sk-qwen-test"
    mock_settings.DASHSCOPE_BASE_URL = "https://qwen.url"
    mock_settings.DEFAULT_LLM_MODEL = "qwen-flash"

    with patch("app.services.factories.llm_factory.ChatOpenAI") as MockChatOpenAI:
        setup_llm() # 不传参数
        
        _, kwargs = MockChatOpenAI.call_args
        assert kwargs["model"] == "qwen-flash"
        assert kwargs["base_url"] == "https://qwen.url"

@pytest.mark.asyncio
async def test_chat_with_specific_model(client):
    """
    测试指定 LLM 模型参数 (集成测试)
    即使我们没有真实的 Gemini Key，只要工厂逻辑正确，
    它至少会尝试初始化，这里主要测 API 参数传递链路是否通畅。
    """
    payload = {
        "query": "Hello",
        "strategy": "default",
        "llm_model": "qwen-turbo" # 显式指定一个 Qwen 模型
    }
    response = await client.post("/chat/query", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data

@pytest.mark.asyncio
async def test_chat_simple(client):
    """回归测试：不传 llm_model 应该使用默认值"""
    payload = {
        "query": "Hello, who are you?",
        "strategy": "default"
        # llm_model missing
    }
    response = await client.post("/chat/query", json=payload)
    assert response.status_code == 200