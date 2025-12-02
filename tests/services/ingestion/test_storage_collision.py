# tests/services/test_storage_collision.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi import UploadFile
from app.services.minio import file_storage

@pytest.mark.asyncio
async def test_save_upload_file_uniqueness():
    """
    [Critical Fix Validation]
    验证同名文件上传时，生成的 MinIO 对象路径是否唯一。
    防止覆盖覆盖导致的数据丢失问题。
    """
    # 1. 准备 Mock 数据
    knowledge_id = 101
    filename = "duplicate_report.pdf"
    content_type = "application/pdf"
    
    # 模拟 UploadFile 对象
    # 注意：FastAPI 的 UploadFile 在测试中通常需要 Mock file 属性
    mock_file_1 = MagicMock(spec=UploadFile)
    mock_file_1.filename = filename
    mock_file_1.content_type = content_type
    mock_file_1.file = MagicMock() # file-like object

    mock_file_2 = MagicMock(spec=UploadFile)
    mock_file_2.filename = filename
    mock_file_2.content_type = content_type
    mock_file_2.file = MagicMock()

    # 2. Mock MinIO 客户端
    # 我们不需要真实上传，只需要验证生成的 object_name
    with patch("app.services.minio.file_storage.get_minio_client") as mock_get_client:
        mock_client = mock_get_client.return_value
        mock_client.bucket_exists.return_value = True
        
        # 3. 执行两次上传
        # 这里实际上会调用 mock_client.put_object
        saved_path_1 = file_storage.save_upload_file(mock_file_1, knowledge_id)
        saved_path_2 = file_storage.save_upload_file(mock_file_2, knowledge_id)

        print(f"\nPath 1: {saved_path_1}")
        print(f"Path 2: {saved_path_2}")

        # 4. 验证核心逻辑
        # 即使文件名和知识库ID相同，物理存储路径必须不同
        assert saved_path_1 != saved_path_2
        
        # 验证路径结构包含 UUID (长度肯定比 原长度长)
        # 原逻辑: 101/duplicate_report.pdf
        # 新逻辑: 101/{uuid}_duplicate_report.pdf
        expected_min_len = len(f"{knowledge_id}/{filename}") + 32 # uuid hex length
        assert len(saved_path_1) >= expected_min_len
        assert filename in saved_path_1