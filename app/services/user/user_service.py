from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domain.models.user import User, UserPlan
from app.core.config import settings
from app.core.security import get_password_hash, verify_password

class UserService:
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        statement = select(User).where(User.email == email)
        result = await db.exec(statement)
        return result.first()

    @staticmethod
    async def create_user(
        db: AsyncSession, 
        email: str, 
        password: str, 
        full_name: str = None,
        plan: UserPlan = UserPlan.FREE
    ) -> User:
        hashed = get_password_hash(password)

        plan_config = settings.PLANS.get(plan.value, settings.PLANS["FREE"])
        
        db_obj = User(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            is_active=True,
            plan=plan,
            daily_request_limit=plan_config["daily_request_limit"],
            daily_token_limit=plan_config["daily_token_limit"]
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> Optional[User]:
        """
        验证用户凭证，成功返回 User 对象，失败返回 None
        """
        user = await UserService.get_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    @staticmethod
    async def upgrade_plan(db: AsyncSession, user_id: int, new_plan: UserPlan) -> User:
        """
        升级用户套餐
        """
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
            
        plan_config = settings.PLANS.get(new_plan.value)
        if not plan_config:
            raise ValueError(f"Invalid plan: {new_plan}")
            
        user.plan = new_plan
        user.daily_request_limit = plan_config["daily_request_limit"]
        user.daily_token_limit = plan_config["daily_token_limit"]
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user