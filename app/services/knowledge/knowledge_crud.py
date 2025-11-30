import logging
from typing import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.domain.models import (Knowledge, 
                               KnowledgeCreate, KnowledgeUpdate, 
                               Document, Experiment)
from app.services.knowledge.document_crud import delete_document_and_vectors

logger = logging.getLogger(__name__)

async def create_knowledge(db: AsyncSession, knowledge_to_create: KnowledgeCreate) -> Knowledge:
    logger.info(f"Creating new knowledge base: {knowledge_to_create.name}")
    knowledge_db = Knowledge.model_validate(knowledge_to_create)
    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    return knowledge_db

async def get_knowledge_by_id(db: AsyncSession, knowledge_id: int) -> Knowledge:
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge

async def get_all_knowledges(db: AsyncSession, skip:int = 0, limit: int = 100) -> Sequence[Knowledge]:
    statement = select(Knowledge).offset(skip).limit(limit)
    result = await db.exec(statement)
    return result.all()

async def update_knowledge(db: AsyncSession, knowledge_id: int, knowledge_to_update: KnowledgeUpdate) -> Knowledge:
    knowledge_db = await get_knowledge_by_id(db, knowledge_id)
    update_data = knowledge_to_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(knowledge_db, key, value)
    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    return knowledge_db

async def delete_knowledge_pipeline(db: AsyncSession, knowledge_id: int):
    """
    级联删除知识库
    """
    logger.info(f"开始执行知识库 {knowledge_id} 的级联删除任务...")
    
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        return

    statement = select(Document).where(Document.knowledge_base_id == knowledge_id)
    result = await db.exec(statement)
    documents = result.all()
    
    # 删除文档
    for doc in documents:
        try:
            await delete_document_and_vectors(db, doc.id) 
        except Exception as e:
            logger.error(f"删除文档 {doc.id} 失败: {e}")

    # 再次检查残留并删除
    stmt_check = select(Document).where(Document.knowledge_base_id == knowledge_id)
    result_check = await db.exec(stmt_check)
    remaining_docs = result_check.all()
    for doc in remaining_docs:
        try:
            await delete_document_and_vectors(db, doc.id)
        except Exception:
            pass

    # 删除实验
    try:
        exp_statement = select(Experiment).where(Experiment.knowledge_id == knowledge_id)
        exp_result = await db.exec(exp_statement)
        experiments = exp_result.all()
        for exp in experiments:
            # 🟢 [FIX] 必须 await
            await db.delete(exp)
    except Exception as e:
        logger.error(f"删除关联实验失败: {e}")

    # 删除知识库本体
    try:
        # 🟢 [FIX] 必须 await
        await db.delete(knowledge)
        await db.commit()
        logger.info(f"知识库 {knowledge.name} 删除完成。")
    except Exception as e:
        logger.error(f"删除知识库记录失败: {e}")
        await db.rollback()