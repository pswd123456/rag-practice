import pytest
import asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.domain.models import Knowledge

@pytest.mark.asyncio
async def test_async_session_is_really_async(db: AsyncSession):
    """
    验证 DB Session 确实是异步的，并且可以并发执行查询。
    """
    # 1. 验证类型
    assert isinstance(db, AsyncSession), "Fixture should yield an AsyncSession"

    # 2. 插入数据
    kb1 = Knowledge(name="AsyncKB_1", description="Test 1")
    kb2 = Knowledge(name="AsyncKB_2", description="Test 2")
    db.add(kb1)
    db.add(kb2)
    await db.commit()

    # 3. 验证并发查询能力
    # 同时发起两个查询，看是否能正确 await
    async def get_kb_name(kb_id):
        k = await db.get(Knowledge, kb_id)
        return k.name

    results = await asyncio.gather(
        get_kb_name(kb1.id),
        get_kb_name(kb2.id)
    )

    assert "AsyncKB_1" in results
    assert "AsyncKB_2" in results