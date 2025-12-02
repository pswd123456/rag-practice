# tests/api/test_api_consistency.py
import pytest
from unittest.mock import MagicMock
from app.domain.models import Knowledge, KnowledgeStatus, User, UserKnowledgeLink, UserKnowledgeRole
from app.core.security import create_access_token

@pytest.mark.asyncio
async def test_delete_knowledge_redis_failure_recovery(async_client, db_session, mock_redis):
    """
    [Consistency Test]
    验证当 Redis 入队失败时，API 是否能将 Knowledge 状态从 DELETING 回滚/更新为 FAILED。
    """
    # 1. 准备数据 (User + KB + Link)
    user = User(email="consistency@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    kb = Knowledge(name="Consistency Test KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    link = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.OWNER)
    db_session.add(link)
    await db_session.commit()

    # 2. 生成 Token Header
    token = create_access_token(subject=user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # 3. 模拟 Redis 故障
    mock_redis.enqueue_job.side_effect = Exception("Redis Connection Timeout")

    # 4. 发起删除请求
    response = await async_client.delete(f"/knowledge/knowledges/{kb.id}", headers=headers)

    # 5. 验证 API 响应
    assert response.status_code == 500
    assert "任务入队失败" in response.json()["detail"]

    # 6. 验证状态
    await db_session.refresh(kb)
    assert kb.status == KnowledgeStatus.FAILED, \
        f"Redis 失败后，Knowledge 状态应置为 FAILED，实际为 {kb.status}"