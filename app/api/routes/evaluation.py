# app/api/routes/evaluation.py
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select, desc
from arq import create_pool
from arq.connections import RedisSettings

from app.api import deps
from app.core.config import settings
from app.domain.models import (
    Testset, Experiment, Knowledge, Document
)
from pydantic import BaseModel

router = APIRouter()

# --- Schemas (临时定义在这里，也可移到 domain/schemas) ---
class TestsetCreateRequest(BaseModel):
    name: str
    source_doc_ids: List[int] # 基于哪些文档生成

class ExperimentCreateRequest(BaseModel):
    knowledge_id: int
    testset_id: int
    runtime_params: Dict[str, Any] = {} # {"top_k": 3, "strategy": "hybrid"}

# -------------------------------------------------------
# 1. Testset 管理
# -------------------------------------------------------

@router.post("/testsets", response_model=int)
async def create_generation_task(
    req: TestsetCreateRequest,
    db: Session = Depends(deps.get_db_session)
):
    """
    提交一个测试集生成任务
    """
    # 1. 创建数据库记录 (占位)
    testset = Testset(
        name=req.name,
        file_path="", # 暂时为空，Worker 生成后会更新
        description="Generating...",
        status="GENERATING"
    )
    db.add(testset)
    db.commit()
    db.refresh(testset)

    # 2. 推送任务到 Redis
    try:
        redis = await create_pool(RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT))
        # 注意：这里传递的是 list[int]，Worker 那边要能接收
        await redis.enqueue_job("generate_testset_task", testset.id, req.source_doc_ids)
        await redis.close()
    except Exception as e:
        # 回滚
        db.delete(testset)
        db.commit()
        raise HTTPException(status_code=500, detail=f"任务入队失败: {str(e)}")

    return testset.id

@router.get("/testsets", response_model=List[Testset])
def get_testsets(db: Session = Depends(deps.get_db_session)):
    return db.exec(select(Testset).order_by(desc(Testset.created_at))).all()

@router.get("/testsets/{testset_id}", response_model=Testset)
def get_testset(
    testset_id: int,
    db: Session = Depends(deps.get_db_session)
):
    """
    [新增] 获取单个测试集详情，用于前端轮询状态
    """
    ts = db.get(Testset, testset_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Testset not found")
    return ts

# -------------------------------------------------------
# 2. Experiment 管理
# -------------------------------------------------------

@router.post("/experiments", response_model=int)
async def create_experiment_task(
    req: ExperimentCreateRequest,
    db: Session = Depends(deps.get_db_session)
):
    """
    提交一个评测实验任务
    """
    # 校验 KB 和 Testset 是否存在
    kb = db.get(Knowledge, req.knowledge_id)
    ts = db.get(Testset, req.testset_id)
    if not kb or not ts:
        raise HTTPException(status_code=404, detail="Knowledge or Testset not found")

    # 1. 创建实验记录
    exp = Experiment(
        knowledge_id=req.knowledge_id,
        testset_id=req.testset_id,
        runtime_params=req.runtime_params,
        status="PENDING"
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)

    # 2. 推送任务
    try:
        redis = await create_pool(RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT))
        await redis.enqueue_job("run_experiment_task", exp.id)
        await redis.close()
    except Exception as e:
        exp.status = "FAILED"
        exp.error_message = str(e)
        db.add(exp)
        db.commit()
        raise HTTPException(status_code=500, detail=f"任务入队失败: {str(e)}")

    return exp.id

@router.get("/experiments", response_model=List[Experiment])
def get_experiments(
    knowledge_id: Optional[int],
    db: Session = Depends(deps.get_db_session)
):
    """
    获取实验列表，支持按 Knowledge ID 筛选（画图用）
    """
    query = select(Experiment)
    if knowledge_id:
        query = query.where(Experiment.knowledge_id == knowledge_id)
    
    query = query.order_by(desc(Experiment.created_at))
    return db.exec(query).all()

@router.get("/experiments/{experiment_id}", response_model=Experiment)
def get_experiment(
    experiment_id: int,
    db: Session = Depends(deps.get_db_session)
):
    """
    获取单个实验详情，用于前端轮询
    """
    exp = db.get(Experiment, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp