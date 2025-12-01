# tests/test_worker_routing.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi import UploadFile
from arq.connections import RedisSettings

from app.worker import WorkerSettings, process_document_task, delete_knowledge_task
from app.api.routes.knowledge import upload_file
from app.core.config import settings
from app.domain.models import Knowledge, Document

def test_worker_settings_registry():
    """
    [Unit] 验证 Worker 配置中是否注册了所有核心任务函数。
    这是防止 'function not found' 错误的最后一道防线。
    """
    registered_funcs = WorkerSettings.functions
    
    # 验证核心任务是否存在
    assert process_document_task in registered_funcs
    assert delete_knowledge_task in registered_funcs
    
    # 验证 Redis 配置
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert WorkerSettings.redis_settings.host == settings.REDIS_HOST

@pytest.mark.asyncio
async def test_docling_queue_routing(db_session, mock_redis):
    """
    [Integration] 验证 PDF/Docx 文件是否被路由到 Docling (GPU) 队列
    """
    # 1. 准备数据
    kb = Knowledge(name="GPU Queue KB", embed_model="text-embedding-v4")
    db_session.add(kb)
    await db_session.commit()
    
    # 2. 模拟上传 PDF 文件
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "complex_table.pdf"
    mock_file.file = MagicMock() # 模拟 file.file
    mock_file.content_type = "application/pdf"
    
    # Mock MinIO 保存逻辑，避免真实上传
    with patch("app.api.routes.knowledge.save_upload_file") as mock_save:
        mock_save.return_value = "1/complex_table.pdf"
        
        # 3. 调用 API 路由处理函数
        # 🟢 [FIX] 显式传入 redis 参数 (注入 mock 对象)
        await upload_file(
            knowledge_id=kb.id, 
            file=mock_file, 
            db=db_session,
            redis=mock_redis 
        )
        
        # 4. 验证路由逻辑
        # 检查 enqueue_job 是否被调用
        assert mock_redis.enqueue_job.called
        
        # 获取调用参数
        call_args = mock_redis.enqueue_job.call_args
        job_name = call_args[0][0]
        kwargs = call_args[1]
        
        # 断言任务名称
        assert job_name == "process_document_task"
        
        # 断言队列名称为 Docling Queue
        assert kwargs.get("_queue_name") == settings.DOCLING_QUEUE_NAME
        print(f"✅ PDF Routing Verified: Queue -> {kwargs.get('_queue_name')}")

@pytest.mark.asyncio
async def test_default_queue_routing(db_session, mock_redis):
    """
    [Integration] 验证普通 TXT/MD 文件是否被路由到默认 CPU 队列
    """
    # 1. 准备数据
    kb = Knowledge(name="CPU Queue KB")
    db_session.add(kb)
    await db_session.commit()
    
    # 2. 模拟上传 TXT 文件
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "notes.txt"
    mock_file.file = MagicMock()
    mock_file.content_type = "text/plain"
    
    with patch("app.api.routes.knowledge.save_upload_file") as mock_save:
        mock_save.return_value = "2/notes.txt"
        
        # 3. 调用 API
        # 🟢 [FIX] 显式传入 redis 参数
        await upload_file(
            knowledge_id=kb.id, 
            file=mock_file, 
            db=db_session,
            redis=mock_redis
        )
        
        # 4. 验证路由逻辑
        call_args = mock_redis.enqueue_job.call_args
        kwargs = call_args[1]
        
        # 断言队列名称为默认队列
        assert kwargs.get("_queue_name") == settings.DEFAULT_QUEUE_NAME
        print(f"✅ TXT Routing Verified: Queue -> {kwargs.get('_queue_name')}")

@pytest.mark.asyncio
async def test_task_payload_integrity(db_session, mock_redis):
    """
    验证任务入队时传递的 Payload (doc_id) 是否与数据库中的 ID 一致
    """
    kb = Knowledge(name="Payload KB")
    db_session.add(kb)
    await db_session.commit()
    
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.md"
    mock_file.file = MagicMock()
    
    with patch("app.api.routes.knowledge.save_upload_file") as mock_save:
        mock_save.return_value = "path/to/test.md"
        
        # 调用 API
        # 🟢 [FIX] 显式传入 redis 参数
        await upload_file(
            knowledge_id=kb.id, 
            file=mock_file, 
            db=db_session, 
            redis=mock_redis
        )
        
        # 获取 enqueue_job 传递的参数
        call_args = mock_redis.enqueue_job.call_args
        passed_doc_id = call_args[0][1]
        
        # 从数据库查找最新生成的 Document ID
        from sqlmodel import select
        stmt = select(Document).where(Document.filename == "test.md")
        result = await db_session.exec(stmt)
        db_doc = result.first()
        
        # 断言
        assert db_doc is not None
        assert passed_doc_id == db_doc.id