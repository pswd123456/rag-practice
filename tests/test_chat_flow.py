import pytest
import asyncio
# 1. 测试最基本的对话 (不带 knowledge_id)
@pytest.mark.asyncio
async def test_chat_simple(client):
    payload = {
        "query": "Hello, who are you?",
        "strategy": "default"
    }
    response = await client.post("/chat/query", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    # 刚开始没有任何知识库，sources 应该是空的
    assert isinstance(data["sources"], list)

# 2. 测试带知识库的对话 (集成测试)
@pytest.mark.asyncio
async def test_chat_with_knowledge(client, temp_kb):
    kb_id = temp_kb

    # A. 上传文件
    content = b"DeepSeek is a powerful LLM developed by High-Flyer."
    files = {"file": ("deepseek_intro.txt", content, "text/plain")}
    await client.post(f"/knowledge/{kb_id}/upload", files=files)
    
    # 🛠️ [关键修改] 增加等待时间
    # 给 Worker 留出处理时间 (MinIO下载+解析+Embedding+入库)
    # 根据你的电脑性能，3-5秒通常足够处理这个小文本
    print(">>> 等待 Worker 处理文档...")
    await asyncio.sleep(3) 

    # B. 测试默认策略 (现在应该能查到了)
    res_default = await client.post("/chat/query", json={
        "query": "What is DeepSeek?",
        "knowledge_id": kb_id,
        "strategy": "default"
    })

    assert res_default.status_code == 200
    ans_default = res_default.json()
    assert len(ans_default["sources"]) > 0 # 应该能搜到刚才传的文件
    assert "DeepSeek" in ans_default["sources"][0]["chunk_content"]

    # C. 测试 A/B 策略开关 (验证代码路径是否通畅)
    # 虽然现在 hybrid 逻辑是回退，但我们至少要保证它不报错
    res_hybrid = await client.post("/chat/query", json={
        "query": "What is DeepSeek?",
        "knowledge_id": kb_id,
        "strategy": "hybrid" 
    })
    assert res_hybrid.status_code == 200
    
    # D. 测试非法策略 (验证兜底逻辑)
    res_invalid = await client.post("/chat/query", json={
        "query": "test",
        "strategy": "unknown_strategy_xyz"
    })
    assert res_invalid.status_code == 200 # 我们的代码里写了 else 兜底，所以不应该 500