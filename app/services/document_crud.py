from sqlmodel import Session
from fastapi import HTTPException
from app.domain.models import Document, Knowledge
from app.services.retrieval import VectorStoreManager
from app.services.factories import setup_embed_model
from app.services.file_storage import delete_file_from_minio
import logging

logger = logging.getLogger(__name__)
def delete_document_and_vectors(db: Session, doc_id: int):
    """
    执行原子删除：
    1. 检查文档存在性
    2. 从 Chroma 删除向量 (关键步骤，失败则中断)
    3. 从 Postgres 删除记录
    4. 从 MinIO 删除文件 (最后执行，降低残留风险)
    """
    # 1. 查找 Document
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 准备数据
    chroma_ids = [chunk.chroma_id for chunk in doc.chunks]
    
    # 2. [关键] 先删向量。如果这一步失败，抛出异常，中止后续 DB 操作。
    if chroma_ids:
        knowledge = db.get(Knowledge, doc.knowledge_base_id)
        # 只有当关联的知识库还存在时，才尝试删向量
        if knowledge:
            try:
                collection_name = f"kb_{knowledge.id}"
                # 这里可以优化：不需要重新 setup_embed_model，只要名字对就行，
                # 但为了复用 VectorStoreManager 逻辑先保持现状
                embed_model = setup_embed_model(knowledge.embed_model)
                manager = VectorStoreManager(collection_name, embed_model)
                
                # 🟢 核心修正：让 delete_vectors 抛出的异常向上冒泡
                # VectorStoreManager.delete_vectors 内部如果 raise，这里不要吞掉
                manager.delete_vectors(chroma_ids)
                
            except Exception as e:
                logger.error(f"ChromaDB 向量删除失败，回滚操作: {e}")
                # 🟢 必须抛出异常，阻止 DB 删除！
                raise HTTPException(status_code=500, detail=f"向量库删除失败，操作已取消: {str(e)}")

    # 3. 向量删除成功后，再删数据库记录
    try:
        for chunk in doc.chunks:
            db.delete(chunk)
        db.delete(doc)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"数据库删除文档 {doc_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据库删除失败: {str(e)}")
    
    # 4. 最后清理 MinIO 文件
    # (即使这一步失败了，只会留下垃圾文件，不会影响 RAG 检索准确性，比孤儿向量危害小)
    if doc.file_path:
        try:
            delete_file_from_minio(doc.file_path)
        except Exception as e:
            # 文件删除失败可以仅 Log，不影响主流程
            logger.warning(f"MinIO 文件删除失败 (可忽略): {e}")
    
    return {"message": f"文档 ID {doc_id} 及其 {len(chroma_ids)} 个向量已成功删除。"}