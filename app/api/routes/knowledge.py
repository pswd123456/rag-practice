from typing import Sequence

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from sqlmodel import Session

from arq import create_pool
from arq.connections import RedisSettings

from app.api import deps
from app.services.retrieval import VectorStoreManager
from app.core.config import settings
from app.domain.models import (Knowledge,
                               KnowledgeCreate,
                               KnowledgeRead,
                               KnowledgeUpdate,
                               Document,
                               DocStatus)

from app.services import knowledge_crud
from app.services.file_storage import save_upload_file
from app.services.document_crud import delete_document_and_vectors
router = APIRouter()

# ------------------ Knowledge base management ------------------
@router.post("/knowledges", response_model=KnowledgeRead)
def handle_create_knowledge(
    *, #强制关键字参数
    knowledge_in: KnowledgeCreate,
    db: Session = Depends(deps.get_db_session),
):
    return knowledge_crud.create_knowledge(db, knowledge_in)

@router.get("/knowledges", response_model=Sequence[KnowledgeRead])
def handle_get_all_knowledges(
    db: Session = Depends(deps.get_db_session),
    skip: int = 0,
    limit: int = 100,
):
    return knowledge_crud.get_all_knowledges(db=db, skip=skip, limit=limit)

@router.get("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
def handle_get_knowledge_by_id(
    knowledge_id: int,
    db: Session = Depends(deps.get_db_session),
):
    return knowledge_crud.get_knowledge_by_id(db=db, knowledge_id=knowledge_id)

@router.put("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
def handle_update_knowledge(
    knowledge_id: int,
    knowledge_in: KnowledgeUpdate,
    db: Session = Depends(deps.get_db_session),
):
    return knowledge_crud.update_knowledge(db=db, knowledge_id=knowledge_id, knowledge_to_update=knowledge_in)

# ------------------- Vector Store ------------------
@router.post("/vector-store/reload")
def reload_vector_store(
    force: bool = Body(False, description="是否强制重新嵌入所有文档"),
    manager: VectorStoreManager = Depends(deps.get_vector_store_manager),
):
    manager.reload(force_rebuild=force)
    deps.reset_rag_pipeline()
    stats = manager.stats()
    return {"documents": stats["documents"], "collection": stats["collection"]}


@router.get("/vector-store/stats")
def vector_store_stats(
    manager: VectorStoreManager = Depends(deps.get_vector_store_manager),
):
    return manager.stats()

# ------------------- Document management ------------------

@router.post("/{knowledge_id}/upload", response_model=int)
async def upload_file(
        knowledge_id: int,
        file: UploadFile = File(...),
        db: Session = Depends(deps.get_db_session),
    ):

    # 检查知识库是否存在
    knowledge = db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="知识库不存在")
    
    # 保存文件
    try:
        saved_path = save_upload_file(file, knowledge_id)
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
    db.commit()
    db.refresh(doc)
    #推送任务到redis
    try:
        redis = await create_pool(RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT))
        await redis.enqueue_job("process_document_task", doc.id)
        await redis.close()
    except Exception as e:
        doc.status = DocStatus.FAILED
        doc.error_message = f"推送任务到 Redis 失败: {str(e)}"
        db.add(doc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"推送任务到 Redis 失败: {str(e)}")
    
    return doc.id
    
@router.delete("/documents/{doc_id}")
def handle_delete_document(
    doc_id: int,
    db: Session = Depends(deps.get_db_session),
):
    """
    删除指定文档及其在向量库中的所有切片。
    """
    try:
        # 调用复杂的服务逻辑，它负责原子删除
        return delete_document_and_vectors(db=db, doc_id=doc_id)
    except HTTPException as e:
        # 捕捉 404 错误
        raise e
    except Exception as e:
        # 捕捉其他错误 (如 Chroma 连接失败)
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
