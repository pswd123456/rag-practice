from sqlmodel import Session, select
from fastapi import HTTPException
from typing import List

from app.domain.models import Document, Chunk
from app.services.retrieval import VectorStoreManager
from app.services.factories import setup_embed_model
from app.services.file_storage import delete_file_from_minio
from app.core.config import settings

def delete_document_and_vectors(db: Session, doc_id: int):
    """
    执行原子删除：
    1. 从 MinIO 删除源文件
    2. 查找所有关联的 chroma_id。
    3. 从 ChromaDB 中删除这些向量。
    4. 从 Postgres 中删除 Chunk 记录。
    5. 从 Postgres 中删除 Document 记录。
    """
    # 1. 查找 Document
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if doc.file_path:
        delete_file_from_minio(doc.file_path)

    # 2. 查找所有关联的 chroma_id
    # 使用 Relationship 加载关联的 chunks
    chroma_ids = [chunk.chroma_id for chunk in doc.chunks]
    
    # 3. 初始化 VectorStoreManager 并执行删除
    # 注意：这里需要重新初始化模型和管理器，因为它是同步 CRUD 操作
    embed_model = setup_embed_model("text-embedding-v4")
    manager = VectorStoreManager(settings.CHROMADB_COLLECTION_NAME, embed_model, settings.TOP_K)
    
    # 调用增强后的 delete_vectors 方法
    manager.delete_vectors(chroma_ids) 
    
    # 4. 从 Postgres 中删除 Chunk 和 Document 记录
    # 启用级联删除 (Cascade Delete) 是更好的做法，但在当前简单模型中，我们手动操作。
    for chunk in doc.chunks:
        db.delete(chunk)

    db.delete(doc)
    db.commit()
    
    return {"message": f"文档 ID {doc_id} 及其 {len(chroma_ids)} 个向量已成功删除。"}