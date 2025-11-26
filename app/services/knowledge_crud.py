import logging
from typing import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.domain.models import (Knowledge, 
                               KnowledgeCreate, KnowledgeUpdate, 
                               Document, Experiment)
from app.services.document_crud import delete_document_and_vectors

# 仅获取 logger 实例，依赖 Main/Worker 的统一配置
logger = logging.getLogger(__name__)


async def create_knowledge(db: AsyncSession, knowledge_to_create: KnowledgeCreate) -> Knowledge:
    # 增加业务日志
    logger.info(f"Creating new knowledge base: {knowledge_to_create.name}")
    knowledge_db = Knowledge.model_validate(knowledge_to_create)
    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    return knowledge_db

async def get_knowledge_by_id(db: AsyncSession, knowledge_id: int) -> Knowledge:
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        logger.warning(f"Knowledge base not found: {knowledge_id}")
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge

async def get_all_knowledges(db: AsyncSession, skip:int = 0, limit: int = 100) -> Sequence[Knowledge]:
    statement = select(Knowledge).offset(skip).limit(limit)
    result = await db.exec(statement)
    knowledges = result.all()
    return knowledges

async def update_knowledge(db: AsyncSession, knowledge_id: int, knowledge_to_update: KnowledgeUpdate) -> Knowledge:
    knowledge_db = await get_knowledge_by_id(db, knowledge_id)

    update_data = knowledge_to_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(knowledge_db, key, value)

    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    logger.info(f"Updated knowledge base: {knowledge_id}")
    return knowledge_db

async def delete_knowledge_pipeline(db: AsyncSession, knowledge_id: int):
    """
    级联删除知识库 (异步版)
    """
    logger.info(f"开始执行知识库 {knowledge_id} 的级联删除任务...")
    
    knowledge = await db.get(Knowledge, knowledge_id)
    if not knowledge:
        logger.warning(f"知识库 {knowledge_id} 不存在，可能已被删除，跳过。")
        return

    statement = select(Document).where(Document.knowledge_base_id == knowledge_id)
    result = await db.exec(statement)
    documents = result.all()
    total_docs = len(documents)
    
    logger.info(f"知识库 {knowledge.name} 下共有 {total_docs} 个文档待删除。")

    deleted_count = 0
    for doc in documents:
        try:
            # ⚠️ 这里必须 await，因为 delete_document_and_vectors 已经改为异步
            await delete_document_and_vectors(db, doc.id) 
            deleted_count += 1
            if deleted_count % 10 == 0:
                logger.debug(f"进度: 已删除 {deleted_count}/{total_docs} 个文档...")
        except Exception as e:
            logger.error(f"删除文档 {doc.id} 失败: {e}", exc_info=True)

    # 检查残留
    stmt_check = select(Document).where(Document.knowledge_base_id == knowledge_id)
    result_check = await db.exec(stmt_check)
    remaining_docs = result_check.all()
    
    if remaining_docs:
        logger.error(f"级联删除异常：知识库 {knowledge_id} 仍有 {len(remaining_docs)} 个文档未被清除。")
        return

    try:
        # 显式查询实验记录
        exp_statement = select(Experiment).where(Experiment.knowledge_id == knowledge_id)
        exp_result = await db.exec(exp_statement)
        experiments = exp_result.all()
        
        if experiments:
            logger.info(f"正在清理关联的 {len(experiments)} 个实验记录...")
            for exp in experiments:
                db.delete(exp)
                
    except Exception as e:
        logger.error(f"删除关联实验失败: {e}", exc_info=True)
        return

    try:
        db.delete(knowledge)
        await db.commit()
        logger.info(f"知识库 {knowledge.name} (ID: {knowledge_id}) 删除完成。")
    except Exception as e:
        logger.error(f"删除知识库记录失败: {e}", exc_info=True)
        await db.rollback()