import logging
import os
import asyncio
import tempfile
from pathlib import Path
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.models import Document, DocStatus, Chunk, Knowledge
# DoclingLoader
from app.services.loader.docling_loader import load_docling_document
from app.services.loader import load_single_document, split_docs
from app.services.factories import setup_embed_model
from app.services.retrieval import setup_vector_store
from app.services.file_storage import get_minio_client

logger = logging.getLogger(__name__)

async def process_document_pipeline(db: AsyncSession, doc_id: int):
    """
    核心文档处理管道 (异步版)：下载 -> 加载(自动路由) -> 切分 -> 向量化 -> 存储
    
    关键策略：
    1. DB 操作使用 await。
    2. 文件下载、文档解析(CPU密集)、向量库写入(同步网络IO) 使用 asyncio.to_thread 放入线程池，
       避免阻塞 Worker 的主事件循环。
    """
    # 1. 获取文档并预加载关联的 Knowledge (避免 lazy load 报错)
    stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.knowledge_base))
    result = await db.exec(stmt)
    doc = result.first()

    if not doc:
        logger.error(f"文档 {doc_id} 不存在")
        # 这种情况下没法更新状态，只能抛错或记录日志
        raise ValueError(f"文档 {doc_id} 不存在")
    
    knowledge = doc.knowledge_base
    # 双重检查，防止脏数据
    if not knowledge:
        # 尝试手动查一次
        knowledge = await db.get(Knowledge, doc.knowledge_base_id)
        if not knowledge:
            raise ValueError(f"关联的知识库 {doc.knowledge_base_id} 不存在")

    collection_name = f"kb_{knowledge.id}"
    logger.info(f"开始处理文档 {doc_id} | KB: {knowledge.name} | File: {doc.filename}")

    # 更新状态
    doc.status = DocStatus.PROCESSING
    db.add(doc)
    await db.commit()

    temp_file_path = None
    try:
        # 1. 下载文件 (IO Blocking -> Thread)
        minio_client = get_minio_client()
        original_suffix = Path(doc.filename).suffix.lower()
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_file:
            temp_file_path = tmp_file.name
        
        # 在线程中执行下载
        def _download_task():
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=doc.file_path,
                file_path=temp_file_path
            )
        await asyncio.to_thread(_download_task)
        
        # 2. 根据文件类型路由 Loader (CPU Blocking -> Thread)
        def _load_task():
            if original_suffix in [".pdf", ".docx", ".doc"]:
                logger.info(f"检测到 {original_suffix} 文件，使用 DoclingLoader (GPU/CPU)...")
                return load_docling_document(temp_file_path)
            else:
                logger.info(f"使用标准 Loader 处理 {original_suffix} 文件...")
                return load_single_document(temp_file_path)

        raw_docs = await asyncio.to_thread(_load_task)
        
        # 3. 注入元数据 (内存操作，无需 await)
        for d in raw_docs:
            d.metadata["source"] = doc.filename 
            d.metadata["doc_id"] = doc.id
            d.metadata["knowledge_id"] = doc.knowledge_base_id

        # 4. 切分 (CPU Blocking -> Thread)
        def _split_task():
            return split_docs(raw_docs, knowledge.chunk_size, knowledge.chunk_overlap)
        
        splitted_docs = await asyncio.to_thread(_split_task)
        
        # 5. 向量化与入库 (Network Blocking -> Thread)
        # Chroma 的 add_documents 内部会调用 Embedding API (Network) 和写入 DB (IO/Network)
        def _vector_store_task():
            embed_model = setup_embed_model(knowledge.embed_model)
            vector_store = setup_vector_store(collection_name, embed_model)
            return vector_store.add_documents(splitted_docs)

        chroma_ids = await asyncio.to_thread(_vector_store_task)

        # 6. 保存 Chunk 映射 (DB Async)
        chunks_to_save = []
        for i, (c_id, s_docs) in enumerate(zip(chroma_ids, splitted_docs)):
            chunk = Chunk(
                document_id=doc.id, # type: ignore
                chroma_id=c_id,
                chunk_index=i,
                content=s_docs.page_content,
                page_number=s_docs.metadata.get("page_number") or s_docs.metadata.get("page")
            )
            chunks_to_save.append(chunk)
        
        db.add_all(chunks_to_save)

        # 7. 完成
        doc.status = DocStatus.COMPLETED
        db.add(doc)
        await db.commit()
        logger.info(f"文档 {doc.id} 处理完成，共生成 {len(chunks_to_save)} 个切片。")

    except Exception as e:
        logger.error(f"文档 {doc_id} 处理失败: {e}", exc_info=True)
        # 回滚逻辑
        # 注意：SQLAlchemy AsyncSession 在异常后通常需要 rollback 才能继续使用
        await db.rollback()
        
        # 重新获取 doc 对象 (因为 rollback 后 session 中的对象可能过期)
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