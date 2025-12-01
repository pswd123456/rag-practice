import pytest
from sqlmodel import select
from app.domain.models import Document, DocStatus, Testset, Experiment, Knowledge, KnowledgeStatus
from app.worker import check_and_fix_zombie_tasks

@pytest.mark.asyncio
async def test_worker_recovery_logic(db_session):
    """
    [Integration] 验证 Worker 启动时的僵尸任务清理逻辑
    """
    # 1. 准备处于 "中间状态" 的脏数据
    
    # Zombie Document
    kb = Knowledge(name="Zombie KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    
    doc = Document(
        knowledge_base_id=kb.id,
        filename="zombie.pdf",
        file_path="1/zombie.pdf",
        status=DocStatus.PROCESSING # 模拟正在处理
    )
    db_session.add(doc)
    
    # Zombie Testset
    ts = Testset(
        name="Zombie TS",
        file_path="",
        status="GENERATING" # 模拟正在生成
    )
    db_session.add(ts)
    
    # Zombie Experiment
    # 需要先关联 Knowledge 和 Testset
    exp = Experiment(
        knowledge_id=kb.id,
        testset_id=ts.id, # 这里临时用一下，虽然 TS 还没 commit，但 session 内可见
        status="RUNNING" # 模拟正在运行
    )
    db_session.add(exp)

    # Zombie Knowledge Deletion
    kb_del = Knowledge(name="Deleting KB", status=KnowledgeStatus.DELETING)
    db_session.add(kb_del)
    
    await db_session.commit()
    
    # 记录 IDs
    doc_id = doc.id
    ts_id = ts.id
    exp_id = exp.id
    kb_del_id = kb_del.id

    # 2. 执行恢复逻辑 (模拟 Worker 启动)
    # 我们直接传入 db_session 来模拟 worker 内部获取 session 的行为
    # 注意：实际 worker 代码会自己创建 session，这里为了测试方便，我们让函数支持传入 session，或者我们 mock session_maker
    
    # 这里的 check_and_fix_zombie_tasks 还没写，我们先约定它的行为。
    # 为了测试方便，我们假设它可以接受外部 session，或者我们在 app.worker 里重构一下
    
    # 实际上 check_and_fix_zombie_tasks 内部是 `async with async_session_maker() as db:`
    # 我们需要 Mock async_session_maker 或者让该函数接受可选参数 db
    
    # 在此测试中，我们直接调用逻辑的核心部分，或者 Mock app.worker.async_session_maker
    from unittest.mock import MagicMock, patch
    
    # Mock 上下文管理器
    mock_db_ctx = MagicMock()
    mock_db_ctx.__aenter__.return_value = db_session
    mock_db_ctx.__aexit__.return_value = None
    
    with patch("app.worker.async_session_maker", return_value=mock_db_ctx):
        await check_and_fix_zombie_tasks()

    # 3. 验证状态是否已重置
    
    # 验证 Document
    new_doc = await db_session.get(Document, doc_id)
    assert new_doc.status == DocStatus.FAILED
    assert "系统重启" in new_doc.error_message
    
    # 验证 Testset
    new_ts = await db_session.get(Testset, ts_id)
    assert new_ts.status == "FAILED"
    assert "系统重启" in new_ts.error_message
    
    # 验证 Experiment
    new_exp = await db_session.get(Experiment, exp_id)
    assert new_exp.status == "FAILED"
    assert "系统重启" in new_exp.error_message

    # 验证 Knowledge
    new_kb_del = await db_session.get(Knowledge, kb_del_id)
    assert new_kb_del.status == KnowledgeStatus.FAILED