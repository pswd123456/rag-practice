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

    mock_settings.DEEPSEEK_API_KEY = "sk-deepseek-test"
    mock_settings.DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    
    # Mock ChatOpenAI
    with patch("app.services.factories.llm_factory.ChatOpenAI") as MockChatOpenAI:
        
        # Case A: Qwen Model (Default path)
        setup_llm("qwen-plus")
        
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

        # Case C: DeepSeek Model [New]
        setup_llm("deepseek-chat")

        call_args_deepseek = MockChatOpenAI.call_args_list[2]
        _, kwargs_deepseek = call_args_deepseek
        assert kwargs_deepseek["base_url"] == "https://api.deepseek.com"
        assert kwargs_deepseek["api_key"].get_secret_value() == "sk-deepseek-test"


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
    """
    # 只要工厂逻辑正确，且配置有 Key (或 mock 了)，这里应该能跑通 API 链路
    payload = {
        "query": "Hello",
        "strategy": "default",
        "llm_model": "qwen-turbo"
    }
    response = await client.post("/chat/query", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data