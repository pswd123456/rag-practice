# app/services/minio/file_storage.py
import logging
import io
import os
import uuid 
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
        endpoint=settings.MINIO_ENDPOINT,
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
    """
    保存上传文件到 MinIO，返回对象存储路径。
    
    [Security Fix 2025-11-29]: 
    不再仅使用 filename 作为对象名，而是添加 UUID 前缀。
    解决同名文件覆盖导致的数据丢失风险。
    """
    client = get_minio_client()
    
    if not client.bucket_exists(bucket_name=settings.MINIO_BUCKET_NAME):
        client.make_bucket(bucket_name=settings.MINIO_BUCKET_NAME)

    # 生成唯一对象名: {knowledge_id}/{uuid}_{filename}
    # 使用 uuid4 hex (32 chars) 确保唯一性，同时保留原文件名以便 debug 识别
    unique_prefix = uuid.uuid4().hex
    # 替换文件名中的空格或特殊字符是一个好习惯，但这里主要依靠 UUID 保证唯一
    safe_filename = upload_file.filename.replace(" ", "_")
    object_name = f"{knowledge_id}/{unique_prefix}_{safe_filename}"
    
    file_size = _get_file_size(upload_file.file)

    try:
        logger.info(f"开始上传文件 {object_name} 到 MinIO (Size: {file_size})...")
        
        client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=upload_file.file,
            length=file_size,
            content_type=upload_file.content_type or "application/octet-stream",
            part_size=10 * 1024 * 1024
        )
        logger.info(f"文件上传成功: {object_name}")
    except Exception as e:
        logger.error(f"MinIO 上传失败: {e}", exc_info=True)
        raise e
    finally:
        upload_file.file.close()

    return object_name

def save_bytes_to_minio(data: bytes, object_name: str, content_type: str = "application/octet-stream"):
    """
    直接保存字节数据。
    注意：调用者需自行确保 object_name 的唯一性。
    """
    client = get_minio_client()
    try:
        if not client.bucket_exists(bucket_name=settings.MINIO_BUCKET_NAME):
            client.make_bucket(bucket_name=settings.MINIO_BUCKET_NAME)
        
        data_stream = io.BytesIO(data)
        length = len(data)

        logger.info(f"Saving bytes to MinIO: {object_name} (Size: {length})")
        
        client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=data_stream,
            length=length,
            content_type=content_type
        )
        return object_name
    except Exception as e:
        logger.error(f"上传 Bytes 到 MinIO 失败: {e}", exc_info=True)
        raise e

def get_file_from_minio(object_name: str) -> bytes:
    client = get_minio_client()
    response = None
    try:
        response = client.get_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name
        )
        return response.read()
    except Exception as e:
        logger.error(f"从 MinIO 读取文件失败 [{object_name}]: {e}", exc_info=True)
        raise e
    finally:
        if response:
            response.close()
            response.release_conn()

def delete_file_from_minio(object_name: str):
    client = get_minio_client()
    try:
        logger.info(f"正在从 MinIO 删除文件: {object_name}")
        client.remove_object(bucket_name=settings.MINIO_BUCKET_NAME, object_name=object_name)
        logger.info(f"MinIO 文件删除成功: {object_name}")
    except Exception as e:
        logger.error(f"MinIO 删除失败: {e}", exc_info=True)