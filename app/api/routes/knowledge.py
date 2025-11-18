from typing import Sequence

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from sqlmodel import Session

from app.api import deps
from app.services.retrieval import VectorStoreManager

from app.domain.models import (Knowledge,
                               KnowledgeCreate,
                               KnowledgeRead,
                               KnowledgeUpdate,
                               Document,
                               DocStatus)

from app.services import knowledge_crud
from app.services.file_storage import save_upload_file

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
def upload_file(
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

    return doc.id
    
