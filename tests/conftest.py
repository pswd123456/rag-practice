import pytest
import pytest_asyncio  # 👈 1. 新增导入
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