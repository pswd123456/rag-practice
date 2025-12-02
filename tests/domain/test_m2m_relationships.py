# tests/domain/test_m2m_relationships.py
import pytest
from sqlmodel import select
from app.domain.models import User, Knowledge, UserKnowledgeLink, UserKnowledgeRole, KnowledgeStatus

@pytest.mark.asyncio
async def test_user_knowledge_m2m_link(db_session):
    """
    [TDD] 验证 User 与 Knowledge 的 M:N 关系及 Role 字段
    """
    # 1. 创建 User
    user = User(email="owner@m2m.com", hashed_password="pw", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # 2. 创建 Knowledge (不再需要 user_id)
    # 注意：实际修改模型后，User 和 Knowledge 的构造函数会发生变化
    kb = Knowledge(name="Shared Team KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    # 3. 创建关联 (Link)
    link = UserKnowledgeLink(
        user_id=user.id,
        knowledge_id=kb.id,
        role=UserKnowledgeRole.OWNER
    )
    db_session.add(link)
    await db_session.commit()
    await db_session.refresh(link)

    # 4. 验证关联是否存在
    assert link.user_id == user.id
    assert link.knowledge_id == kb.id
    assert link.role == UserKnowledgeRole.OWNER

    # 5. 验证通过 User 查询 Knowledge (利用 SQLModel 的 Relationship)
    # 需要显式 refresh 加载关系
    await db_session.refresh(user, ["knowledges"])
    assert len(user.knowledges) == 1
    assert user.knowledges[0].name == "Shared Team KB"

    # 6. 验证通过 Knowledge 查询 User
    await db_session.refresh(kb, ["users"])
    assert len(kb.users) == 1
    assert kb.users[0].email == "owner@m2m.com"

@pytest.mark.asyncio
async def test_duplicate_link_constraint(db_session):
    """
    [TDD] 验证不能重复添加相同的 (user_id, knowledge_id) 对
    """
    user = User(email="user@test.com", hashed_password="pw")
    kb = Knowledge(name="Test KB")
    db_session.add(user)
    db_session.add(kb)
    await db_session.commit()

    link1 = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.EDITOR)
    db_session.add(link1)
    await db_session.commit()

    # 尝试添加重复链接
    link2 = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.VIEWER)
    db_session.add(link2)
    
    # 应该抛出 IntegrityError (Unique Constraint)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await db_session.commit()
    
    await db_session.rollback()