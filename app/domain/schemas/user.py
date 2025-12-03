from typing import Optional
from pydantic import BaseModel, EmailStr

# 注册请求
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

# 用户信息响应 (不包含密码)
class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool = False # 🟢 Fix: 暴露管理员状态1