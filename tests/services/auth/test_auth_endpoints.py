import pytest
from httpx import AsyncClient
from app.core.config import settings

@pytest.mark.asyncio
async def test_register_and_login_flow(async_client: AsyncClient, db_session):
    """
    [Integration] 测试完整的注册 -> 登录 -> 验权流程
    """
    email = "newuser@example.com"
    password = "strongpassword123"
    
    # 1. 注册 (Register)
    # 注意：为了简化，我们先直接在测试里创建用户，或者调用注册接口(如果实现了)
    # 这里我们测试注册接口
    reg_payload = {"email": email, "password": password, "full_name": "New User"}
    response = await async_client.post("/auth/register", json=reg_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert "id" in data

    # 2. 登录 (Login)
    # OAuth2 标准表单提交 (application/x-www-form-urlencoded)
    login_data = {
        "username": email, # OAuth2 规范字段名为 username
        "password": password
    }
    response = await async_client.post("/auth/access-token", data=login_data)
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    
    token = token_data["access_token"]

    # 3. 验证 Token (Test Token)
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.post("/auth/test-token", headers=headers)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == email

@pytest.mark.asyncio
async def test_login_wrong_password(async_client: AsyncClient, db_session):
    """
    [Integration] 测试错误密码
    """
    # 先注册
    await async_client.post("/auth/register", json={"email": "wrong@test.com", "password": "123"})
    
    # 尝试错误登录
    login_data = {"username": "wrong@test.com", "password": "wrongpassword"}
    response = await async_client.post("/auth/access-token", data=login_data)
    
    assert response.status_code == 400