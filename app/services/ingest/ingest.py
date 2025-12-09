"""
app/services/ingest/ingest.py
"""
import logging
import os
import uuid
import asyncio
import tempfile
from pathlib import Path
from sqlmodel import select

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LangChainDocument

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
    Phases:
    1. DB: 获取元数据, 状态 -> PROCESSING
    2. No-DB: 下载, 解析(Docling/Basic), 向量化
    3. DB: 状态 -> COMPLETED / FAILED
    """
    
    # -----------------------------------------------------
    # Phase 1: 初始化与状态更新 (Short DB Transaction)
    # -----------------------------------------------------
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
            return

        knowledge = doc.knowledge_base
        if not knowledge:
            knowledge = await db.get(Knowledge, doc.knowledge_base_id)
            if not knowledge:
                logger.error(f"关联的知识库 {doc.knowledge_base_id} 不存在")
                doc.status = DocStatus.FAILED
                doc.error_message = "关联的知识库不存在"
                db.add(doc)
                await db.commit()
                return

        # 提取必要数据
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
        doc.error_message = None
        db.add(doc)
        await db.commit()
    
    # -----------------------------------------------------
    # Phase 2: 核心处理 (No DB Connection)
    # -----------------------------------------------------
    temp_file_path = None
    final_docs_to_ingest = []
    
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
        
        # 2. 加载与切分 (Updated for Parent-Child Indexing & Token Counting)
        def _load_and_split_task():
            # 初始化 Tokenizer (cl100k_base 适用于 GPT-4, Qwen, DeepSeek 等)
            try:
                tokenizer = tiktoken.get_encoding("cl100k_base")
            except Exception:
                # Fallback if specific encoding fails
                tokenizer = tiktoken.get_encoding("cl100k_base")

            # 定义子文档切分器 (Small Chunk)
            # Parent <- kb_chunk_size (Configurable via KB Settings)
            parent_chunk_size = kb_chunk_size
            
            # Child <- Configurable via Settings (Small-to-Big Strategy)
            child_chunk_size = settings.CHILD_CHUNK_SIZE
            child_overlap = settings.CHILD_CHUNK_OVERLAP
            
            parent_docs = []

            # A. 生成 Parent Docs
            if original_suffix in [".pdf", ".docx", ".doc"]:
                logger.info(f"使用 Docling 解析 Parent Docs (Size={parent_chunk_size})...")
                # 使用 Docling 生成较大的 Parent Chunks
                parent_docs = load_and_chunk_docling_document(temp_file_path, chunk_size=parent_chunk_size)
            else:
                logger.info(f"使用 BasicLoader 解析 Parent Docs...")
                # 普通文件加载
                raw_docs = load_single_document(temp_file_path)
                # 切分出 Parent
                parent_docs = split_docs(raw_docs, parent_chunk_size, kb_chunk_overlap)

            # B. 生成 Child Docs 并关联
            logger.info(f"生成 Child Docs (Size={child_chunk_size}) 并建立父子关联...")
            
            child_splitter = RecursiveCharacterTextSplitter(
                chunk_size=child_chunk_size,
                chunk_overlap=child_overlap,
                separators=["\n\n", "\n", "。", "！", "？", " ", ""]
            )
            
            results = []
            for p_doc in parent_docs:
                parent_id = str(uuid.uuid4())
                parent_content = p_doc.page_content
                
                # 计算 Parent Token 数并存入 Metadata
                token_count = len(tokenizer.encode(parent_content))
                
                # 切分 Child
                child_chunks = child_splitter.split_documents([p_doc])
                
                for c_doc in child_chunks:
                    # 继承元数据
                    c_doc.metadata.update(p_doc.metadata)
                    
                    # 注入关键关联信息
                    c_doc.metadata["doc_id"] = str(uuid.uuid4()) # Child Unique ID
                    c_doc.metadata["parent_id"] = parent_id      # Link to Parent
                    c_doc.metadata["parent_content"] = parent_content # Store Parent Content
                    c_doc.metadata["token_count"] = token_count  # Pre-calculated Tokens
                    
                    # 补充业务元数据
                    c_doc.metadata["source"] = doc_filename
                    c_doc.metadata["knowledge_id"] = doc_kb_id
                    # 兼容 pyPDF
                    if "page" in c_doc.metadata and "page_number" not in c_doc.metadata:
                        c_doc.metadata["page_number"] = c_doc.metadata["page"]

                    results.append(c_doc)
            
            return results

        final_docs_to_ingest = await asyncio.to_thread(_load_and_split_task)
        
        logger.info(f"文档处理完成。Parents: N/A -> Children: {len(final_docs_to_ingest)}")

        # 4. 向量化与入库 ES
        collection_name = f"kb_{kb_id}"
        
        def _vector_store_task():
            embed_model = setup_embed_model(kb_embed_model)
            manager = VectorStoreManager(collection_name, embed_model)
            manager.ensure_index()
            vector_store = manager.get_vector_store()
            
            logger.info(f"正在向 ES 索引 {manager.index_name} 写入切片...")
            # 注意：ES mapping 已经配置了 parent_content index: False
            return vector_store.add_documents(final_docs_to_ingest)

        await asyncio.to_thread(_vector_store_task)

        # -----------------------------------------------------
        # Phase 3: 完成状态更新
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
        async with async_session_maker() as db:
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