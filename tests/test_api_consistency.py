# tests/test_api_consistency.py
import pytest
from unittest.mock import MagicMock
from app.domain.models import Knowledge, KnowledgeStatus

@pytest.mark.asyncio
async def test_delete_knowledge_redis_failure_recovery(async_client, db_session, mock_redis):
    """
    [Consistency Test]
    验证当 Redis 入队失败时，API 是否能将 Knowledge 状态从 DELETING 回滚/更新为 FAILED。
    """
    # 1. 准备数据
    kb = Knowledge(name="Consistency Test KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    kb_id = kb.id

    # 2. 模拟 Redis 故障
    mock_redis.enqueue_job.side_effect = Exception("Redis Connection Timeout")

    # 3. 发起删除请求
    response = await async_client.delete(f"/knowledge/knowledges/{kb_id}")

    # 4. 验证 API 响应
    assert response.status_code == 500
    assert "任务入队失败" in response.json()["detail"]

    # 5. [关键修复] 强制从数据库刷新对象状态
    # 因为 kb 对象已经在当前 session 的 identity map 中，get() 会直接返回缓存的旧对象
    # 必须使用 refresh() 强制发起 SELECT 查询
    await db_session.refresh(kb)
    
    print(f"\n[Test Debug] Current KB Status: {kb.status}")
    
    assert kb.status == KnowledgeStatus.FAILED, \
        f"Redis 失败后，Knowledge 状态应置为 FAILED，实际为 {kb.status}"