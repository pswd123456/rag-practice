import pytest
import uuid

# 辅助函数
def get_random_suffix():
    return uuid.uuid4().hex[:8]

# 1. 测试创建流程 (这个测试本身就是验证创建，所以我们手动清理，或者保留上面的写法)
# 为了演示清理，我们只保留最核心的上传测试
@pytest.mark.asyncio
async def test_create_and_delete_logic(client):
    """验证我们刚才写的创建和删除接口本身是好使的"""
    # 创建
    name = f"manual_del_{get_random_suffix()}"
    res = await client.post("/knowledge/knowledges", json={"name": name})
    kb_id = res.json()["id"]
    
    # 删除
    del_res = await client.delete(f"/knowledge/knowledges/{kb_id}")
    assert del_res.status_code == 200
    
    # 再次查询应该 404
    get_res = await client.get(f"/knowledge/knowledges/{kb_id}")
    assert get_res.status_code == 404


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