from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
import logging

from app.domain.models import Testset, Experiment
from app.services.minio.file_storage import delete_file_from_minio

logger = logging.getLogger(__name__)

async def delete_experiment(db: AsyncSession, experiment_id: int) -> bool:
    exp = await db.get(Experiment, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    try:
        await db.delete(exp)
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

async def delete_testset(db: AsyncSession, testset_id: int) -> bool:
    stmt = select(Testset).where(Testset.id == testset_id).options(selectinload(Testset.experiments))
    result = await db.exec(stmt)
    testset = result.first()
    
    if not testset:
        raise HTTPException(status_code=404, detail="Testset not found")

    try:
        if testset.experiments:
            for exp in testset.experiments:

                await db.delete(exp)
        
        if testset.file_path:
            delete_file_from_minio(testset.file_path)


        await db.delete(testset)
        await db.commit()
        return True

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))