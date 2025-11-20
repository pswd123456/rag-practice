import logging
from fastapi import UploadFile
from minio import Minio
from app.core.config import settings
import io

logger = logging.getLogger(__name__)

# 初始化 MinIO 客户端
# 注意：在生产环境中，客户端实例最好作为单例或依赖注入管理
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE
)

def save_upload_file(upload_file: UploadFile, knowledge_id: int) -> str:
    """
    将上传的文件流直接推送到 MinIO，并返回对象路径 (Object Name)
    """
    # 1. 确保 Bucket 存在 (可选，生产环境通常预先建好)
    if not minio_client.bucket_exists(settings.MINIO_BUCKET_NAME):
        minio_client.make_bucket(settings.MINIO_BUCKET_NAME)

    # 2. 生成在 MinIO 中的对象路径 (Key)
    # 格式: knowledge_id/filename (例如: 101/report.pdf)
    # 这样天然实现了按知识库隔离文件
    object_name = f"{knowledge_id}/{upload_file.filename}"

    # 3. 上传文件
    # UploadFile.file 是一个 SpooledTemporaryFile，类似文件对象
    #我们需要获取文件大小，MinIO put_object 需要知道 size
    upload_file.file.seek(0, 2) # 移动到末尾
    file_size = upload_file.file.tell()
    upload_file.file.seek(0) # 移回开头

    try:
        logger.info(f"开始上传文件 {object_name} 到 MinIO (Size: {file_size})...")
        minio_client.put_object(
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

    # 返回 MinIO 中的 Key，这将被存入数据库的 file_path 字段
    return object_name

def delete_file_from_minio(object_name: str):
    """
    从 MinIO 中删除指定对象
    """
    try:
        logger.info(f"正在从 MinIO 删除文件: {object_name}")
        minio_client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
        logger.info(f"MinIO 文件删除成功: {object_name}")
    except Exception as e:
        # 删除失败通常不应该阻断后续的 DB 删除，记录错误即可
        logger.error(f"MinIO 删除失败: {e}", exc_info=True)