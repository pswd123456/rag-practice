from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
import logging

from app.domain.models import Testset, Experiment
from app.services.file_storage import delete_file_from_minio

logger = logging.getLogger(__name__)

async def delete_experiment(db: AsyncSession, experiment_id: int) -> bool:
    """
    删除单个实验记录 (异步版)
    """
    exp = await db.get(Experiment, experiment_id)
    if not exp:
        logger.warning(f"尝试删除不存在的实验 ID: {experiment_id}")
        raise HTTPException(status_code=404, detail="Experiment not found")

    try:
        db.delete(exp)
        await db.commit()
        logger.info(f"实验 ID {experiment_id} 删除成功")
        return True
    except Exception as e:
        logger.error(f"删除实验失败: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete experiment failed: {str(e)}")

async def delete_testset(db: AsyncSession, testset_id: int) -> bool:
    """
    删除测试集，并级联删除 (异步版)：
    1. MinIO 中的测试集文件
    2. 关联的所有 Experiment 记录 (手动级联)
    3. Testset 数据库记录
    """
    # ⚠️ 必须预加载 experiments 关系，否则访问 testset.experiments 会报错
    stmt = select(Testset).where(Testset.id == testset_id).options(selectinload(Testset.experiments))
    result = await db.exec(stmt)
    testset = result.first()
    
    if not testset:
        logger.warning(f"尝试删除不存在的测试集 ID: {testset_id}")
        raise HTTPException(status_code=404, detail="Testset not found")

    try:
        # 1. 手动级联删除关联的实验
        if testset.experiments:
            count = len(testset.experiments)
            logger.info(f"正在级联删除测试集 {testset_id} 关联的 {count} 个实验记录...")
            for exp in testset.experiments:
                db.delete(exp)
        
        # 2. 删除 MinIO 文件
        if testset.file_path:
            delete_file_from_minio(testset.file_path)

        # 3. 删除 Testset 记录
        db.delete(testset)
        await db.commit()
        
        logger.info(f"测试集 {testset_id} 及其关联数据删除成功")
        return True

    except Exception as e:
        logger.error(f"删除测试集失败: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete testset failed: {str(e)}")