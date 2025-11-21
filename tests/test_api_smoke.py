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

@pytest.mark.asyncio
async def test_evaluation_crud(client):
    """
    验证 Testset 和 Experiment 的创建与删除 (包含级联逻辑验证)
    """
    # 1. 造假数据：我们需要一个 Testset 记录 (不一定要真的生成文件，只测 DB 逻辑)
    #    因为 API 需要 source_doc_ids，我们先造一个空的 Testset 记录
    #    或者，我们直接 mock create_generation_task 的入参
    
    # 为了简单，我们直接调用 API 创建一个 Testset 任务
    # (注意：由于没有真实的文档，worker 可能会失败，但 Testset 记录会创建)
    ts_name = f"testset_{get_random_suffix()}"
    create_res = await client.post("/evaluation/testsets", json={
        "name": ts_name,
        "source_doc_ids": [] # 空列表
    })
    assert create_res.status_code == 200
    ts_id = create_res.json()
    
    # 2. 验证 Testset 存在
    get_ts = await client.get(f"/evaluation/testsets/{ts_id}")
    assert get_ts.status_code == 200
    assert get_ts.json()["status"] == "GENERATING" # 初始状态
    
    # 3. 创建一个 Experiment (为了测试级联删除)
    # 需要先有一个 knowledge，我们临时建一个
    kb_name = f"kb_for_exp_{get_random_suffix()}"
    kb_res = await client.post("/knowledge/knowledges", json={"name": kb_name})
    kb_id = kb_res.json()["id"]
    
    exp_res = await client.post("/experiments", json={
        "knowledge_id": kb_id,
        "testset_id": ts_id,
        "runtime_params": {"top_k": 1}
    })
    # 注意：/experiments 路径可能要检查 evaluation.py 里的 prefix
    # 在 api/__init__.py 中，evaluation 的 prefix 是 /evaluation
    # 这里的 post 路径应该是 /evaluation/experiments
    # 修正 client 调用路径：
    exp_res = await client.post("/evaluation/experiments", json={
        "knowledge_id": kb_id,
        "testset_id": ts_id,
        "runtime_params": {"top_k": 1}
    })
    assert exp_res.status_code == 200
    exp_id = exp_res.json()
    
    # 4. 验证单独删除 Experiment
    del_exp = await client.delete(f"/evaluation/experiments/{exp_id}")
    assert del_exp.status_code == 200
    
    # 验证没了
    get_exp = await client.get(f"/evaluation/experiments/{exp_id}")
    assert get_exp.status_code == 404
    
    # 5. 再次创建一个 Experiment，用于测试删除 Testset 时的级联删除
    exp_res_2 = await client.post("/evaluation/experiments", json={
        "knowledge_id": kb_id,
        "testset_id": ts_id,
        "runtime_params": {"top_k": 1}
    })
    exp_id_2 = exp_res_2.json()
    
    # 6. 删除 Testset
    del_ts = await client.delete(f"/evaluation/testsets/{ts_id}")
    assert del_ts.status_code == 200
    
    # 7. 验证 Testset 没了
    get_ts_2 = await client.get(f"/evaluation/testsets/{ts_id}")
    assert get_ts_2.status_code == 404
    
    # 8. 【关键】验证 Experiment 2 也被级联删除了
    get_exp_2 = await client.get(f"/evaluation/experiments/{exp_id_2}")
    assert get_exp_2.status_code == 404
    
    # 清理 Knowledge
    await client.delete(f"/knowledge/knowledges/{kb_id}")