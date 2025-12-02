# tests/services/ingestion/test_knowledge_crud_m2m.py
import pytest
import pytest_asyncio # 🟢
from sqlmodel import select
from app.domain.models import User, Knowledge, KnowledgeCreate, UserKnowledgeLink, UserKnowledgeRole
from app.services.knowledge import knowledge_crud

# 🟢 改为 pytest_asyncio.fixture
@pytest_asyncio.fixture
async def user_a(db_session):
    user = User(email="user_a@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

# 🟢 改为 pytest_asyncio.fixture
@pytest_asyncio.fixture
async def user_b(db_session):
    user = User(email="user_b@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.mark.asyncio
async def test_create_knowledge_creates_link(db_session, user_a):
    kb_in = KnowledgeCreate(name="User A's KB")
    
    kb = await knowledge_crud.create_knowledge(db_session, kb_in, user_a.id)
    
    assert kb.id is not None
    assert kb.name == "User A's KB"
    
    link_stmt = select(UserKnowledgeLink).where(
        UserKnowledgeLink.user_id == user_a.id,
        UserKnowledgeLink.knowledge_id == kb.id
    )
    result = await db_session.exec(link_stmt)
    link = result.first()
    
    assert link is not None
    assert link.role == UserKnowledgeRole.OWNER

@pytest.mark.asyncio
async def test_get_knowledges_isolation(db_session, user_a, user_b):
    await knowledge_crud.create_knowledge(db_session, KnowledgeCreate(name="KB A1"), user_a.id)
    await knowledge_crud.create_knowledge(db_session, KnowledgeCreate(name="KB A2"), user_a.id)
    await knowledge_crud.create_knowledge(db_session, KnowledgeCreate(name="KB B1"), user_b.id)
    
    kbs_a = await knowledge_crud.get_all_knowledges(db_session, user_a.id)
    assert len(kbs_a) == 2
    assert all(k.name in ["KB A1", "KB A2"] for k in kbs_a)
    
    kbs_b = await knowledge_crud.get_all_knowledges(db_session, user_b.id)
    assert len(kbs_b) == 1
    assert kbs_b[0].name == "KB B1"

@pytest.mark.asyncio
async def test_get_knowledge_by_id_auth(db_session, user_a, user_b):
    kb = await knowledge_crud.create_knowledge(db_session, KnowledgeCreate(name="Auth KB"), user_a.id)
    
    found_kb = await knowledge_crud.get_knowledge_by_id(db_session, kb.id, user_a.id)
    assert found_kb.id == kb.id
    
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await knowledge_crud.get_knowledge_by_id(db_session, kb.id, user_b.id)
    assert exc.value.status_code == 404