# app/db/init_db.py
import logging
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.services.user.user_service import UserService
from app.domain.models.user import UserPlan

logger = logging.getLogger(__name__)

async def init_db(db: AsyncSession) -> None:
    """
    初始化数据库数据：创建默认超级管理员
    """
    try:
        user = await UserService.get_by_email(db, email=settings.FIRST_SUPERUSER)
        if not user:
            logger.info(f"正在创建默认超级管理员: {settings.FIRST_SUPERUSER}")
            
            # 1. 使用 Service 创建基础用户 (会自动处理密码哈希)
            user = await UserService.create_user(
                db,
                email=settings.FIRST_SUPERUSER,
                password=settings.FIRST_SUPERUSER_PASSWORD,
                full_name="Initial Admin",
                plan=UserPlan.ENTERPRISE # 给管理员最高等级权限
            )
            
            # 2. 手动提升为超级管理员
            user.is_superuser = True
            db.add(user)
            await db.commit()
            await db.refresh(user)
            
            logger.info("✅ 默认超级管理员创建成功。")
        else:
            logger.info(f"超级管理员 {settings.FIRST_SUPERUSER} 已存在，跳过创建。")
            
    except Exception as e:
        logger.error(f"❌ 初始化数据库失败: {e}")
        # 不抛出异常，防止阻断服务启动