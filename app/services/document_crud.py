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
    1. 从 MinIO 删除源文件
    更改为直接删除collection
    4. 从 Postgres 中删除 Chunk 记录。
    5. 从 Postgres 中删除 Document 记录。
    """
    # 1. 查找 Document
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if doc.file_path:
        delete_file_from_minio(doc.file_path)

    chroma_ids = [chunk.chroma_id for chunk in doc.chunks]
    if chroma_ids:
        knowledge = db.get(Knowledge, doc.knowledge_base_id)
        if knowledge:
            try:
                collection_name = f"kb_{knowledge.id}"
                embed_model_name = knowledge.embed_model

                embed_model = setup_embed_model(embed_model_name)
                manager = VectorStoreManager(collection_name, embed_model)
                manager.delete_vectors(chroma_ids)
            except Exception as e:
                logger.error(f"Failed to delete vectors from ChromaDB: {e}")
            
    # 4. 从 Postgres 中删除 Chunk 和 Document 记录
    try:
        for chunk in doc.chunks:
            db.delete(chunk)

        db.delete(doc)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"数据库删除文档 {doc_id} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据库删除失败: {str(e)}")
    
    return {"message": f"文档 ID {doc_id} 及其 {len(chroma_ids)} 个向量已成功删除。"}