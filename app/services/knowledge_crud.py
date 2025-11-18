from sqlmodel import Session, select
from app.domain.models import Knowledge, KnowledgeCreate, KnowledgeUpdate
from fastapi import HTTPException
from typing import Sequence
def create_knowledge(db: Session, knowledge_to_create: KnowledgeCreate) -> Knowledge:
    Knowledge_db = Knowledge.model_validate(knowledge_to_create)
    
    db.add(Knowledge_db)
    db.commit()
    db.refresh(Knowledge_db)
    return Knowledge_db

def get_knowledge_by_id(db: Session, knowledge_id: int) -> Knowledge:
    knowledge = db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge

def get_all_knowledges(db: Session, skip:int = 0, limit: int = 100) -> Sequence[Knowledge]:
    knowledges = db.exec(select(Knowledge)).all()
    return knowledges

def update_knowledge(db: Session, knowledge_id: int, knowledge_to_update: KnowledgeUpdate) -> Knowledge:
    knowledge_db = get_knowledge_by_id(db, knowledge_id)

    update_data = knowledge_to_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(knowledge_db, key, value)

    db.add(knowledge_db)
    db.commit()
    db.refresh(knowledge_db)

    return knowledge_db



