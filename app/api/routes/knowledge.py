from typing import Sequence

from fastapi import APIRouter, Body, Depends
from sqlmodel import Session

from app.api import deps
from app.services.retrieval import VectorStoreManager
from app.domain.models import KnowledgeCreate, KnowledgeRead, KnowledgeUpdate
from app.services import knowledge_crud

router = APIRouter()

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