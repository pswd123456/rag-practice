import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, select
import uuid
from app.domain.models import Document, DocStatus, Chunk, Knowledge
from app.services.ingest.processor import process_document_pipeline

# 🔴 修改点 1: Patch 的目标变了
# 从 .minio_client 变成了 .get_minio_client
@patch("app.services.ingest.processor.get_minio_client") 
@patch("app.services.ingest.processor.load_single_document")
@patch("app.services.ingest.processor.setup_vector_store")
@patch("app.services.ingest.processor.setup_embed_model")
def test_process_document_pipeline_success(
    mock_setup_embed,
    mock_setup_vstore,
    mock_load_doc,
    mock_get_minio_client, # 🔴 修改点 2: 参数名改一下，更清晰
    db: Session,
):
    
    random_suffix = uuid.uuid4().hex[:8]
    # --- 1. 准备测试数据 (Arrange) ---
    kb = Knowledge(name=f"test_kb_processo_{random_suffix}", description="for unit test")
    db.add(kb)
    db.commit()
    db.refresh(kb)

    doc = Document(
        knowledge_base_id=kb.id,
        filename="test_report.pdf",
        file_path="1/test_report.pdf",
        status=DocStatus.PENDING
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # --- 2. 配置 Mock 的行为 (Arrange Mocks) ---
    
    # 🔴 修改点 3: 模拟工厂函数的行为
    # get_minio_client() 调用后返回一个 mock 实例
    mock_minio_instance = MagicMock()
    mock_get_minio_client.return_value = mock_minio_instance
    
    # 设置这个实例的方法行为
    mock_minio_instance.fget_object.return_value = None 

    # (B) 模拟 load_single_document
    from langchain_core.documents import Document as LCDocument
    mock_load_doc.return_value = [
        LCDocument(page_content="This is page 1 content", metadata={"page": 1}),
        LCDocument(page_content="This is page 2 content", metadata={"page": 2})
    ]

    # (C) 模拟 VectorStore
    mock_vstore_instance = MagicMock()
    mock_vstore_instance.add_documents.return_value = ["chroma_id_1", "chroma_id_2"]
    mock_setup_vstore.return_value = mock_vstore_instance

    # --- 3. 执行被测函数 (Act) ---
    process_document_pipeline(db, doc.id)

    # --- 4. 验证结果 (Assert) ---
    db.refresh(doc)
    assert doc.status == DocStatus.COMPLETED
    
    chunks = db.exec(select(Chunk).where(Chunk.document_id == doc.id)).all()
    assert len(chunks) == 2
    
    # 🔴 修改点 4: 验证 Mock 调用
    # 验证 get_minio_client 被调用了
    mock_get_minio_client.assert_called_once()
    # 验证返回的实例执行了 fget_object
    mock_minio_instance.fget_object.assert_called_once()
    
    # 检查参数
    call_args = mock_minio_instance.fget_object.call_args
    # 注意：这里你可能需要根据最新的 processor.py 代码确认参数位置
    # 之前代码是 kwargs['object_name']，确保 processor.py 里也是这么传的
    assert call_args.kwargs.get('object_name') == "1/test_report.pdf" or \
           call_args.args[1] == "1/test_report.pdf"

    # 清理
    db.delete(doc)
    db.delete(kb)
    for c in chunks:
        db.delete(c)
    db.commit()