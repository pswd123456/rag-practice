import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import Session, select

from app.domain.models import Document, DocStatus, Chunk, Knowledge
from app.services.ingest.processor import process_document_pipeline

# 假设你的 processor.py 放在 app/services/ingest/ 目录下

@patch("app.services.ingest.processor.minio_client")  # 1. Mock MinIO
@patch("app.services.ingest.processor.load_single_document") # 2. Mock 文件加载器
@patch("app.services.ingest.processor.setup_vector_store")   # 3. Mock 向量库设置
@patch("app.services.ingest.processor.setup_embed_model")    # 4. Mock Embedding 模型
def test_process_document_pipeline_success(
    mock_setup_embed,
    mock_setup_vstore,
    mock_load_doc,
    mock_minio,
    db: Session,
):
    # --- 1. 准备测试数据 (Arrange) ---
    # 创建一个临时的 Knowledge 和 Document 记录
    kb = Knowledge(name="test_kb_processor", description="for unit test")
    db.add(kb)
    db.commit()
    db.refresh(kb)

    doc = Document(
        knowledge_base_id=kb.id, #type: ignore
        filename="test_report.pdf",
        file_path="1/test_report.pdf",
        status=DocStatus.PENDING
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # --- 2. 配置 Mock 的行为 (Arrange Mocks) ---
    
    # (A) 模拟 MinIO 下载不报错
    mock_minio.fget_object.return_value = None 

    # (B) 模拟 load_single_document 返回一个 LangChain Document 对象
    from langchain_core.documents import Document as LCDocument
    mock_load_doc.return_value = [
        LCDocument(page_content="This is page 1 content", metadata={"page": 1}),
        LCDocument(page_content="This is page 2 content", metadata={"page": 2})
    ]

    # (C) 模拟 VectorStore 的 add_documents 方法
    # 我们不需要真的连 Chroma，只需要它返回几个 ID 即可
    mock_vstore_instance = MagicMock()
    mock_vstore_instance.add_documents.return_value = ["chroma_id_1", "chroma_id_2"]
    mock_setup_vstore.return_value = mock_vstore_instance

    # --- 3. 执行被测函数 (Act) ---
    process_document_pipeline(db, doc.id)#type: ignore

    # --- 4. 验证结果 (Assert) ---

    # (A) 验证 Document 状态是否更新为 COMPLETED
    db.refresh(doc)
    assert doc.status == DocStatus.COMPLETED
    assert doc.error_message is None

    # (B) 验证是否在 Postgres 中生成了对应的 Chunk 记录
    chunks = db.exec(select(Chunk).where(Chunk.document_id == doc.id)).all()
    assert len(chunks) == 2 # 因为我们在 mock_load_doc 里造了2页数据
    
    # 检查第一个 Chunk 的数据准确性
    c1 = chunks[0]
    assert c1.content == "This is page 1 content"
    assert c1.chroma_id == "chroma_id_1"
    assert c1.chunk_index == 0
    
    # (C) 验证 Mock 对象是否按预期被调用了
    # 验证是否尝试从 MinIO 下载了正确的文件路径
    mock_minio.fget_object.assert_called_once()
    call_args = mock_minio.fget_object.call_args
    assert call_args.kwargs['object_name'] == "1/test_report.pdf"
    
    # 验证是否调用了向量库添加数据
    mock_vstore_instance.add_documents.assert_called_once()

    # --- 清理数据 (Teardown) - 如果使用 pytest-asyncio+rollback 模式可省略 ---
    db.delete(doc)
    db.delete(kb)
    for c in chunks:
        db.delete(c)
    db.commit()