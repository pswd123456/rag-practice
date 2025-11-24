from sqlmodel import Session
from fastapi import HTTPException
import logging

from app.domain.models import Testset, Experiment
from app.services.file_storage import delete_file_from_minio

logger = logging.getLogger(__name__)

def delete_experiment(db: Session, experiment_id: int) -> bool:
    """
    删除单个实验记录
    """
    exp = db.get(Experiment, experiment_id)
    if not exp:
        logger.warning(f"尝试删除不存在的实验 ID: {experiment_id}")
        raise HTTPException(status_code=404, detail="Experiment not found")

    try:
        db.delete(exp)
        db.commit()
        logger.info(f"实验 ID {experiment_id} 删除成功")
        return True
    except Exception as e:
        logger.error(f"删除实验失败: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete experiment failed: {str(e)}")

def delete_testset(db: Session, testset_id: int) -> bool:
    """
    删除测试集，并级联删除：
    1. MinIO 中的测试集文件
    2. 关联的所有 Experiment 记录 (手动级联)
    3. Testset 数据库记录
    """
    testset = db.get(Testset, testset_id)
    if not testset:
        logger.warning(f"尝试删除不存在的测试集 ID: {testset_id}")
        raise HTTPException(status_code=404, detail="Testset not found")

    try:
        # 1. 手动级联删除关联的实验 (避免外键约束报错)
        # 注意：SQLModel 的 relationship 默认不带 ON DELETE CASCADE，需手动处理或在 DB 层配置
        # 这里采用手动处理以保证逻辑清晰
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
        db.commit()
        
        logger.info(f"测试集 {testset_id} 及其关联数据删除成功")
        return True

    except Exception as e:
        logger.error(f"删除测试集失败: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete testset failed: {str(e)}")