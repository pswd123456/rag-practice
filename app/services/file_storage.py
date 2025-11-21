import logging
import io
from functools import lru_cache # <--- 1. 引入 lru_cache
from fastapi import UploadFile
from minio import Minio
from app.core.config import settings

logger = logging.getLogger(__name__)

# 🔴 移除顶层的 minio_client = Minio(...)

# 🟢 新增单例 Getter
@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    """
    获取全局唯一的 MinIO 客户端。
    使用 lru_cache 确保只初始化一次。
    """
    # 只有在第一次调用时才会连接，避免 Import 时的副作用
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )

def save_upload_file(upload_file: UploadFile, knowledge_id: int) -> str:
    client = get_minio_client() # <--- 使用 Getter
    
    if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
        client.make_bucket(settings.MINIO_BUCKET_NAME)

    object_name = f"{knowledge_id}/{upload_file.filename}"
    
    upload_file.file.seek(0, 2)
    file_size = upload_file.file.tell()
    upload_file.file.seek(0)

    try:
        logger.info(f"开始上传文件 {object_name} 到 MinIO (Size: {file_size})...")
        client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=upload_file.file,
            length=file_size,
            content_type=upload_file.content_type or "application/octet-stream"
        )
        logger.info(f"文件 {object_name} 上传成功")
    except Exception as e:
        logger.error(f"MinIO 上传失败: {e}", exc_info=True)
        raise e
    finally:
        upload_file.file.close()

    return object_name

def save_bytes_to_minio(data: bytes, object_name: str, content_type: str = "application/octet-stream"):
    client = get_minio_client() # <--- 使用 Getter
    try:
        if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
            client.make_bucket(settings.MINIO_BUCKET_NAME)
        
        data_stream = io.BytesIO(data)
        length = len(data)

        logger.info(f"Saving {object_name} to MinIO(Size :{length})")
        client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=data_stream,
            length=length,
            content_type=content_type
        )
        return object_name
    except Exception as e:
        logger.error(f"上传文件到 MinIO 失败: {e}", exc_info=True)
        raise e

def get_file_from_minio(object_name: str) -> bytes:
    client = get_minio_client() # <--- 使用 Getter
    response = None
    try:
        response = client.get_object(
            settings.MINIO_BUCKET_NAME,
            object_name
        )
        return response.read()
    except Exception as e:
        logger.error(f"从 MinIO 读取文件失败: {e}", exc_info=True)
        raise e
    finally:
        if response:
            response.close()
            response.release_conn()

def delete_file_from_minio(object_name: str):
    client = get_minio_client() # <--- 使用 Getter
    try:
        logger.info(f"正在从 MinIO 删除文件: {object_name}")
        client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        logger.info(f"MinIO 文件删除成功: {object_name}")
    except Exception as e:
        logger.error(f"MinIO 删除失败: {e}", exc_info=True)