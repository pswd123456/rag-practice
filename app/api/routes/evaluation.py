# app/api/routes/evaluation.py

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from arq import ArqRedis 

from app.api import deps
from app.core.config import settings
from app.domain.models import (
    Testset, Experiment, Knowledge
)
from pydantic import BaseModel

from app.services.evaluation import evaluation_crud

router = APIRouter()

# --- Schemas ---
class TestsetCreateRequest(BaseModel):
    name: str
    source_doc_ids: List[int]
    generator_llm: str = "qwen-max" 

class ExperimentCreateRequest(BaseModel):
    knowledge_id: int
    testset_id: int
    runtime_params: Dict[str, Any] = {} 

# -------------------------------------------------------
# 1. Testset 管理
# -------------------------------------------------------

@router.post("/testsets", response_model=int)
async def create_generation_task(
    req: TestsetCreateRequest,
    db: AsyncSession = Depends(deps.get_db_session),
    redis: ArqRedis = Depends(deps.get_redis_pool), # 🟢 注入 Redis
):
    """
    提交一个测试集生成任务
    """
    testset = Testset(
        name=req.name,
        file_path="", 
        description=f"Generating with {req.generator_llm}...",
        status="GENERATING"
    )
    db.add(testset)
    await db.commit()
    await db.refresh(testset)

    try:
        # 🟢 优化：复用连接池
        await redis.enqueue_job("generate_testset_task", testset.id, req.source_doc_ids, req.generator_llm)
    except Exception as e:
        await db.delete(testset)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"任务入队失败: {str(e)}")

    return testset.id

@router.get("/testsets", response_model=List[Testset])
async def get_testsets(db: AsyncSession = Depends(deps.get_db_session)):
    # 🟢 异步查询
    result = await db.exec(select(Testset).order_by(desc(Testset.created_at)))
    return result.all()

@router.get("/testsets/{testset_id}", response_model=Testset)
async def get_testset(
    testset_id: int,
    db: AsyncSession = Depends(deps.get_db_session)
):
    ts = await db.get(Testset, testset_id) # 🟢 await
    if not ts:
        raise HTTPException(status_code=404, detail="Testset not found")
    return ts

@router.delete("/testsets/{testset_id}")
async def delete_testset_endpoint(
    testset_id: int,
    db: AsyncSession = Depends(deps.get_db_session)
):
    # 🟢 await CRUD
    return await evaluation_crud.delete_testset(db, testset_id)

# -------------------------------------------------------
# 2. Experiment 管理
# -------------------------------------------------------

@router.post("/experiments", response_model=int)
async def create_experiment_task(
    req: ExperimentCreateRequest,
    db: AsyncSession = Depends(deps.get_db_session),
    redis: ArqRedis = Depends(deps.get_redis_pool), # 🟢 注入 Redis
):
    """
    提交一个评测实验任务
    """
    kb = await db.get(Knowledge, req.knowledge_id)
    ts = await db.get(Testset, req.testset_id)
    if not kb or not ts:
        raise HTTPException(status_code=404, detail="Knowledge or Testset not found")

    exp = Experiment(
        knowledge_id=req.knowledge_id,
        testset_id=req.testset_id,
        runtime_params=req.runtime_params,
        status="PENDING"
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)

    try:
        # 🟢 优化：复用连接池
        await redis.enqueue_job("run_experiment_task", exp.id)
    except Exception as e:
        exp.status = "FAILED"
        exp.error_message = str(e)
        db.add(exp)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"任务入队失败: {str(e)}")

    return exp.id

@router.get("/experiments", response_model=List[Experiment])
async def get_experiments(
    knowledge_id: Optional[int],
    db: AsyncSession = Depends(deps.get_db_session)
):
    query = select(Experiment)
    if knowledge_id:
        query = query.where(Experiment.knowledge_id == knowledge_id)
    
    query = query.order_by(desc(Experiment.created_at))
    # 🟢 异步查询
    result = await db.exec(query)
    return result.all()

@router.get("/experiments/{experiment_id}", response_model=Experiment)
async def get_experiment(
    experiment_id: int,
    db: AsyncSession = Depends(deps.get_db_session)
):
    exp = await db.get(Experiment, experiment_id) # 🟢 await
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp

@router.delete("/experiments/{experiment_id}")
async def delete_experiment_endpoint(
    experiment_id: int,
    db: AsyncSession = Depends(deps.get_db_session)
):
    # 🟢 await CRUD
    return await evaluation_crud.delete_experiment(db, experiment_id)