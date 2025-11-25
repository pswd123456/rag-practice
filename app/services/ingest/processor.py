# app/services/ingest/processor.py
import logging
import os
import tempfile
from pathlib import Path
from sqlmodel import Session

from app.core.config import settings
from app.domain.models import Document, DocStatus, Chunk, Knowledge
# [修改] 引入 DoclingLoader
from app.services.loader.docling_loader import load_docling_document
from app.services.loader import load_single_document, split_docs
from app.services.factories import setup_embed_model
from app.services.retrieval import setup_vector_store
from app.services.file_storage import get_minio_client

logger = logging.getLogger(__name__)

def process_document_pipeline(db: Session, doc_id: int):
    """
    核心文档处理管道：下载 -> 加载(自动路由) -> 切分 -> 向量化 -> 存储
    """
    doc = db.get(Document, doc_id)
    if not doc:
        logger.error(f"文档 {doc_id} 不存在")
        raise ValueError(f"文档 {doc_id} 不存在")
    
    knowledge = doc.knowledge_base
    if not knowledge:
        knowledge = db.get(Knowledge, doc.knowledge_base_id)

    collection_name = f"kb_{knowledge.id}"
    logger.info(f"开始处理文档 {doc_id} | KB: {knowledge.name} | File: {doc.filename}")

    # 更新状态
    doc.status = DocStatus.PROCESSING
    db.add(doc)
    db.commit()

    temp_file_path = None
    try:
        # 1. 下载文件
        minio_client = get_minio_client()
        original_suffix = Path(doc.filename).suffix.lower() # 统一转小写
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_file:
            minio_client.fget_object(
                bucket_name=settings.MINIO_BUCKET_NAME,
                object_name=doc.file_path,
                file_path=tmp_file.name
            )
            temp_file_path = tmp_file.name
        
        # 2. 根据文件类型路由 Loader
        if original_suffix in [".pdf", ".docx", ".doc"]:
            logger.info(f"检测到 {original_suffix} 文件，使用 DoclingLoader (GPU加速)...")
            # Docling 输出的是 Markdown 格式的 Document 对象
            raw_docs = load_docling_document(temp_file_path)
        else:
            logger.info(f"使用标准 Loader 处理 {original_suffix} 文件...")
            raw_docs = load_single_document(temp_file_path)
        
        # 3. 注入元数据
        for d in raw_docs:
            d.metadata["source"] = doc.filename 
            d.metadata["doc_id"] = doc.id
            d.metadata["knowledge_id"] = doc.knowledge_base_id

        # 4. 切分 (目前 Docling 输出的也是大段 Markdown，先复用 Recursive 切分)
        # TODO: 后续步骤将针对 Markdown 结构优化切分器 (MarkdownHeaderTextSplitter)
        splitted_docs = split_docs(raw_docs, knowledge.chunk_size, knowledge.chunk_overlap)
        
        # 5. 向量化与入库 (Chroma)
        embed_model = setup_embed_model(knowledge.embed_model)
        vector_store = setup_vector_store(collection_name, embed_model)
        chroma_ids = vector_store.add_documents(splitted_docs)

        # 6. 保存 Chunk 映射
        chunks_to_save = []
        for i, (c_id, s_docs) in enumerate(zip(chroma_ids, splitted_docs)):
            chunk = Chunk(
                document_id=doc.id, # type: ignore
                chroma_id=c_id,
                chunk_index=i,
                content=s_docs.page_content,
                page_number=s_docs.metadata.get("page_number") or s_docs.metadata.get("page") # 兼容 Docling 和 PyPDF
            )
            chunks_to_save.append(chunk)
        db.add_all(chunks_to_save)

        # 7. 完成
        doc.status = DocStatus.COMPLETED
        db.add(doc)
        db.commit()
        logger.info(f"文档 {doc.id} 处理完成，共生成 {len(chunks_to_save)} 个切片。")

    except Exception as e:
        logger.error(f"文档 {doc_id} 处理失败: {e}", exc_info=True)
        # 回滚逻辑
        db.rollback()
        doc.status = DocStatus.FAILED
        doc.error_message = str(e)[:500]
        db.add(doc)
        db.commit()

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)