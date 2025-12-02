from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.services.user.user_service import UserService
from app.domain.schemas import Token, UserRead, UserCreate
from app.domain.models import User

router = APIRouter()

@router.post("/access-token", response_model=Token)
async def login_access_token(
    db: AsyncSession = Depends(deps.get_db_session),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Any:
    """
    OAuth2 兼容的 Token 登录接口，获取 Access Token
    """
    user = await UserService.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Incorrect email or password"
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token = create_access_token(subject=user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/test-token", response_model=UserRead)
async def test_token(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    测试 Token 有效性，返回当前用户信息
    """
    return current_user

@router.post("/register", response_model=UserRead)
async def register_user(
    *,
    db: AsyncSession = Depends(deps.get_db_session),
    user_in: UserCreate,
) -> Any:
    """
    开放注册接口
    """
    user = await UserService.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    user = await UserService.create_user(
        db, email=user_in.email, password=user_in.password, full_name=user_in.full_name
    )
    return user