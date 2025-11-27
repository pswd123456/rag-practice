# tests/api/test_endpoints.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.api import deps
from app.main import app

# ==========================================
# 1. Chat 接口测试
# ==========================================

@pytest.mark.asyncio
async def test_chat_query_validation_error(async_client):
    """
    [Smoke] 测试参数校验：缺少 query 字段应返回 422
    """
    payload = {
        "knowledge_id": 1,
        "strategy": "default"
        # 缺少 "query"
    }
    response = await async_client.post("/chat/query", json=payload)
    assert response.status_code == 422
    assert "Field required" in response.text

@pytest.mark.asyncio
async def test_chat_query_success(async_client):
    """
    [Smoke] 测试正常对话流程 (Mock Pipeline)
    """
    # 1. Mock Pipeline Factory 依赖
    # 我们不希望测试真实的 RAG 逻辑，只测试路由层
    mock_pipeline = MagicMock()
    # 模拟 async_query 返回 (answer, docs)
    mock_pipeline.async_query = AsyncMock(return_value=("Mock Answer", []))

    async def mock_factory_dependency(*args, **kwargs):
        # 工厂函数本身是异步的，返回一个 Pipeline 实例
        return mock_pipeline

    # 2. 覆盖 FastAPI 依赖
    app.dependency_overrides[deps.get_rag_pipeline_factory] = lambda: mock_factory_dependency

    try:
        payload = {
            "query": "Hello",
            "knowledge_id": 1,
            "strategy": "dense"
        }
        response = await async_client.post("/chat/query", json=payload)
        
        # 3. 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Mock Answer"
        assert isinstance(data["sources"], list)
    
    finally:
        # 清理依赖覆盖
        app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_chat_stream_headers(async_client):
    """
    [Smoke] 测试流式接口是否返回正确的 SSE Header
    """
    # Mock Pipeline
    mock_pipeline = MagicMock()
    # astream_with_sources 是个生成器
    async def mock_gen(*args, **kwargs):
        yield "Mock Stream Chunk"
    
    mock_pipeline.astream_with_sources = mock_gen
    
    async def mock_factory(*args, **kwargs):
        return mock_pipeline

    app.dependency_overrides[deps.get_rag_pipeline_factory] = lambda: mock_factory

    try:
        payload = {"query": "Stream me"}
        response = await async_client.post("/chat/stream", json=payload)
        
        assert response.status_code == 200
        # 🟢 [关键] 验证 SSE Content-Type
        assert "text/event-stream" in response.headers["content-type"]
    finally:
        app.dependency_overrides = {}

# ==========================================
# 2. Evaluation 接口测试
# ==========================================

@pytest.mark.asyncio
async def test_create_experiment_dependency_check(async_client, db_session):
    """
    [Integration] 测试创建实验时的依赖检查：
    如果 Knowledge 或 Testset 不存在，应返回 404
    """
    # 尝试使用不存在的 ID (999)
    payload = {
        "knowledge_id": 999,
        "testset_id": 999,
        "runtime_params": {"top_k": 5}
    }
    
    response = await async_client.post("/evaluation/experiments", json=payload)
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]

@pytest.mark.asyncio
async def test_create_testset_success(async_client, mock_redis):
    """
    [Integration] 测试创建测试集并触发后台任务
    """
    payload = {
        "name": "Smoke Test Set",
        "source_doc_ids": [1, 2, 3],
        "generator_llm": "qwen-max"
    }
    
    response = await async_client.post("/evaluation/testsets", json=payload)
    
    assert response.status_code == 200
    ts_id = response.json()
    assert isinstance(ts_id, int)
    
    # 验证 Redis 任务推送
    assert mock_redis.enqueue_job.called
    args = mock_redis.enqueue_job.call_args[0]
    assert args[0] == "generate_testset_task"
    assert args[2] == [1, 2, 3] # source_doc_ids