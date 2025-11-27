# tests/test_knowledge_crud.py
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import select

# 🟢 [FIX] 移除 Chunk
from app.domain.models import Knowledge, Document, KnowledgeCreate, KnowledgeStatus
from app.services import knowledge_crud

@pytest.mark.asyncio
async def test_create_knowledge(db_session):
    knowledge_in = KnowledgeCreate(
        name="Test KB",
        chunk_size=1024,
        chunk_overlap=100
    )
    kb = await knowledge_crud.create_knowledge(db_session, knowledge_in)
    assert kb.id is not None
    assert kb.name == "Test KB"

@pytest.mark.asyncio
async def test_delete_knowledge_cascading(db_session, mock_minio):
    """
    测试级联删除：Knowledge -> Documents -> MinIO & ES
    """
    # 1. 准备数据
    kb = Knowledge(name="Cascade Del KB", status=KnowledgeStatus.DELETING)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    doc1 = Document(knowledge_base_id=kb.id, filename="doc1.pdf", file_path="1/doc1.pdf", status="COMPLETED")
    db_session.add(doc1)
    await db_session.commit()
    
    # 2. Mock VectorStoreManager (针对 ES)
    with patch("app.services.document_crud.VectorStoreManager") as MockVSM:
        mock_vsm_instance = MockVSM.return_value
        # 模拟 delete_by_doc_id 成功
        mock_vsm_instance.delete_by_doc_id.return_value = True

        # 执行删除
        await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id)
        
        # 验证 ES 删除被调用
        # 因为 doc1 存在，document_crud.delete_document_and_vectors 会被调用
        # 进而调用 delete_by_doc_id
        assert mock_vsm_instance.delete_by_doc_id.called

    # 3. 验证 DB 清除
    result_kb = await db_session.get(Knowledge, kb.id)
    assert result_kb is None
    
    result_doc = await db_session.exec(select(Document).where(Document.knowledge_base_id == kb.id))
    assert len(result_doc.all()) == 0

    # 4. 验证 MinIO 删除
    assert mock_minio.remove_object.called