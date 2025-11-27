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
    执行原子删除 (异步版)：
    1. 检查文档存在性 (预加载 Chunks)
    2. 从 Chroma 删除向量 (关键步骤，失败则中断)
    3. 从 Postgres 删除记录
    4. 从 MinIO 删除文件 (最后执行，降低残留风险)
    """
    # 1. 查找 Document 并预加载 Chunks
    # ⚠️ 异步模式下必须显式加载关系，否则访问 doc.chunks 会报错
    stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.chunks))
    result = await db.exec(stmt)
    doc = result.first()

    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 准备数据 (此时 chunks 已加载到内存)
    chroma_ids = [chunk.chroma_id for chunk in doc.chunks]
    
    # 2. [关键] 先删向量。如果这一步失败，抛出异常，中止后续 DB 操作。
    if chroma_ids:
        # 获取关联知识库信息
        knowledge = await db.get(Knowledge, doc.knowledge_base_id)
        # 只有当关联的知识库还存在时，才尝试删向量
        if knowledge:
            try:
                collection_name = f"kb_{knowledge.id}"
                embed_model = setup_embed_model(knowledge.embed_model)
                manager = VectorStoreManager(collection_name, embed_model)
                
                await asyncio.to_thread(manager.delete_vectors, chroma_ids)
                
            except Exception as e:
                logger.error(f"ChromaDB 向量删除失败，回滚操作: {e}")
                # 🟢 必须抛出异常，阻止 DB 删除！
                raise HTTPException(status_code=500, detail=f"向量库删除失败，操作已取消: {str(e)}")

    # 3. 向量删除成功后，再删数据库记录
    try:
        # 显式删除 chunks (虽然 CASCADE 可能处理，但显式更安全)
        for chunk in doc.chunks:
            db.delete(chunk) # 标记删除，无需 await
        
        db.delete(doc) # 标记删除
        await db.commit() # 提交事务，需要 await
    except Exception as e:
        await db.rollback() # 回滚
        logger.error(f"数据库删除文档 {doc_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据库删除失败: {str(e)}")
    
    # 4. 最后清理 MinIO 文件
    if doc.file_path:
        try:
            delete_file_from_minio(doc.file_path)
        except Exception as e:
            logger.warning(f"MinIO 文件删除失败 (可忽略): {e}")
    
    return {"message": f"文档 ID {doc_id} 及其 {len(chroma_ids)} 个向量已成功删除。"}