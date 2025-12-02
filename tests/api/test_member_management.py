# tests/api/test_member_management.py
import pytest
import pytest_asyncio # 🟢
from httpx import AsyncClient
from app.domain.models import User, Knowledge, KnowledgeStatus, UserKnowledgeLink, UserKnowledgeRole
from app.core.security import create_access_token

# 🟢 改为 pytest_asyncio.fixture
@pytest_asyncio.fixture
async def setup_users_and_kb(db_session):
    # 1. 创建三个用户: Owner, Editor, Viewer, Stranger
    users = {}
    for role in ["owner", "editor", "viewer", "stranger"]:
        u = User(email=f"{role}@test.com", hashed_password="pw", is_active=True)
        db_session.add(u)
        await db_session.commit()
        await db_session.refresh(u)
        users[role] = u

    # 2. 创建 KB
    kb = Knowledge(name="Team KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    # 3. 建立 Link
    links = [
        UserKnowledgeLink(user_id=users["owner"].id, knowledge_id=kb.id, role=UserKnowledgeRole.OWNER),
        UserKnowledgeLink(user_id=users["editor"].id, knowledge_id=kb.id, role=UserKnowledgeRole.EDITOR),
        UserKnowledgeLink(user_id=users["viewer"].id, knowledge_id=kb.id, role=UserKnowledgeRole.VIEWER)
    ]
    for l in links:
        db_session.add(l)
    await db_session.commit()

    return users, kb

def get_auth_header(user):
    token = create_access_token(subject=user.id)
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_add_member_permission(async_client, setup_users_and_kb):
    users, kb = setup_users_and_kb
    
    # Editor 尝试添加成员 -> 403
    resp = await async_client.post(
        f"/knowledge/{kb.id}/members",
        json={"email": users["stranger"].email, "role": "VIEWER"},
        headers=get_auth_header(users["editor"])
    )
    assert resp.status_code == 403

    # Owner 尝试添加成员 -> 200
    resp = await async_client.post(
        f"/knowledge/{kb.id}/members",
        json={"email": users["stranger"].email, "role": "EDITOR"},
        headers=get_auth_header(users["owner"])
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "EDITOR"

@pytest.mark.asyncio
async def test_remove_member_permission(async_client, setup_users_and_kb):
    users, kb = setup_users_and_kb
    
    # Viewer 尝试移除 Editor -> 403
    resp = await async_client.delete(
        f"/knowledge/{kb.id}/members/{users['editor'].id}",
        headers=get_auth_header(users["viewer"])
    )
    assert resp.status_code == 403
    
    # Owner 移除 Editor -> 200
    resp = await async_client.delete(
        f"/knowledge/{kb.id}/members/{users['editor'].id}",
        headers=get_auth_header(users["owner"])
    )
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_upload_permission(async_client, setup_users_and_kb):
    users, kb = setup_users_and_kb
    
    files = {"file": ("test.txt", b"content", "text/plain")}
    
    # Viewer 上传 -> 403
    resp = await async_client.post(
        f"/knowledge/{kb.id}/upload",
        files=files,
        headers=get_auth_header(users["viewer"])
    )
    assert resp.status_code == 403

    # Editor 上传 -> 200
    files2 = {"file": ("test2.txt", b"content", "text/plain")}
    resp = await async_client.post(
        f"/knowledge/{kb.id}/upload",
        files=files2,
        headers=get_auth_header(users["editor"])
    )
    assert resp.status_code != 403