import pytest
import uuid
import asyncio
# 辅助函数
def get_random_suffix():
    return uuid.uuid4().hex[:8]

@pytest.mark.asyncio
async def test_create_and_delete_logic(client):
    """验证异步删除流程：创建 -> 触发删除 -> 轮询等待直至消失"""
    # 1. 创建
    name = f"manual_del_{get_random_suffix()}"
    res = await client.post("/knowledge/knowledges", json={"name": name})
    assert res.status_code == 200
    kb_id = res.json()["id"]
    
    # 2. 删除 (触发异步任务)
    del_res = await client.delete(f"/knowledge/knowledges/{kb_id}")
    # 注意：如果你在 router 里设置了 status_code=202，这里应改为 202；如果是默认 200 则保持 200
    assert del_res.status_code in [200, 202]
    
    # 3. 轮询检查 (Polling)
    # 给 Worker 一点时间来处理删除任务 (比如最多等 5 秒)
    max_retries = 10
    wait_seconds = 0.5
    
    is_deleted = False
    for _ in range(max_retries):
        # 尝试查询
        get_res = await client.get(f"/knowledge/knowledges/{kb_id}")
        
        if get_res.status_code == 404:
            # 成功：已经查不到了，说明删除完成
            is_deleted = True
            break
        
        # 失败：还在，等一会儿再查
        await asyncio.sleep(wait_seconds)
    
    # 4. 最终断言
    if not is_deleted:
        pytest.fail(f"超时：知识库 {kb_id} 在 {max_retries * wait_seconds} 秒内未被删除。Worker 正常运行吗？")


# 2. 测试上传流程 (使用 temp_kb 自动管理生命周期)
@pytest.mark.asyncio
async def test_upload_flow(client, temp_kb):
    """
    这里的 temp_kb 参数就是上面 fixture yield 出来的 kb_id。
    在这个测试里，我们只管上传，不用管创建和删除，fixture 帮我们全包了。
    """
    kb_id = temp_kb # 拿到 fixture 提供的 ID

    # 模拟上传
    file_content = b"Content for teardown test."
    files = {"file": ("clean_test.txt", file_content, "text/plain")}
    
    response = await client.post(f"/knowledge/{kb_id}/upload", files=files)
    
    assert response.status_code == 200
    assert isinstance(response.json(), int)
    
    # 测试结束，Pytest 会自动跳回去执行 temp_kb 里 yield 后面的代码 (执行删除)