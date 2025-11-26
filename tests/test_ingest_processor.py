import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession # 🟢 使用 AsyncSession
import uuid
from app.domain.models import Document, DocStatus, Chunk, Knowledge
from app.services.ingest.processor import process_document_pipeline

@pytest.mark.asyncio # 🟢 标记为异步测试
@patch("app.services.ingest.processor.get_minio_client") 
@patch("app.services.ingest.processor.load_single_document")
@patch("app.services.ingest.processor.setup_vector_store")
@patch("app.services.ingest.processor.setup_embed_model")
async def test_process_document_pipeline_success(
    mock_setup_embed,
    mock_setup_vstore,
    mock_load_doc,
    mock_get_minio_client,
    db: AsyncSession, # 🟢 注入 AsyncSession
):
    
    random_suffix = uuid.uuid4().hex[:8]
    # --- 1. 准备测试数据 (Arrange) ---
    kb = Knowledge(name=f"test_kb_processo_{random_suffix}", description="for unit test")
    db.add(kb)
    await db.commit() # 🟢 await
    await db.refresh(kb) # 🟢 await

    doc = Document(
        knowledge_base_id=kb.id,
        filename="test_report.pdf",
        file_path="1/test_report.pdf",
        status=DocStatus.PENDING
    )
    db.add(doc)
    await db.commit() # 🟢 await
    await db.refresh(doc) # 🟢 await

    # --- 2. 配置 Mock 的行为 (Arrange Mocks) ---
    mock_minio_instance = MagicMock()
    mock_get_minio_client.return_value = mock_minio_instance
    mock_minio_instance.fget_object.return_value = None 

    from langchain_core.documents import Document as LCDocument
    mock_load_doc.return_value = [
        LCDocument(page_content="This is page 1 content", metadata={"page": 1}),
        LCDocument(page_content="This is page 2 content", metadata={"page": 2})
    ]

    mock_vstore_instance = MagicMock()
    mock_vstore_instance.add_documents.return_value = ["chroma_id_1", "chroma_id_2"]
    mock_setup_vstore.return_value = mock_vstore_instance

    # --- 3. 执行被测函数 (Act) ---
    # 🟢 process_document_pipeline 现在是异步的，必须 await
    await process_document_pipeline(db, doc.id)

    # --- 4. 验证结果 (Assert) ---
    await db.refresh(doc) # 🟢 await
    assert doc.status == DocStatus.COMPLETED
    
    # 🟢 异步查询
    result = await db.exec(select(Chunk).where(Chunk.document_id == doc.id))
    chunks = result.all()
    assert len(chunks) == 2
    
    # 验证 Mock 调用
    mock_get_minio_client.assert_called_once()
    # 注意：由于使用了 asyncio.to_thread，mock 调用依然会被捕获，因为 mock 对象是线程共享的
    mock_minio_instance.fget_object.assert_called_once()

    # 清理 (Transaction Rollback 会自动处理，但手动删也可以)
    # 这里我们依赖 db fixture 的 rollback 机制即可