import logging
import io
import os  # 🟢 新增
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
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )

# 🟢 新增辅助函数：高效获取文件大小
def _get_file_size(file_obj) -> int:
    """
    尝试使用 fstat 获取文件大小（零 IO），失败则回退到 seek（IO 开销）。
    SpooledTemporaryFile 在数据量大时会落盘，此时有 fileno，可以用 fstat。
    """
    try:
        return os.fstat(file_obj.fileno()).st_size
    except Exception:
        # 回退方案：内存文件或不支持 fileno 的对象
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        return size

def save_upload_file(upload_file: UploadFile, knowledge_id: int) -> str:
    """
    接受用户上传的文件保存到minio,
    处理UPloadFile对象
    """
    client = get_minio_client()
    
    if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
        client.make_bucket(settings.MINIO_BUCKET_NAME)

    object_name = f"{knowledge_id}/{upload_file.filename}"
    
    # 🟢 1. 使用优化后的方式获取大小
    file_size = _get_file_size(upload_file.file)

    try:
        logger.info(f"开始上传文件 {object_name} 到 MinIO (Size: {file_size})...")
        
        # 🟢 2. 执行上传
        # MinIO Python SDK 的 put_object 会自动分片读取 data (stream)
        # 显式设置 part_size=10MB 可以优化大文件上传的内存和稳定性
        client.put_object(
            bucket_name=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=upload_file.file,
            length=file_size,
            content_type=upload_file.content_type or "application/octet-stream",
            part_size=10 * 1024 * 1024  # 10MB part size
        )
        logger.info(f"文件 {object_name} 上传成功")
    except Exception as e:
        logger.error(f"MinIO 上传失败: {e}", exc_info=True)
        raise e
    finally:
        # 🟢 3. 显式关闭，释放 SpooledTemporaryFile 资源
        upload_file.file.close()

    return object_name

def save_bytes_to_minio(data: bytes, object_name: str, content_type: str = "application/octet-stream"):
    client = get_minio_client()
    try:
        if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
            client.make_bucket(settings.MINIO_BUCKET_NAME)
        
        # BytesIO 是纯内存操作，length 直接取 len(data)
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
    """
    注意：此函数会将整个文件读入内存 (return bytes)。
    对于极大的文件 (如 >1GB)，建议在业务层改用 client.get_object 返回的 stream 直接处理，
    而不是调用此辅助函数。
    此函数主要用于处理ragas测试集
    """
    client = get_minio_client()
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
    client = get_minio_client()
    try:
        logger.info(f"正在从 MinIO 删除文件: {object_name}")
        client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        logger.info(f"MinIO 文件删除成功: {object_name}")
    except Exception as e:
        logger.error(f"MinIO 删除失败: {e}", exc_info=True)