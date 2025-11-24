import pytest
import asyncio
import json
import logging
from httpx import AsyncClient

# 1. 配置日志 (替代 print)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def _upload_and_wait_for_doc(client: AsyncClient, kb_id: int, filename: str, content: bytes) -> int:
    """
    辅助函数：上传文件并轮询等待处理完成
    """
    # 1. 上传
    files = {"file": (filename, content, "text/plain")}
    upload_res = await client.post(f"/knowledge/{kb_id}/upload", files=files)
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    doc_id = upload_res.json()
    
    # 2. 轮询状态
    max_retries = 30
    for i in range(max_retries):
        res = await client.get(f"/knowledge/documents/{doc_id}")
        assert res.status_code == 200
        status = res.json()["status"]
        
        if status == "COMPLETED":
            logger.info(f"文档 {doc_id} 处理完成 (尝试次数: {i+1})")
            return doc_id
        elif status == "FAILED":
            error_msg = res.json().get("error_message")
            pytest.fail(f"文档处理失败: {error_msg}")
            
        await asyncio.sleep(0.5)
        
    pytest.fail(f"文档 {doc_id} 处理超时 (Wait > {max_retries * 0.5}s)")

# --- Tests ---

@pytest.mark.asyncio
async def test_chat_query_integration(client: AsyncClient, temp_kb: int):
    """
    测试标准问答接口 /chat/query
    流程: 创建KB -> 上传文档 -> 等待处理 -> 提问 -> 验证回答和来源
    """
    kb_id = temp_kb
    logger.info(f"开始测试 Chat Query Flow (KB ID: {kb_id})")

    # 1. 准备数据
    content = b"RAG (Retrieval-Augmented Generation) combines retrieval and generation."
    await _upload_and_wait_for_doc(client, kb_id, "rag_intro.txt", content)

    # 2. 发起提问
    payload = {
        "query": "What is RAG?",
        "knowledge_id": kb_id,
        "strategy": "default"
    }
    response = await client.post("/chat/query", json=payload)
    
    # 3. 验证响应
    assert response.status_code == 200
    data = response.json()
    
    # 验证 Schema 结构
    assert "answer" in data
    assert "sources" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    
    # 验证检索效果 (因为我们上传了相关文档，应该有 Sources)
    assert len(data["sources"]) > 0
    first_source = data["sources"][0]
    assert first_source["source_filename"] == "rag_intro.txt"
    assert "RAG" in first_source["chunk_content"]
    
    logger.info("Chat Query 测试通过")


@pytest.mark.asyncio
async def test_chat_stream_integration(client: AsyncClient, temp_kb: int):
    """
    测试流式问答接口 /chat/stream (SSE)
    流程: 创建KB -> 上传文档 -> 等待处理 -> 流式提问 -> 解析SSE事件 -> 验证完整性
    """
    kb_id = temp_kb
    logger.info(f"开始测试 Chat Stream Flow (KB ID: {kb_id})")

    # 1. 准备数据
    content = b"Streamlit is an open-source Python framework for data scientists."
    await _upload_and_wait_for_doc(client, kb_id, "streamlit_intro.txt", content)

    # 2. 发起流式请求
    payload = {
        "query": "What is Streamlit?",
        "knowledge_id": kb_id,
        "strategy": "default"
    }

    full_answer = ""
    sources_received = False
    
    # 使用 stream 上下文
    async with client.stream("POST", "/chat/stream", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # 状态机变量
        current_event = None

        # 🛠️ [Fix] 使用单一迭代器，避免 StreamConsumed 错误
        async for line in response.aiter_lines():
            if not line:
                continue
            
            if line.startswith("event:"):
                # 记录当前事件类型
                current_event = line[6:].strip()
            
            elif line.startswith("data:"):
                # 根据上一个 event 类型解析 data
                data_content = line[5:].strip()
                
                if current_event == "sources":
                    try:
                        sources = json.loads(data_content)
                        assert isinstance(sources, list)
                        if len(sources) > 0:
                            # 验证来源是否正确
                            assert sources[0]["source_filename"] == "streamlit_intro.txt"
                        sources_received = True
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode sources JSON: {data_content}")
                    
                elif current_event == "message":
                    try:
                        # message data 是 JSON 编码的字符串 (token)
                        # 例如: data: "Str"
                        token = json.loads(data_content)
                        full_answer += token
                    except json.JSONDecodeError:
                        # 兼容非 JSON 情况 (虽然我们的 API 应该总是返回 JSON string)
                        full_answer += data_content
                
                # data 处理完后，通常意味着一个 SSE 块结束
                # 但 SSE 标准允许 event 和 data 顺序不固定，这里我们不强制重置 current_event
                # 直到遇到下一个 event: xxx

    # 3. 验证结果
    assert sources_received, "未收到 Sources 事件"
    assert len(full_answer) > 0, "回答内容为空"
    assert "Streamlit" in full_answer or "framework" in full_answer, f"回答内容似乎不相关: {full_answer}"
    
    logger.info(f"Stream 回答接收完毕: {full_answer[:50]}...")
    logger.info("Chat Stream 测试通过")


@pytest.mark.asyncio
async def test_chat_strategy_fallback(client: AsyncClient, temp_kb: int):
    """
    测试不同策略参数的健壮性 (Robustness)
    确保即使策略未完全实现，也不会导致 500 错误
    """
    payload = {
        "query": "Test strategy",
        "knowledge_id": temp_kb,
        "strategy": "hybrid" # 暂时未实现的策略
    }
    response = await client.post("/chat/query", json=payload)
    assert response.status_code == 200
    assert "answer" in response.json()