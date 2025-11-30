import logging
from typing import Sequence
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession  # 🟢 引入 AsyncSession

from arq import create_pool
from arq.connections import RedisSettings

from app.api import deps
from app.core.config import settings
from app.domain.models import (Knowledge,
                               KnowledgeCreate,
                               KnowledgeRead,
                               KnowledgeUpdate,
                               KnowledgeStatus,
                               Document,
                               DocStatus)

from app.services.knowledge import knowledge_crud
from app.services.minio.file_storage import save_upload_file
from app.services.knowledge.document_crud import delete_document_and_vectors


logger = logging.getLogger(__name__)
router = APIRouter()

# ------------------ Knowledge base management ------------------

@router.post("/knowledges", response_model=KnowledgeRead)
async def handle_create_knowledge(
    *, # 强制关键字参数
    knowledge_in: KnowledgeCreate,
    db: AsyncSession = Depends(deps.get_db_session), # 🟢 类型提示变更
):
    # 🟢 增加 await
    return await knowledge_crud.create_knowledge(db, knowledge_in)

@router.get("/knowledges", response_model=Sequence[KnowledgeRead])
async def handle_get_all_knowledges(
    db: AsyncSession = Depends(deps.get_db_session),
    skip: int = 0,
    limit: int = 100,
):
    # 🟢 增加 await
    return await knowledge_crud.get_all_knowledges(db=db, skip=skip, limit=limit)

@router.get("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
async def handle_get_knowledge_by_id(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
):
    # 🟢 增加 await
    return await knowledge_crud.get_knowledge_by_id(db=db, knowledge_id=knowledge_id)

@router.put("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
async def handle_update_knowledge(
    knowledge_id: int,
    knowledge_in: KnowledgeUpdate,
    db: AsyncSession = Depends(deps.get_db_session),
):
    # 🟢 增加 await
    return await knowledge_crud.update_knowledge(db=db, knowledge_id=knowledge_id, knowledge_to_update=knowledge_in)

@router.delete("/knowledges/{knowledge_id}")
async def handle_delete_knowledge(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
):
    """
    异步删除知识库，并级联删除其下所有文档和向量。
    """
    # 1. 查出知识库 (🟢 await)
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="知识库不存在")
    
    # 立即标记为 DELETING
    knowledge.status = KnowledgeStatus.DELETING
    db.add(knowledge) # 内存操作，不需要 await
    await db.commit() # 🟢 await
    # 状态更新不需要 refresh，因为直接返回 message

    # 2. 推送任务到 Redis (Arq 已经是异步的，保持现状)
    try:
        redis = await create_pool(RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT))
        await redis.enqueue_job("delete_knowledge_task", knowledge_id)
        await redis.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务入队失败: {str(e)}")

    # 3. 立即返回，不等待删除完成
    return {"message": f"知识库 {knowledge.name} 删除任务已提交后台处理。"}

# 获取指定知识库下的所有文档
@router.get("/knowledges/{knowledge_id}/documents", response_model=Sequence[Document])
async def handle_get_knowledge_documents(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
):
    # 检查知识库是否存在 (🟢 await)
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="知识库不存在")
    
    # 查询文档
    statement = (
        select(Document)
        .where(Document.knowledge_base_id == knowledge_id)
        .order_by(desc(Document.created_at))
    )
    # 🟢 异步执行查询: (await db.exec(...)).all()
    result = await db.exec(statement)
    return result.all()

# ------------------- Document management ------------------

@router.post("/{knowledge_id}/upload", response_model=int)
async def upload_file(
        knowledge_id: int,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(deps.get_db_session),
    ):

    # 检查知识库是否存在
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="知识库不存在")
    
    # 使用 HTTP 409 Conflict 状态码表示状态冲突
    if knowledge.status == KnowledgeStatus.DELETING:
        raise HTTPException(
            status_code=409, 
            detail=f"知识库 '{knowledge.name}' 正在删除中，无法上传新文件。"
        )
    
    try:
        saved_path = await run_in_threadpool(save_upload_file, file, knowledge_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")
    
    file_name = file.filename
    if not file_name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    doc = Document(
        knowledge_base_id=knowledge_id,
        filename=file_name,
        file_path=saved_path,
        status=DocStatus.PENDING,
    )

    db.add(doc)
    await db.commit() # 🟢 await
    await db.refresh(doc) # 🟢 await
    
    # 推送任务到 redis
    try:
        redis = await create_pool(RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT))
        
        # 检查文件后缀
        suffix = Path(file_name).suffix.lower()
        if suffix in [".pdf", ".docx", ".doc"]:
            # 路由到 Docling 专用队列 (GPU Worker)
            logger.info(f"文件 {file_name} 为复杂文档，路由至 {settings.DOCLING_QUEUE_NAME}")
            await redis.enqueue_job(
                "process_document_task", 
                doc.id, 
                _queue_name=settings.DOCLING_QUEUE_NAME
            )
        else:
            # 路由到默认队列 (CPU Worker)
            logger.info(f"文件 {file_name} 为普通文档，路由至 {settings.DEFAULT_QUEUE_NAME}")
            await redis.enqueue_job(
                "process_document_task", 
                doc.id,
                _queue_name=settings.DEFAULT_QUEUE_NAME
            )
            
        await redis.close()
    except Exception as e:
        doc.status = DocStatus.FAILED
        doc.error_message = f"推送任务到 Redis 失败: {str(e)}"
        db.add(doc)
        await db.commit() # 🟢 await
        raise HTTPException(status_code=500, detail=f"推送任务到 Redis 失败: {str(e)}")
    
    return doc.id
    
@router.delete("/documents/{doc_id}")
async def handle_delete_document(
    doc_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
):
    """
    删除指定文档及其在向量库中的所有切片。
    """
    try:
        # 调用复杂的服务逻辑，它负责原子删除 (🟢 await)
        return await delete_document_and_vectors(db=db, doc_id=doc_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

# 查询单个文档详情 (用于前端轮询状态)
@router.get("/documents/{doc_id}", response_model=Document)
async def handle_get_document(
    doc_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
):
    # 🟢 await
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc