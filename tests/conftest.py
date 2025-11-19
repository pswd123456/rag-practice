import pytest
import pytest_asyncio
import uuid # 记得导入 uuid
from httpx import AsyncClient, ASGITransport
from app.main import app

# 👈 2. 使用 pytest_asyncio.fixture 替代 pytest.fixture
# 这样即使在 strict 模式下，它也能被正确识别为异步 fixture
@pytest_asyncio.fixture(scope="function")
async def client():
    """
    创建一个异步的 HTTP 客户端。
    """
    # 使用 app=app 直接挂载，绕过网络层
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

def get_random_suffix():
    return uuid.uuid4().hex[:8]
@pytest_asyncio.fixture(scope="function")
async def temp_kb(client):
    # --- Setup ---
    random_name = f"test_kb_{get_random_suffix()}"
    payload = {"name": random_name, "description": "Auto-created by pytest"}
    
    response = await client.post("/knowledge/knowledges", json=payload)
    assert response.status_code == 200
    kb_id = response.json()["id"]
    
    # --- Yield ---
    yield kb_id

    # --- Teardown ---
    await client.delete(f"/knowledge/knowledges/{kb_id}")