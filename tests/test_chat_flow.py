import pytest
import asyncio
import time
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
    
    # 1. 捕获上传响应，获取 doc_id
    upload_res = await client.post(f"/knowledge/{kb_id}/upload", files=files)
    assert upload_res.status_code == 200
    doc_id = upload_res.json() # 假设 API 返回的是 int 类型的 doc_id

    # 2. 🛠️ [核心修复] 轮询等待文档状态变为 COMPLETED
    # 设置最大超时时间 (比如 20秒)，避免死循环
    max_retries = 20
    is_processed = False
    
    print(f">>> 开始轮询文档 {doc_id} 状态...")
    for _ in range(max_retries):
        # 调用你在 knowledge.py 里写的 GET /knowledge/documents/{doc_id} 接口
        doc_res = await client.get(f"/knowledge/documents/{doc_id}")
        assert doc_res.status_code == 200
        
        status = doc_res.json()["status"]
        print(f"Current Status: {status}")
        
        if status == "COMPLETED":
            is_processed = True
            break
        elif status == "FAILED":
            pytest.fail(f"文档处理失败: {doc_res.json().get('error_message')}")
        
        # 没完成就等 1 秒再查
        await asyncio.sleep(1)

    if not is_processed:
        pytest.fail("测试失败：文档处理超时 (Wait > 20s)")

    # B. 测试默认策略
    res_default = await client.post("/chat/query", json={
        "query": "What is DeepSeek?",
        "knowledge_id": kb_id,
        "strategy": "default"
    })

    assert res_default.status_code == 200
    ans_default = res_default.json()
    
    # 调试输出：如果失败了，打印出到底返回了什么
    if len(ans_default["sources"]) == 0:
        print(f"Debug Response: {ans_default}")

    assert len(ans_default["sources"]) > 0
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