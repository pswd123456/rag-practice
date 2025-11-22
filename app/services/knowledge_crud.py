from sqlmodel import Session, select
from app.domain.models import (Knowledge, 
                               KnowledgeCreate, KnowledgeUpdate, 
                               Document)
# delete_knowledge_pipeline 函数中使用了 delete_document_and_vectors，保留引用
from app.services.document_crud import delete_document_and_vectors

from fastapi import HTTPException
from typing import Sequence

import logging

# 移除 unnecessary imports 和 全局配置
# import logging.config
# from app.core.logging_setup import get_logging_config
# from app.core.config import settings 

# 仅获取 logger，不进行 dictConfig 配置
logger = logging.getLogger(__name__)


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

def delete_knowledge_pipeline(db: Session, knowledge_id: int):
    """
    [异步任务专用]
    级联删除知识库：
    1. 查出所有文档。
    2. 逐个调用原子删除（清理 MinIO + Chroma + DB）。
    3. 删除知识库主体。
    """
    logger.info(f"开始执行知识库 {knowledge_id} 的级联删除任务...")
    
    knowledge = db.get(Knowledge, knowledge_id)
    if not knowledge:
        logger.warning(f"知识库 {knowledge_id} 不存在，可能已被删除，跳过。")
        return

    # 1. 查出该知识库下的所有文档
    statement = select(Document).where(Document.knowledge_base_id == knowledge_id)
    documents = db.exec(statement).all()

    total_docs = len(documents)
    logger.info(f"知识库 {knowledge.name} 下共有 {total_docs} 个文档待删除。")

    # 2. 逐个删除文档
    deleted_count = 0
    for doc in documents:
        try:
            # 复用已有的原子删除逻辑
            delete_document_and_vectors(db, doc.id)#type: ignore
            deleted_count += 1
            # 可选：每删 10 个打印一次日志，或者记录进度到 Redis
            if deleted_count % 10 == 0:
                logger.info(f"进度: 已删除 {deleted_count}/{total_docs} 个文档...")
        except Exception as e:
            logger.error(f"删除文档 {doc.id} 失败: {e}", exc_info=True)
            # 继续删下一个，不要因为一个失败就中断整个流程

    # 重新查询 DB，确认此知识库下是否还有文档残留
    remaining_docs = db.exec(select(Document).where(Document.knowledge_base_id == knowledge_id)).all()

    if len(remaining_docs) > 0:
        logger.error(f"级联删除中止：知识库 {knowledge_id} 仍有 {len(remaining_docs)} 个文档未被清除。")
        logger.error("可能原因：数据库锁定或严重逻辑错误。知识库将保留以便排查。")
        # 这里直接返回，知识库状态会保持在 "DELETING"，这是合理的，提示管理员介入
        return

    # 3. 删除知识库本身
    try:
        db.delete(knowledge)
        db.commit()
        logger.info(f"知识库 {knowledge.name} (ID: {knowledge_id}) 删除完成。共清理 {deleted_count} 个文档。")
    except Exception as e:
        logger.error(f"删除知识库记录失败: {e}", exc_info=True)
        db.rollback()