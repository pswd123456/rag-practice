# tests/worker/test_worker_routing.py
import pytest
from unittest.mock import MagicMock, patch
from fastapi import UploadFile
from arq.connections import RedisSettings

from app.worker import WorkerSettings, process_document_task, delete_knowledge_task
from app.api.routes.knowledge import upload_file
from app.core.config import settings
from app.domain.models import Knowledge, Document, User, UserKnowledgeLink, UserKnowledgeRole

def test_worker_settings_registry():
    """
    [Unit] 验证 Worker 配置中是否注册了所有核心任务函数。
    """
    registered_funcs = WorkerSettings.functions
    assert process_document_task in registered_funcs
    assert delete_knowledge_task in registered_funcs
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert WorkerSettings.redis_settings.host == settings.REDIS_HOST

# Helper to create context
async def create_context(db_session, kb_name):
    # Create User
    user = User(email="worker_test@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Create KB
    kb = Knowledge(name=kb_name, embed_model="text-embedding-v4")
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    # Create Link (Permission)
    link = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.OWNER)
    db_session.add(link)
    await db_session.commit()
    
    return user, kb

@pytest.mark.asyncio
async def test_docling_queue_routing(db_session, mock_redis):
    """
    [Integration] 验证 PDF/Docx 文件是否被路由到 Docling (GPU) 队列
    """
    user, kb = await create_context(db_session, "GPU Queue KB")
    
    # 模拟上传 PDF 文件
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "complex_table.pdf"
    mock_file.file = MagicMock() 
    mock_file.content_type = "application/pdf"
    
    with patch("app.api.routes.knowledge.save_upload_file") as mock_save:
        mock_save.return_value = "1/complex_table.pdf"
        
        # 🟢 [FIX] 传入 current_user
        await upload_file(
            knowledge_id=kb.id, 
            file=mock_file, 
            db=db_session,
            redis=mock_redis,
            current_user=user
        )
        
        assert mock_redis.enqueue_job.called
        call_args = mock_redis.enqueue_job.call_args
        kwargs = call_args[1]
        assert kwargs.get("_queue_name") == settings.DOCLING_QUEUE_NAME

@pytest.mark.asyncio
async def test_default_queue_routing(db_session, mock_redis):
    """
    [Integration] 验证普通 TXT/MD 文件是否被路由到默认 CPU 队列
    """
    user, kb = await create_context(db_session, "CPU Queue KB")
    
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "notes.txt"
    mock_file.file = MagicMock()
    mock_file.content_type = "text/plain"
    
    with patch("app.api.routes.knowledge.save_upload_file") as mock_save:
        mock_save.return_value = "2/notes.txt"
        
        # 🟢 [FIX] 传入 current_user
        await upload_file(
            knowledge_id=kb.id, 
            file=mock_file, 
            db=db_session,
            redis=mock_redis,
            current_user=user
        )
        
        call_args = mock_redis.enqueue_job.call_args
        kwargs = call_args[1]
        assert kwargs.get("_queue_name") == settings.DEFAULT_QUEUE_NAME

@pytest.mark.asyncio
async def test_task_payload_integrity(db_session, mock_redis):
    """
    验证任务入队时传递的 Payload (doc_id) 是否与数据库中的 ID 一致
    """
    user, kb = await create_context(db_session, "Payload KB")
    
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "test.md"
    mock_file.file = MagicMock()
    
    with patch("app.api.routes.knowledge.save_upload_file") as mock_save:
        mock_save.return_value = "path/to/test.md"
        
        # 🟢 [FIX] 传入 current_user
        await upload_file(
            knowledge_id=kb.id, 
            file=mock_file, 
            db=db_session, 
            redis=mock_redis,
            current_user=user
        )
        
        call_args = mock_redis.enqueue_job.call_args
        passed_doc_id = call_args[0][1]
        
        from sqlmodel import select
        stmt = select(Document).where(Document.filename == "test.md")
        result = await db_session.exec(stmt)
        db_doc = result.first()
        
        assert db_doc is not None
        assert passed_doc_id == db_doc.id