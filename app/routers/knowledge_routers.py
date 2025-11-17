from fastapi import APIRouter, Depends
from sqlmodel import Session
from typing import Sequence

from app.db.session import get_session
from app.services import knowledge_crud
from app.models.knowledge_models import KnowledgeCreate, KnowledgeUpdate, KnowledgeRead

router = APIRouter()

@router.post("/knowledges", response_model=KnowledgeRead)
def handle_create_knowledge(
    *,
    knowledge_in: KnowledgeCreate,
    db: Session = Depends(get_session),
):
    return knowledge_crud.create_knowledge(db, knowledge_in)

@router.get("/knowledges", response_model=Sequence[KnowledgeRead])
def handle_get_all_knowledges(
    db: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
):
    return knowledge_crud.get_all_knowledges(db=db, skip=skip, limit=limit)

@router.get("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
def handle_get_knowledge_by_id(
    knowledge_id: int,
    db: Session = Depends(get_session),
):
    return knowledge_crud.get_knowledge_by_id(db=db, knowledge_id=knowledge_id)

@router.put("/knowledges/{knowledge_id}", response_model=KnowledgeRead)
def handle_update_knowledge(
    knowledge_id: int,
    knowledge_in: KnowledgeUpdate,
    db: Session = Depends(get_session),
):
    return knowledge_crud.update_knowledge(db=db, knowledge_id=knowledge_id, knowledge_to_update=knowledge_in)