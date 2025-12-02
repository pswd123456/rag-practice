# app/services/knowledge/knowledge_crud.py
import logging
import asyncio
from typing import Sequence, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.domain.models import (Knowledge, 
                               KnowledgeCreate, KnowledgeUpdate, 
                               Document, Experiment)
from app.services.knowledge.document_crud import delete_document_and_vectors
from app.services.retrieval import VectorStoreManager
from app.services.factories import setup_embed_model

logger = logging.getLogger(__name__)

async def create_knowledge(
    db: AsyncSession, 
    knowledge_to_create: KnowledgeCreate, 
    user_id: int
) -> Knowledge:
    """
    创建一个新的知识库并绑定到指定用户。
    """
    logger.info(f"Creating new knowledge base for User {user_id}: {knowledge_to_create.name}")
    
    # 将 Pydantic 模型转换为 SQLModel，并手动注入 user_id
    knowledge_db = Knowledge.model_validate(
        knowledge_to_create, 
        update={"user_id": user_id}
    )
    
    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    return knowledge_db

async def get_knowledge_by_id(
    db: AsyncSession, 
    knowledge_id: int, 
    user_id: int
) -> Knowledge:
    """
    获取指定 ID 的知识库，并校验是否属于该用户。
    """
    # 增加 user_id 过滤条件
    statement = select(Knowledge).where(
        Knowledge.id == knowledge_id, 
        Knowledge.user_id == user_id
    )
    result = await db.exec(statement)
    knowledge = result.first()
    
    if not knowledge:
        # 为了隐私安全，即使 ID 存在但属于别人，也返回 404
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge

async def get_all_knowledges(
    db: AsyncSession, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 100
) -> Sequence[Knowledge]:
    """
    获取当前用户的所有知识库列表。
    """
    statement = (
        select(Knowledge)
        .where(Knowledge.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.exec(statement)
    return result.all()

async def update_knowledge(
    db: AsyncSession, 
    knowledge_id: int, 
    user_id: int,
    knowledge_to_update: KnowledgeUpdate
) -> Knowledge:
    """
    更新知识库信息 (需校验 Owner)。
    """
    # 复用 get_knowledge_by_id 进行权限校验
    knowledge_db = await get_knowledge_by_id(db, knowledge_id, user_id)
    
    update_data = knowledge_to_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(knowledge_db, key, value)
    
    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    return knowledge_db

async def delete_knowledge_pipeline(
    db: AsyncSession, 
    knowledge_id: int,
    user_id: int
):
    """
    级联删除知识库 (需校验 Owner)。
    """
    logger.info(f"User {user_id} 请求级联删除知识库 {knowledge_id}...")
    
    # 1. 权限校验 (查不到即无权或不存在)
    # 这里我们手动查一下，不复用 get_knowledge_by_id 避免抛出异常后不好处理后续逻辑（虽然这里抛出 404 也是对的）
    statement = select(Knowledge).where(
        Knowledge.id == knowledge_id, 
        Knowledge.user_id == user_id
    )
    result = await db.exec(statement)
    knowledge = result.first()
    
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")

    # 2. 获取关联文档
    # 这里不需要额外过滤 user_id，因为 Knowledge 已经是确认过的了
    doc_stmt = select(Document).where(Document.knowledge_base_id == knowledge_id)
    result = await db.exec(doc_stmt)
    documents = result.all()
    
    # 3. 删除所有文档 (包含 MinIO 文件和 ES 中的 Vector Documents)
    for doc in documents:
        try:
            # Document CRUD 内部目前没有 user_id 校验，但这里是安全的，
            # 因为我们是从属于 User 的 Knowledge 中查出的 Document
            await delete_document_and_vectors(db, doc.id) 
        except Exception as e:
            logger.error(f"删除文档 {doc.id} 失败: {e}")

    # Double check 残留
    result_check = await db.exec(doc_stmt)
    remaining_docs = result_check.all()
    for doc in remaining_docs:
        try:
            await delete_document_and_vectors(db, doc.id)
        except Exception:
            pass

    # 4. 删除关联实验
    try:
        exp_statement = select(Experiment).where(Experiment.knowledge_id == knowledge_id)
        exp_result = await db.exec(exp_statement)
        experiments = exp_result.all()
        for exp in experiments:
            await db.delete(exp)
    except Exception as e:
        logger.error(f"删除关联实验失败: {e}")

    # 5. 删除 ES 索引本身
    try:
        collection_name = f"kb_{knowledge.id}"
        embed_model = setup_embed_model(knowledge.embed_model)
        manager = VectorStoreManager(collection_name, embed_model)
        
        await asyncio.to_thread(manager.delete_index)
        logger.info(f"ES 索引 {collection_name} 清理请求已发送。")
    except Exception as e:
        logger.error(f"删除 ES 索引失败 (Resource Leak Warning): {e}")

    # 6. 删除知识库本体
    try:
        await db.delete(knowledge)
        await db.commit()
        logger.info(f"知识库 {knowledge.name} 删除完成。")
    except Exception as e:
        logger.error(f"删除知识库记录失败: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")