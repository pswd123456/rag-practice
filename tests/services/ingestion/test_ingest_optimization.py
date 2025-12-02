import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.ingest import ingest
from app.domain.models import Document, Knowledge, DocStatus

@pytest.mark.asyncio
async def test_process_document_pipeline_session_management():
    """
    [Optimization Test] 验证 process_document_pipeline 是否正确进行了 Session 拆分管理，
    确保长耗时操作期间不占用数据库连接。
    """
    # 1. 准备 Mock 数据
    doc_id = 1
    mock_doc = Document(
        id=doc_id, 
        knowledge_base_id=10, 
        filename="test.pdf", 
        file_path="10/test.pdf",
        status=DocStatus.PENDING
    )
    mock_kb = Knowledge(
        id=10, 
        name="Test KB", 
        chunk_size=500, 
        chunk_overlap=50, 
        embed_model="text-embedding-v4"
    )
    # 设置关联关系 (模拟 Eager Load)
    mock_doc.knowledge_base = mock_kb

    # 2. Mock 数据库 Session 和 async_session_maker
    mock_session = AsyncMock()
    
    # [关键修复]
    # 显式创建一个 MagicMock 作为 db.exec 的返回值 (Result 对象)
    # 这样 result.first() 就是同步调用，直接返回 mock_doc
    mock_result = MagicMock()
    mock_result.first.return_value = mock_doc
    
    # 设置 session.exec (AsyncMock) 的返回值
    mock_session.exec = AsyncMock(return_value=mock_result)
    
    # 模拟 get 直接获取 (用于后续重新获取)
    mock_session.get.return_value = mock_doc

    mock_db_context = AsyncMock()
    mock_db_context.__aenter__.return_value = mock_session
    mock_db_context.__aexit__.return_value = None

    # 3. Mock 耗时操作 (Docling, MinIO, ES)
    with patch("app.services.ingest.ingest.async_session_maker", return_value=mock_db_context) as MockSessionMaker, \
         patch("app.services.ingest.ingest.get_minio_client") as mock_minio, \
         patch("app.services.ingest.ingest.load_and_chunk_docling_document", return_value=[]) as mock_docling, \
         patch("app.services.ingest.ingest.VectorStoreManager") as mock_vsm:
        
        # 执行 Pipeline (不传 db 参数)
        await ingest.process_document_pipeline(doc_id)

        # 4. 验证 Session 获取次数
        # 预期至少获取 2 次 Session: 
        #   1. 开始时获取 (Read Meta + Update PROCESSING)
        #   2. 结束时获取 (Update COMPLETED)
        # 且在耗时操作期间 Session 应该是关闭的
        assert MockSessionMaker.call_count >= 2
        
        # 验证第一次 Session 用于获取数据和更新状态
        assert mock_session.commit.called
        
        # 验证耗时操作被调用
        mock_minio.return_value.fget_object.assert_called()
        mock_docling.assert_called()

        print("\n✅ Session split verification passed: Session acquired separate times.")

@pytest.mark.asyncio
async def test_process_document_pipeline_error_handling():
    """
    [Optimization Test] 验证在长耗时操作失败时，能否重新获取 Session 并标记 FAILED
    """
    doc_id = 2
    mock_doc = Document(id=doc_id, knowledge_base_id=10, filename="fail.pdf", file_path="10/fail.pdf")
    mock_kb = Knowledge(id=10, name="Test KB")
    mock_doc.knowledge_base = mock_kb

    mock_session = AsyncMock()
    
    # [关键修复] 同样应用到异常处理测试
    mock_result = MagicMock()
    mock_result.first.return_value = mock_doc
    mock_session.exec = AsyncMock(return_value=mock_result)
    
    # 模拟 get: 第一次在 Phase 1 成功，第二次在 Error Handler 中成功
    mock_session.get.side_effect = [mock_doc, mock_doc] 

    mock_db_context = AsyncMock()
    mock_db_context.__aenter__.return_value = mock_session

    # 模拟 MinIO 下载抛出异常
    with patch("app.services.ingest.ingest.async_session_maker", return_value=mock_db_context), \
         patch("app.services.ingest.ingest.get_minio_client", side_effect=ValueError("Download Error")):
        
        await ingest.process_document_pipeline(doc_id)

        # 验证是否重新获取 Session 并更新了状态
        # 这里的逻辑是: 
        # 1. Session 1 (Start) -> Commit
        # 2. Exception -> Session 2 (Error Handler) -> Commit
        assert mock_doc.status == DocStatus.FAILED
        assert "Download Error" in mock_doc.error_message