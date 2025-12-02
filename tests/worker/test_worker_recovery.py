import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import select
from app.domain.models import Document, DocStatus, Testset, Experiment, Knowledge, KnowledgeStatus
from app.worker import check_and_fix_zombie_tasks

@pytest.mark.asyncio
async def test_worker_recovery_logic(db_session):
    """
    [Integration] 验证 Worker 启动时的僵尸任务清理逻辑
    """
    # 1. 准备处于 "中间状态" 的脏数据
    
    # Zombie Knowledge (用于关联 Document 和 Experiment)
    kb = Knowledge(name="Zombie KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    # Zombie Document
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
    
    # 🟢 [FIX] 关键修复：必须先提交并刷新，让 DB 生成 ID，否则 ts.id 为 None
    await db_session.commit()
    await db_session.refresh(ts)
    
    # Zombie Experiment
    exp = Experiment(
        knowledge_id=kb.id,
        testset_id=ts.id, # 现在 ts.id 有值了
        status="RUNNING" # 模拟正在运行
    )
    db_session.add(exp)

    # Zombie Knowledge Deletion
    kb_del = Knowledge(name="Deleting KB", status=KnowledgeStatus.DELETING)
    db_session.add(kb_del)
    
    await db_session.commit()
    
    # 记录 IDs 用于后续验证
    doc_id = doc.id
    ts_id = ts.id
    exp_id = exp.id
    kb_del_id = kb_del.id

    # 2. 执行恢复逻辑 (模拟 Worker 启动)
    # Mock app.worker.async_session_maker 以复用测试的 db_session
    mock_db_ctx = MagicMock()
    mock_db_ctx.__aenter__.return_value = db_session
    mock_db_ctx.__aexit__.return_value = None
    
    with patch("app.worker.async_session_maker", return_value=mock_db_ctx):
        await check_and_fix_zombie_tasks()

    # 3. 验证状态是否已重置
    
    # 验证 Document 被重置为 FAILED
    await db_session.refresh(doc)
    new_doc = await db_session.get(Document, doc_id)
    assert new_doc.status == DocStatus.FAILED
    assert "任务异常中断" in new_doc.error_message
    
    # 验证 Testset 被重置为 FAILED
    await db_session.refresh(ts)
    new_ts = await db_session.get(Testset, ts_id)
    assert new_ts.status == "FAILED"
    assert "任务异常中断" in new_ts.error_message
    
    # 验证 Experiment 被重置为 FAILED
    await db_session.refresh(exp)
    new_exp = await db_session.get(Experiment, exp_id)
    assert new_exp.status == "FAILED"
    assert "任务异常中断" in new_exp.error_message

    # 验证 Knowledge 被重置为 FAILED
    await db_session.refresh(kb_del)
    new_kb_del = await db_session.get(Knowledge, kb_del_id)
    assert new_kb_del.status == KnowledgeStatus.FAILED