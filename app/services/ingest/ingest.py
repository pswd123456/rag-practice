"""
app/services/ingest/ingest.py
"""
import logging
import os
import asyncio
import tempfile
from pathlib import Path
from sqlmodel import select

from app.db.session import async_session_maker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.models import Document, DocStatus, Knowledge
from app.services.loader.docling_loader import load_and_chunk_docling_document
from app.services.loader import load_single_document, split_docs
from app.services.factories import setup_embed_model
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.minio.file_storage import get_minio_client

logger = logging.getLogger(__name__)

async def process_document_pipeline(doc_id: int):
    """
    核心文档处理管道
    将 DB 操作与耗时 IO/CPU 操作分离，避免长时间占用数据库连接。
    
    Phases:
    1. DB: 获取元数据, 状态 -> PROCESSING
    2. No-DB: 下载, 解析(Docling), 向量化
    3. DB: 状态 -> COMPLETED / FAILED
    """
    
    # -----------------------------------------------------
    # Phase 1: 初始化与状态更新 (Short DB Transaction)
    # -----------------------------------------------------
    # 需要在 Session 关闭前提取出的局部变量
    doc_filename = None
    doc_file_path = None
    doc_kb_id = None
    kb_id = None
    kb_chunk_size = None
    kb_chunk_overlap = None
    kb_embed_model = None
    kb_name = None

    async with async_session_maker() as db:
        # 1. 获取文档并预加载关联的 Knowledge
        stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.knowledge_base))
        result = await db.exec(stmt)
        doc = result.first()

        if not doc:
            logger.error(f"文档 {doc_id} 不存在")
            return # 无法处理，直接退出

        knowledge = doc.knowledge_base
        if not knowledge:
            # 尝试通过 ID 获取
            knowledge = await db.get(Knowledge, doc.knowledge_base_id)
            if not knowledge:
                logger.error(f"关联的知识库 {doc.knowledge_base_id} 不存在")
                doc.status = DocStatus.FAILED
                doc.error_message = "关联的知识库不存在"
                db.add(doc)
                await db.commit()
                return

        # 提取必要数据到局部变量 (Detaching data)
        doc_filename = doc.filename
        doc_file_path = doc.file_path
        doc_kb_id = doc.knowledge_base_id
        
        kb_id = knowledge.id
        kb_name = knowledge.name
        kb_chunk_size = knowledge.chunk_size
        kb_chunk_overlap = knowledge.chunk_overlap
        kb_embed_model = knowledge.embed_model

        logger.info(f"开始处理文档 {doc_id} | KB: {kb_name} | File: {doc_filename}")

        # 更新状态
        doc.status = DocStatus.PROCESSING
        doc.error_message = None # 清理旧错误
        db.add(doc)
        await db.commit()
    
    # Phase 1 结束，Session 释放
    
    # -----------------------------------------------------
    # Phase 2: 核心处理 (No DB Connection)
    # -----------------------------------------------------
    temp_file_path = None
    splitted_docs = []
    
    try:
        # 1. 下载文件
        minio_client = get_minio_client()
        original_suffix = Path(doc_filename).suffix.lower()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_file:
            temp_file_path = tmp_file.name
        
        def _download_task():
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=doc_file_path,
                file_path=temp_file_path
            )
        await asyncio.to_thread(_download_task)
        
        # 2. 加载与切分 (CPU Bound / IO Bound)
        def _load_and_split_task():
            if original_suffix in [".pdf", ".docx", ".doc"]:
                logger.info(f"检测到 {original_suffix} 文件，使用 Docling HybridChunker 处理...")
                return load_and_chunk_docling_document(temp_file_path, chunk_size=kb_chunk_size)
            else:
                logger.info(f"使用标准 Loader + RecursiveSplitter 处理 {original_suffix} 文件...")
                raw_docs = load_single_document(temp_file_path)
                return split_docs(raw_docs, kb_chunk_size, kb_chunk_overlap)

        splitted_docs = await asyncio.to_thread(_load_and_split_task)
        
        # 3. 注入通用元数据
        for d in splitted_docs:
            d.metadata["source"] = doc_filename
            d.metadata["doc_id"] = doc_id
            d.metadata["knowledge_id"] = doc_kb_id
            if "page" in d.metadata and "page_number" not in d.metadata:
                d.metadata["page_number"] = d.metadata["page"]#兼容pyPDFloader的写法

        logger.info(f"文档处理完成，共生成 {len(splitted_docs)} 个切片。")

        # 4. 向量化与入库 ES (Network Bound)
        # 注意: setup_embed_model 和 VectorStoreManager 初始化不需要 DB 连接
        collection_name = f"kb_{kb_id}"
        
        def _vector_store_task():
            embed_model = setup_embed_model(kb_embed_model)
            manager = VectorStoreManager(collection_name, embed_model)
            manager.ensure_index()
            vector_store = manager.get_vector_store()
            
            logger.info(f"正在向 ES 索引 {manager.index_name} 写入切片...")
            # add_documents 是 LangChain ES Store 的方法，通常是 IO 操作
            return vector_store.add_documents(splitted_docs)

        await asyncio.to_thread(_vector_store_task)

        # -----------------------------------------------------
        # Phase 3: 完成状态更新 (Short DB Transaction)
        # -----------------------------------------------------
        async with async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if doc:
                doc.status = DocStatus.COMPLETED
                db.add(doc)
                await db.commit()
                logger.info(f"文档 {doc_id} 状态已更新为 COMPLETED")

    except Exception as e:
        logger.error(f"文档 {doc_id} 处理失败: {e}", exc_info=True)
        
        # Error Handler: 重新获取 Session 记录错误
        async with async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if doc:
                doc.status = DocStatus.FAILED
                doc.error_message = str(e)[:500]
                db.add(doc)
                await db.commit()

    finally:
        # 清理临时文件
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass