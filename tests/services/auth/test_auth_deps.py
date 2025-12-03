import pytest
from fastapi import HTTPException, status
from unittest.mock import MagicMock, AsyncMock, patch
from jose import jwt

from app.api import deps
from app.core.config import settings
from app.domain.models.user import User

# 构造一个测试用的 Token
def create_test_token(sub: str):
    to_encode = {"sub": sub}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

@pytest.mark.asyncio
async def test_get_current_user_valid(db_session):
    """
    [Unit] 测试有效 Token 能成功解析出用户
    """
    # 1. 准备 Mock 数据
    user_id = 123
    mock_user = User(id=user_id, email="valid@test.com", is_active=True)
    token = create_test_token(str(user_id))
    
    # 2. Mock 数据库查询 (db.get)
    # 注意：deps.get_current_user 内部会调用 db.get(User, user_id)
    with patch.object(db_session, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_user
        
        # 3. 执行依赖函数
        user = await deps.get_current_user(token, db_session)
        
        # 4. 验证
        assert user.id == user_id
        assert user.email == "valid@test.com"
        mock_get.assert_called_once()

@pytest.mark.asyncio
async def test_get_current_user_invalid_token(db_session):
    """
    [Unit] 测试无效 Token 抛出异常
    """
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_user("invalid.token.string", db_session)
    
    # [Fix] 无效 Token 应返回 401 Unauthorized，而非 403 Forbidden
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.asyncio
async def test_get_current_user_not_found(db_session):
    """
    [Unit] 测试 Token 有效但数据库无此人 (如已销号)
    """
    token = create_test_token("999")
    
    with patch.object(db_session, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None # 模拟没找到
        
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user(token, db_session)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_get_current_active_user_inactive():
    """
    [Unit] 测试非活跃用户被拦截
    """
    inactive_user = User(id=1, email="banned@test.com", is_active=False)
    
    with pytest.raises(HTTPException) as exc:
        deps.get_current_active_user(inactive_user)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST