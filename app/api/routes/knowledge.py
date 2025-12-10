# app/api/routes/knowledge.py

import logging
from typing import Sequence, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession
from arq import ArqRedis

from app.api import deps
from app.core.config import settings
from app.domain.models import (Knowledge,
                               KnowledgeCreate,
                               KnowledgeRead,
                               KnowledgeUpdate,
                               KnowledgeStatus,
                               Document,
                               DocStatus,
                               User,
                               UserKnowledgeRole
                               )

from app.domain.schemas.knowledge_member import MemberAddRequest, MemberRead
from app.services.knowledge import knowledge_crud
from app.services.minio.file_storage import save_upload_file
from app.services.knowledge.document_crud import delete_document_and_vectors


logger = logging.getLogger(__name__)
router = APIRouter()

# -------------------------------------------------------
# Member Management
# -------------------------------------------------------

@router.post("/{knowledge_id}/members", response_model=MemberRead)
async def add_member_endpoint(
    knowledge_id: int,
    req: MemberAddRequest,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    """邀请新成员 (Owner only)"""
    return await knowledge_crud.add_member(
        db, knowledge_id, current_user.id, req.email, req.role
    )

@router.delete("/{knowledge_id}/members/{user_id}")
async def remove_member_endpoint(
    knowledge_id: int,
    user_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    """移除成员 (Owner only)"""
    await knowledge_crud.remove_member(db, knowledge_id, current_user.id, user_id)
    return {"message": "Member removed"}

@router.get("/{knowledge_id}/members", response_model=list[MemberRead])
async def get_members_endpoint(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
):
    """获取成员列表"""
    return await knowledge_crud.get_members(db, knowledge_id, current_user.id)

# ------------------ Knowledge base management ------------------

@router.post("/knowledges", response_model=KnowledgeRead)
async def handle_create_knowledge(
    *,
    knowledge_in: KnowledgeCreate,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user), # [New]
):
    """
    创建知识库 (绑定到当前用户)
    """
    return await knowledge_crud.create_knowledge(db, knowledge_in, user_id=current_user.id)

@router.get("/knowledges", response_model=Sequence[KnowledgeRead])
async def handle_get_all_knowledges(
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user), # [New]
    skip: int = 0,
    limit: int = 100,
):
    """
    获取当前用户的知识库列表
    """
    return await knowledge_crud.get_all_knowledges(db=db, user_id=current_user.id, skip=skip, limit=limit)

@router.get("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
async def handle_get_knowledge_by_id(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user), # [New]
):
    return await knowledge_crud.get_knowledge_by_id(db=db, knowledge_id=knowledge_id, user_id=current_user.id)

@router.put("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
async def handle_update_knowledge(
    knowledge_id: int,
    knowledge_in: KnowledgeUpdate,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user), # [New]
):
    return await knowledge_crud.update_knowledge(
        db=db, 
        knowledge_id=knowledge_id, 
        user_id=current_user.id, 
        knowledge_to_update=knowledge_in
    )

@router.delete("/knowledges/{knowledge_id}")
async def handle_delete_knowledge(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    redis: ArqRedis = Depends(deps.get_redis_pool),
    current_user: User = Depends(deps.get_current_active_user), # [New]
):
    """
    异步删除知识库
    """
   
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    await knowledge_crud.check_privilege(
        db, knowledge_id, current_user.id, 
        [UserKnowledgeRole.OWNER]
    )
    
    knowledge.status = KnowledgeStatus.DELETING
    db.add(knowledge)
    await db.commit()

    try:
        await redis.enqueue_job("delete_knowledge_task", knowledge_id, current_user.id)
    except Exception as e:
        logger.error(f"Redis Enqueue Failed: {e}")
        knowledge.status = KnowledgeStatus.FAILED
        db.add(knowledge)
        await db.commit()
        raise HTTPException(status_code=500, detail="任务入队失败")

    return {"message": f"知识库 {knowledge.name} 删除任务已提交。"}
# ------------------- Document management ------------------
@router.get("/knowledges/{knowledge_id}/documents", response_model=Sequence[Document])
async def handle_get_knowledge_documents(
    knowledge_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
):
 
    await knowledge_crud.get_knowledge_by_id(db, knowledge_id, current_user.id)
    
    statement = (
        select(Document)
        .where(Document.knowledge_base_id == knowledge_id)
        .order_by(desc(Document.created_at))
    )
    result = await db.exec(statement)
    return result.all()
@router.post("/{knowledge_id}/upload", response_model=int)
async def upload_file(
    knowledge_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_db_session),
    redis: ArqRedis = Depends(deps.get_redis_pool),
    current_user: User = Depends(deps.get_current_active_user), 
):
    # [RBAC Check] 只有 OWNER 或 EDITOR 可以上传
    await knowledge_crud.check_privilege(
        db, knowledge_id, current_user.id, 
        [UserKnowledgeRole.OWNER, UserKnowledgeRole.EDITOR]
    )
    
    # 校验权限
    knowledge = await knowledge_crud.get_knowledge_by_id(db, knowledge_id, current_user.id)
    
    if knowledge.status == KnowledgeStatus.DELETING:
        raise HTTPException(status_code=409, detail=f"知识库 '{knowledge.name}' 正在删除中。")
    
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
    await db.commit()
    await db.refresh(doc)
    
    try:
        suffix = Path(file_name).suffix.lower()
        if suffix in [".pdf", ".docx", ".doc"]:
            logger.info(f"文件 {file_name} 为复杂文档，路由至 {settings.DOCLING_QUEUE_NAME}")
            await redis.enqueue_job(
                "process_document_task", 
                doc.id, 
                _queue_name=settings.DOCLING_QUEUE_NAME
            )
        else:
            logger.info(f"文件 {file_name} 为普通文档，路由至 {settings.DEFAULT_QUEUE_NAME}")
            await redis.enqueue_job(
                "process_document_task", 
                doc.id,
                _queue_name=settings.DEFAULT_QUEUE_NAME
            )
            
    except Exception as e:
        logger.error(f"Job Enqueue Error: {e}")
        doc.status = DocStatus.FAILED
        doc.error_message = f"推送任务到 Redis 失败: {str(e)}"
        db.add(doc)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"推送任务到 Redis 失败: {str(e)}")
    
    return doc.id
    
@router.delete("/documents/{doc_id}")
async def handle_delete_document(
    doc_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user), # 新增当前用户依赖
):
    """
    删除文档 (需反查 Knowledge 权限)
    """
  
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
   
    await knowledge_crud.check_privilege(
        db, doc.knowledge_base_id, current_user.id,
        [UserKnowledgeRole.OWNER, UserKnowledgeRole.EDITOR]
    )
    
   
    try:
        return await delete_document_and_vectors(db=db, doc_id=doc_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

@router.get("/documents/{doc_id}", response_model=Document)
async def handle_get_document(
    doc_id: int,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_user), 
):
 
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    await knowledge_crud.check_privilege(
        db, 
        doc.knowledge_base_id, 
        current_user.id, 
        [UserKnowledgeRole.OWNER, UserKnowledgeRole.EDITOR, UserKnowledgeRole.VIEWER]
    )
    
    return doc