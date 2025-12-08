from typing import Optional
from pydantic import BaseModel, EmailStr
from app.domain.models.user import UserPlan

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
    is_superuser: bool = False 

    plan: UserPlan
    daily_request_limit: int
    daily_token_limit: int