import asyncio
import logging
import logging.config
from typing import Any

import tempfile
import os
from minio import Minio

from arq import create_pool
from arq.connections import RedisSettings
from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging_setup import get_logging_config
from app.db.session import engine
from app.domain.models import Document, DocStatus, Chunk
from app.services.loader import load_single_document, split_docs, normalize_metadata
from app.services.factories import setup_hf_embed_model
from app.services.retrieval import setup_vector_store

minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE
)

logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))
logging.config.dictConfig(logging_config_dict)

logger = logging.getLogger(__name__)

async def startup(ctx: Any):
    logger.info("worker startup")
    pass

async def shutdown(ctx: Any):
    logger.info("worker shutdown")


def _sync_process_document(doc_id: int):
    """
    同步执行的文档处理逻辑, 封装在函数中以便在线程池运行
    """

    logger.info(f"[TASK] 处理文档 {doc_id}")

    with Session(engine) as db:
        # 获取文档记录
        doc = db.get(Document, doc_id)
        if not doc:
            logger.error(f"文档 {doc_id} 不存在")
            return
        
        # 更新状态 -> PROCESSING
        doc.status = DocStatus.PROCESSING
        db.add(doc)
        db.commit()

        temp_file_path = None

        try:
            # 1. 从 MinIO 下载文件到临时目录
            file_object_name = doc.file_path # 数据库里存的是 MinIO Key

            # 创建一个临时文件，不自动删除 (delete=False)，因为我们要把路径传给 loader
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                logger.info(f"正在从 MinIO 下载: {file_object_name}")
                minio_client.fget_object(
                    bucket_name=settings.MINIO_BUCKET_NAME,
                    object_name=file_object_name,
                    file_path=tmp_file.name
                )
                temp_file_path = tmp_file.name
            
            logger.debug(f"文件已下载到临时路径: {temp_file_path}")
            # 2. 加载文档 (传入临时文件路径)
            # load_single_document 应该能直接读取这个本地临时文件
            raw_docs = load_single_document(temp_file_path)

            normalized_docs = normalize_metadata(raw_docs)
            # 这一步会强制将source(项目存放路径, 设置在config)设置为文件名, 并且注入doc_id
            logger.debug(f"原始文档标准化完成: {len(normalized_docs)} 条")

            for d in normalized_docs:
                # 使用上传的文件名作为 source (覆盖默认的 data/ 路径)
                d.metadata["source"] = doc.filename 
                # 注入数据库 ID，用于未来数据一致性检查
                d.metadata["doc_id"] = doc.id

            if not doc.id:
                raise ValueError("文档ID不存在")

            splitted_docs = split_docs(normalized_docs)
            logger.info(f"文档 {doc.id} 切分完成，共 {len(splitted_docs)} 条")

            # 获取/初始化向量库
            embed_model = setup_hf_embed_model("Qwen3-Embedding-0.6B")
            vector_store = setup_vector_store(
                settings.CHROMADB_COLLECTION_NAME,
                embed_model
            )

            # 入库, 添加到Chroma, 获取返回的IDs
            chroma_ids = vector_store.add_documents(splitted_docs)
            logger.info(f"文档 {doc.id} 添加到向量库完成，共 {len(chroma_ids)} 条")

            # 保存chunk映射到 postgresql
            chunks_to_save = []

            for i, (c_id, s_docs) in enumerate(zip(chroma_ids, splitted_docs)):
                chunk = Chunk(
                    document_id=doc.id,
                    chroma_id=c_id,
                    chunk_index=i,
                    content=s_docs.page_content,
                    page_number=s_docs.metadata.get("page")
                )
                chunks_to_save.append(chunk)

            db.add_all(chunks_to_save)

            # 更新状态 -> COMPLETED
            doc.status = DocStatus.COMPLETED
            db.add(doc)
            db.commit()
            logger.info(f"文档 {doc.id} 处理完成")

        except Exception as e:
            logger.error(f" 文档 {doc.id} 处理失败: {str(e)}", exc_info=True)
            doc.status = DocStatus.FAILED
            doc.error_message = str(e)
            db.add(doc)
            db.commit()

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.debug(f"临时文件 {temp_file_path} 已删除")
async def process_document_task(ctx: Any, doc_id: int):
    """
    Arq 调用的异步任务入口
    """
    await asyncio.to_thread(_sync_process_document, doc_id)


# --- Arq 配置 ---

class WorkerSettings:
    # 注册可以被执行的任务函数列表
    functions = [process_document_task]

    # 配置 Redis 连接
    redis_settings = RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    
    # 启动和关闭时的钩子（当前仅打印日志）
    on_startup = startup
    on_shutdown = shutdown




