import asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from app.domain.models import Document, Knowledge
from app.services.retrieval import VectorStoreManager
from app.services.factories import setup_embed_model
from app.services.file_storage import delete_file_from_minio
import logging

logger = logging.getLogger(__name__)

async def delete_document_and_vectors(db: AsyncSession, doc_id: int):
    """
    执行原子删除 (适配 ES delete_by_query 版)
    """
    # 1. 查找 Document (不再需要 selectinload(Document.chunks))
    doc = await db.get(Document, doc_id)

    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 2. 从 ES 删除向量 (通过 metadata.doc_id)
    knowledge = await db.get(Knowledge, doc.knowledge_base_id)
    if knowledge:
        try:
            collection_name = f"kb_{knowledge.id}"
            embed_model = setup_embed_model(knowledge.embed_model)
            manager = VectorStoreManager(collection_name, embed_model)
            
            # 🟢 [FIX] 改用 delete_by_doc_id
            await asyncio.to_thread(manager.delete_by_doc_id, doc.id)
            
        except Exception as e:
            logger.error(f"ES 向量删除失败: {e}")
            # 根据需求，这里可以选择抛出异常阻断，或者仅记录日志允许继续删除 DB
            raise HTTPException(status_code=500, detail=f"向量库删除失败: {str(e)}")

    # 3. 删除数据库记录
    try:
        # 🟢 [FIX] 不再需要循环删除 chunk
        # for chunk in doc.chunks: ...
        
        await db.delete(doc)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"数据库删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"数据库删除失败: {str(e)}")
    
    # 4. 清理 MinIO (保持不变)
    if doc.file_path:
        try:
            await asyncio.to_thread(delete_file_from_minio, doc.file_path)
        except Exception as e:
            logger.warning(f"MinIO 文件删除失败: {e}")
    
    return {"message": f"文档 ID {doc_id} 删除成功"}