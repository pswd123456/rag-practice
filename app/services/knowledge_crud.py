import logging
from typing import Sequence

from sqlmodel import Session, select
from fastapi import HTTPException

from app.domain.models import (Knowledge, 
                               KnowledgeCreate, KnowledgeUpdate, 
                               Document)
from app.services.document_crud import delete_document_and_vectors

# 移除重复的 logging config 配置
# 仅获取 logger 实例，依赖 Main/Worker 的统一配置
logger = logging.getLogger(__name__)


def create_knowledge(db: Session, knowledge_to_create: KnowledgeCreate) -> Knowledge:
    # 增加业务日志
    logger.info(f"Creating new knowledge base: {knowledge_to_create.name}")
    knowledge_db = Knowledge.model_validate(knowledge_to_create)
    db.add(knowledge_db)
    db.commit()
    db.refresh(knowledge_db)
    return knowledge_db

def get_knowledge_by_id(db: Session, knowledge_id: int) -> Knowledge:
    knowledge = db.get(Knowledge, knowledge_id)
    if not knowledge:
        logger.warning(f"Knowledge base not found: {knowledge_id}")
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge

def get_all_knowledges(db: Session, skip:int = 0, limit: int = 100) -> Sequence[Knowledge]:
    statement = select(Knowledge).offset(skip).limit(limit)
    knowledges = db.exec(statement).all()
    return knowledges

def update_knowledge(db: Session, knowledge_id: int, knowledge_to_update: KnowledgeUpdate) -> Knowledge:
    knowledge_db = get_knowledge_by_id(db, knowledge_id)

    update_data = knowledge_to_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(knowledge_db, key, value)

    db.add(knowledge_db)
    db.commit()
    db.refresh(knowledge_db)
    logger.info(f"Updated knowledge base: {knowledge_id}")
    return knowledge_db

def delete_knowledge_pipeline(db: Session, knowledge_id: int):
    """
    [异步任务专用] 级联删除知识库
    """
    logger.info(f"开始执行知识库 {knowledge_id} 的级联删除任务...")
    
    knowledge = db.get(Knowledge, knowledge_id)
    if not knowledge:
        logger.warning(f"知识库 {knowledge_id} 不存在，可能已被删除，跳过。")
        return

    statement = select(Document).where(Document.knowledge_base_id == knowledge_id)
    documents = db.exec(statement).all()
    total_docs = len(documents)
    
    logger.info(f"知识库 {knowledge.name} 下共有 {total_docs} 个文档待删除。")

    deleted_count = 0
    for doc in documents:
        try:
            delete_document_and_vectors(db, doc.id) # type: ignore
            deleted_count += 1
            if deleted_count % 10 == 0:
                logger.debug(f"进度: 已删除 {deleted_count}/{total_docs} 个文档...")
        except Exception as e:
            logger.error(f"删除文档 {doc.id} 失败: {e}", exc_info=True)

    # 检查残留
    remaining_docs = db.exec(select(Document).where(Document.knowledge_base_id == knowledge_id)).all()
    if remaining_docs:
        logger.error(f"级联删除异常：知识库 {knowledge_id} 仍有 {len(remaining_docs)} 个文档未被清除。")
        return

    try:
        db.delete(knowledge)
        db.commit()
        logger.info(f"知识库 {knowledge.name} (ID: {knowledge_id}) 删除完成。")
    except Exception as e:
        logger.error(f"删除知识库记录失败: {e}", exc_info=True)
        db.rollback()