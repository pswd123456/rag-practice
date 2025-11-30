import logging
import io
import os
from functools import lru_cache
from fastapi import UploadFile
from minio import Minio
from app.core.config import settings

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    """
    获取全局唯一的 MinIO 客户端。
    """
    return Minio(
        endpoint=settings.MINIO_ENDPOINT, # 必须使用关键字参数
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )

def _get_file_size(file_obj) -> int:
    try:
        return os.fstat(file_obj.fileno()).st_size
    except Exception:
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        return size

def save_upload_file(upload_file: UploadFile, knowledge_id: int) -> str:
    client = get_minio_client()
    
    # [修改] 使用关键字参数 bucket_name
    if not client.bucket_exists(bucket_name=settings.MINIO_BUCKET_NAME):
        client.make_bucket(bucket_name=settings.MINIO_BUCKET_NAME)

    object_name = f"{knowledge_id}/{upload_file.filename}"
    file_size = _get_file_size(upload_file.file)

    try:
        logger.info(f"开始上传文件 {object_name} 到 MinIO (Size: {file_size})...")
        
        # [修改] put_object 也要确保使用关键字参数
        client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=upload_file.file,
            length=file_size,
            content_type=upload_file.content_type or "application/octet-stream",
            part_size=10 * 1024 * 1024
        )
        logger.info(f"文件 {object_name} 上传成功")
    except Exception as e:
        logger.error(f"MinIO 上传失败: {e}", exc_info=True)
        raise e
    finally:
        upload_file.file.close()

    return object_name

def save_bytes_to_minio(data: bytes, object_name: str, content_type: str = "application/octet-stream"):
    client = get_minio_client()
    try:
        # [修改] 关键字参数
        if not client.bucket_exists(bucket_name=settings.MINIO_BUCKET_NAME):
            client.make_bucket(bucket_name=settings.MINIO_BUCKET_NAME)
        
        data_stream = io.BytesIO(data)
        length = len(data)

        logger.info(f"Saving {object_name} to MinIO(Size :{length})")
        # [修改] 关键字参数
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
    client = get_minio_client()
    response = None
    try:
        # [修改] 关键字参数
        response = client.get_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name
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
    client = get_minio_client()
    try:
        logger.info(f"正在从 MinIO 删除文件: {object_name}")
        # [修改] 关键字参数
        client.remove_object(bucket_name=settings.MINIO_BUCKET_NAME, object_name=object_name)
        logger.info(f"MinIO 文件删除成功: {object_name}")
    except Exception as e:
        logger.error(f"MinIO 删除失败: {e}", exc_info=True)