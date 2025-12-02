import pytest
from app.core.config import settings
from app.domain.models.user import User

def test_security_config_loaded():
    """
    验证核心安全配置项是否已加载
    """
    assert hasattr(settings, "SECRET_KEY"), "缺少 SECRET_KEY 配置"
    assert hasattr(settings, "ALGORITHM"), "缺少 ALGORITHM 配置"
    assert hasattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES"), "缺少 Token 过期时间配置"
    
    # 验证默认值或加载值
    assert settings.ALGORITHM == "HS256"
    assert isinstance(settings.ACCESS_TOKEN_EXPIRE_MINUTES, int)

def test_user_model_structure():
    """
    验证 User 模型是否包含必要的鉴权字段
    """
    user = User(
        email="test@example.com",
        hashed_password="hashed_secret",
        full_name="Test User"
    )
    
    assert user.email == "test@example.com"
    assert user.is_active is True  # 默认应为激活
    assert user.is_superuser is False # 默认不应为管理员
    assert user.hashed_password == "hashed_secret"