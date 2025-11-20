# app/services/ingest/processor.py
import logging
import os
import tempfile
from pathlib import Path
from minio import Minio
from sqlmodel import Session

from app.core.config import settings
from app.domain.models import Document, DocStatus, Chunk, Knowledge
from app.services.loader import load_single_document, split_docs, normalize_metadata
from app.services.factories import setup_embed_model
from app.services.retrieval import setup_vector_store

logger = logging.getLogger(__name__)

# 这里的 MinIO 客户端可以由外部传入，或者在这里初始化单例
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE
)

def process_document_pipeline(db: Session, doc_id: int):
    """
    核心文档处理管道：下载 -> 加载 -> 切分 -> 向量化 -> 存储
    """
    # 1. 获取文档记录
    doc = db.get(Document, doc_id)
    if not doc:
        logger.error(f"文档 {doc_id} 不存在")
        raise ValueError(f"文档 {doc_id} 不存在")
    
    knowledge = doc.knowledge_base
    if not knowledge:
        # 如果关系没加载出来，手动查一次
        knowledge = db.get(Knowledge, doc.knowledge_base_id)
        if not knowledge:
            logger.error(f"知识库 {doc.knowledge_base_id} 不存在")
            raise ValueError(f"知识库 {doc.knowledge_base_id} 不存在")

    collection_name = f"kb_{knowledge.id}"
    embed_model_name = knowledge.embed_model

    chunk_size = knowledge.chunk_size
    chunk_overlap = knowledge.chunk_overlap

    logger.info(f"开始处理文档 {doc_id}，所属知识库: {knowledge.name} (ID: {knowledge.id})")
    logger.info(f"配置: Embed={embed_model_name}, Chunk={chunk_size}/{chunk_overlap}, Collection={collection_name}")


    # 更新状态 -> PROCESSING
    doc.status = DocStatus.PROCESSING
    db.add(doc)
    db.commit()

    temp_file_path = None
    try:
        # 2. 从 MinIO 下载文件
        file_object_name = doc.file_path 
        original_suffix = Path(doc.filename).suffix

        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_file:
            logger.info(f"正在从 MinIO 下载: {file_object_name}")
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=file_object_name,
                file_path=tmp_file.name
            )
            temp_file_path = tmp_file.name
        
        # 3. 加载与标准化
        raw_docs = load_single_document(temp_file_path)
        normalized_docs = normalize_metadata(raw_docs)
        
        # 注入元数据
        for d in normalized_docs:
            d.metadata["source"] = doc.filename 
            d.metadata["doc_id"] = doc.id
            d.metadata["knowledge_id"] = doc.knowledge_base_id

        # 4. 切分
        splitted_docs = split_docs(normalized_docs, chunk_size, chunk_overlap)
        
        # 5. 向量化与入库 (Chroma)
        embed_model = setup_embed_model(embed_model_name)
        vector_store = setup_vector_store(collection_name, embed_model)
        chroma_ids = vector_store.add_documents(splitted_docs)

        # 6. 保存 Chunk 映射到 Postgres
        chunks_to_save = []
        for i, (c_id, s_docs) in enumerate(zip(chroma_ids, splitted_docs)):
            chunk = Chunk(
                document_id=doc.id,#type: ignore
                chroma_id=c_id,
                chunk_index=i,
                content=s_docs.page_content,
                page_number=s_docs.metadata.get("page")
            )
            chunks_to_save.append(chunk)
        db.add_all(chunks_to_save)

        # 7. 完成
        doc.status = DocStatus.COMPLETED
        db.add(doc)
        db.commit()
        logger.info(f"文档 {doc.id} 处理完成")

    except Exception as e:
        logger.error(f"文档 {doc_id} 处理失败: {str(e)}", exc_info=True)

        if vector_store and chroma_ids:
            logger.warning(f"检测到处理失败，正在回滚 Chroma 中的 {len(chroma_ids)} 条向量...")
            try:
                vector_store.delete(ids=chroma_ids)
                logger.info("Chroma 向量回滚成功")
            except Exception as rollback_e:
                # 这种情况下只能记日志，或者报警人工处理
                logger.error(f"严重：Chroma 向量回滚失败！这些向量可能成为孤儿数据。IDs: {chroma_ids}, Error: {rollback_e}")       

        db.rollback()

        doc = db.get(Document, doc_id)
        if not doc:
            logger.error(f"文档 {doc_id} 不存在")
            raise ValueError(f"文档 {doc_id} 不存在")
        doc.status = DocStatus.FAILED
        doc.error_message = str(e)[:500]
        db.add(doc)
        db.commit()
        raise e # 抛出异常让 Worker 也能感知（可选）

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)