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
    执行原子删除 (异步版)
    """
    # 1. 查找 Document 并预加载 Chunks
    stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.chunks))
    result = await db.exec(stmt)
    doc = result.first()

    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    chroma_ids = [chunk.chroma_id for chunk in doc.chunks]
    
    # 2. 先删向量
    if chroma_ids:
        knowledge = await db.get(Knowledge, doc.knowledge_base_id)
        if knowledge:
            try:
                collection_name = f"kb_{knowledge.id}"
                embed_model = setup_embed_model(knowledge.embed_model)
                manager = VectorStoreManager(collection_name, embed_model)
                await asyncio.to_thread(manager.delete_vectors, chroma_ids)
            except Exception as e:
                logger.error(f"ChromaDB 向量删除失败: {e}")
                raise HTTPException(status_code=500, detail=f"向量库删除失败: {str(e)}")

    # 3. 再删数据库记录
    try:
        for chunk in doc.chunks:
            # 🟢 [FIX] 必须 await
            await db.delete(chunk)
        
        # 🟢 [FIX] 必须 await
        await db.delete(doc)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"数据库删除文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"数据库删除失败: {str(e)}")
    
    # 4. 最后清理 MinIO
    if doc.file_path:
        try:
            await asyncio.to_thread(delete_file_from_minio, doc.file_path)
        except Exception as e:
            logger.warning(f"MinIO 文件删除失败: {e}")
    
    return {"message": f"文档 ID {doc_id} 删除成功"}