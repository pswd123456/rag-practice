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
# [Modify] 引入 VectorStoreManager，不再使用 setup_vector_store
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.file_storage import get_minio_client

logger = logging.getLogger(__name__)

async def process_document_pipeline(db: AsyncSession, doc_id: int):
    """
    核心文档处理管道 (异步版)：下载 -> 加载(自动路由) -> 切分 -> 向量化 -> ES存储
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

    # [Note] collection_name 将作为 ES 索引的后缀
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
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_file:
            temp_file_path = tmp_file.name
        
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
        
        # 3. 注入元数据 (关键步骤)
        # 这些 metadata 会被写入 ES，后续用于 filter
        for d in raw_docs:
            d.metadata["source"] = doc.filename 
            d.metadata["doc_id"] = doc.id
            d.metadata["knowledge_id"] = doc.knowledge_base_id
            # 确保 page_number 存在 (Docling 可能会生成 page, 标准 loader 可能是 page_number)
            if "page" in d.metadata and "page_number" not in d.metadata:
                d.metadata["page_number"] = d.metadata["page"]

        # 4. 切分 (CPU Blocking -> Thread)
        def _split_task():
            return split_docs(raw_docs, knowledge.chunk_size, knowledge.chunk_overlap)
        
        splitted_docs = await asyncio.to_thread(_split_task)
        
        # 5. [Modify] 向量化与入库 ES (Network Blocking -> Thread)
        def _vector_store_task():
            embed_model = setup_embed_model(knowledge.embed_model)
            
            # 初始化 Manager (会自动处理索引前缀)
            manager = VectorStoreManager(collection_name, embed_model)
            
            # 确保 ES 索引和 Mapping 存在 (IK分词器等)
            manager.ensure_index()
            
            # 获取 Store 实例
            vector_store = manager.get_vector_store()
            
            # 批量写入文档
            # add_documents 会自动调用 embedding 模型生成向量，并写入 ES
            # 返回值是 ES 生成的 document IDs (List[str])
            logger.info(f"正在向 ES 索引 {manager.index_name} 写入 {len(splitted_docs)} 个切片...")
            return vector_store.add_documents(splitted_docs)

        # 获取 ES 返回的 ID 列表
        es_ids = await asyncio.to_thread(_vector_store_task)

        # 6. 保存 Chunk 映射 (DB Async)
        chunks_to_save = []
        for i, (es_id, s_docs) in enumerate(zip(es_ids, splitted_docs)):
            chunk = Chunk(
                document_id=doc.id, # type: ignore
                chroma_id=es_id,    # [Note] 这里复用 chroma_id 字段存储 ES 的 _id
                chunk_index=i,
                content=s_docs.page_content,
                page_number=s_docs.metadata.get("page_number")
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
        await db.rollback()
        
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