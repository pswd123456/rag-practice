"""
app/services/ingest/processor.py
"""
import logging
import os
import asyncio
import tempfile
from pathlib import Path
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.models import Document, DocStatus, Knowledge
# [Modify] 引入新的加载函数
from app.services.loader.docling_loader import load_and_chunk_docling_document
from app.services.loader import load_single_document, split_docs
from app.services.factories import setup_embed_model
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.file_storage import get_minio_client

logger = logging.getLogger(__name__)

async def process_document_pipeline(db: AsyncSession, doc_id: int):
    """
    核心文档处理管道 (异步版)：下载 -> 加载&切分(Hybrid/Recursive) -> 向量化 -> ES存储
    """
    # 1. 获取文档并预加载关联的 Knowledge
    stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.knowledge_base))
    result = await db.exec(stmt)
    doc = result.first()

    if not doc:
        logger.error(f"文档 {doc_id} 不存在")
        raise ValueError(f"文档 {doc_id} 不存在")
    
    knowledge = doc.knowledge_base
    if not knowledge:
        knowledge = await db.get(Knowledge, doc.knowledge_base_id)
        if not knowledge:
            raise ValueError(f"关联的知识库 {doc.knowledge_base_id} 不存在")

    collection_name = f"kb_{knowledge.id}"
    logger.info(f"开始处理文档 {doc_id} | KB: {knowledge.name} | File: {doc.filename}")

    doc.status = DocStatus.PROCESSING
    db.add(doc)
    await db.commit()

    temp_file_path = None
    try:
        # 1. 下载文件
        minio_client = get_minio_client()
        original_suffix = Path(doc.filename).suffix.lower()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_file:
            temp_file_path = tmp_file.name
        
        def _download_task():
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=doc.file_path,
                file_path=temp_file_path
            )
        await asyncio.to_thread(_download_task)
        
        # 2. 加载与切分 (Load & Split)
        # 根据文件类型选择不同的策略
        # PDF/Docx -> Docling HybridChunker (一步到位)
        # Txt/Md -> Standard Loader -> RecursiveSplitter (两步)
        
        splitted_docs = [] # 最终的切片列表

        def _load_and_split_task():
            if original_suffix in [".pdf", ".docx", ".doc"]:
                logger.info(f"检测到 {original_suffix} 文件，使用 Docling HybridChunker 处理...")
                # Docling 直接返回切好的 chunks，无需后续 split
                # 注意：HybridChunker 使用 Token 计数，这里传入 chunk_size 作为 max_tokens
                return load_and_chunk_docling_document(temp_file_path, chunk_size=knowledge.chunk_size)
            else:
                logger.info(f"使用标准 Loader + RecursiveSplitter 处理 {original_suffix} 文件...")
                # 1. 加载全文
                raw_docs = load_single_document(temp_file_path)
                # 2. 机械切分
                return split_docs(raw_docs, knowledge.chunk_size, knowledge.chunk_overlap)

        splitted_docs = await asyncio.to_thread(_load_and_split_task)
        
        # 3. 注入通用元数据
        for d in splitted_docs:
            d.metadata["source"] = doc.filename 
            d.metadata["doc_id"] = doc.id
            d.metadata["knowledge_id"] = doc.knowledge_base_id
            # 确保 page_number 存在 (Docling HybridChunker 可能不直接提供 page_number，而是 doc_items)
            # 这里做一个简单的兼容
            if "page" in d.metadata and "page_number" not in d.metadata:
                d.metadata["page_number"] = d.metadata["page"]

        logger.info(f"文档处理完成，共生成 {len(splitted_docs)} 个切片。")

        # 4. 向量化与入库 ES
        def _vector_store_task():
            embed_model = setup_embed_model(knowledge.embed_model)
            manager = VectorStoreManager(collection_name, embed_model)
            manager.ensure_index()
            vector_store = manager.get_vector_store()
            
            logger.info(f"正在向 ES 索引 {manager.index_name} 写入切片...")
            return vector_store.add_documents(splitted_docs)

        await asyncio.to_thread(_vector_store_task)

        # 5. 完成
        doc.status = DocStatus.COMPLETED
        db.add(doc)
        await db.commit()

    except Exception as e:
        logger.error(f"文档 {doc_id} 处理失败: {e}", exc_info=True)
        await db.rollback()
        
        # 重新获取 doc 以防 session 过期
        doc = await db.get(Document, doc_id)
        if doc:
            doc.status = DocStatus.FAILED
            doc.error_message = str(e)[:500]
            db.add(doc)
            await db.commit()

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass