from jose import jwt
from app.core.config import settings
# 注意：虽然 security 模块还没创建，我们先写引用，这是 TDD 的标准流程
from app.core.security import create_access_token, verify_password, get_password_hash

def test_password_hashing():
    """
    验证密码哈希逻辑：
    1. 验证通过
    2. 验证失败
    3. 哈希值不等于原密码
    """
    password = "my_super_secret_password"
    hashed = get_password_hash(password)
    
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)
    assert hashed != password

def test_access_token_creation():
    """
    验证 JWT 生成逻辑：
    1. 生成 Token
    2. 解码 Token 验证 Subject (用户标识)
    3. 验证包含过期时间 (exp)
    """
    user_identity = "user@example.com"
    token = create_access_token(subject=user_identity)
    
    # 使用相同的密钥解码验证
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    
    assert payload["sub"] == user_identity
    assert "exp" in payload