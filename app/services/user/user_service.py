from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domain.models.user import User
from app.core.security import get_password_hash, verify_password

class UserService:
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        statement = select(User).where(User.email == email)
        result = await db.exec(statement)
        return result.first()

    @staticmethod
    async def create_user(db: AsyncSession, email: str, password: str, full_name: str = None) -> User:
        hashed = get_password_hash(password)
        db_obj = User(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            is_active=True
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