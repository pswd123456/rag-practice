import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from sqlmodel import select

from app.domain.models import Document, Chunk, Knowledge
from app.services import document_crud

@pytest.mark.asyncio
async def test_delete_document_atomicity_failure(db_session):
    """
    [关键] 测试删除原子性：如果 Chroma 删除失败，DB 必须回滚，不能删除文档记录。
    """
    # 1. 准备数据
    kb = Knowledge(name="Atomicity KB")
    db_session.add(kb)
    await db_session.commit()
    
    doc = Document(
        knowledge_base_id=kb.id, 
        filename="critical.pdf", 
        file_path="1/critical.pdf",
        status="COMPLETED"
    )
    db_session.add(doc)
    await db_session.commit()
    
    chunk = Chunk(document_id=doc.id, chroma_id="uuid-critical", chunk_index=0, content="import data")
    db_session.add(chunk)
    await db_session.commit()

    # 2. 模拟 Chroma 删除失败抛出异常
    with patch("app.services.document_crud.VectorStoreManager") as MockVSM:
        mock_vsm_instance = MockVSM.return_value
        # 模拟抛出 ValueError
        mock_vsm_instance.delete_vectors.side_effect = ValueError("Chroma Connection Timeout")

        # 3. 调用删除逻辑，期望捕获 500 异常
        with pytest.raises(HTTPException) as excinfo:
            await document_crud.delete_document_and_vectors(db_session, doc.id)
        
        assert excinfo.value.status_code == 500
        assert "向量库删除失败" in excinfo.value.detail

    # 4. 关键验证：数据库状态必须回滚
    # Document 应该还在
    db_doc = await db_session.get(Document, doc.id)
    assert db_doc is not None
    assert db_doc.filename == "critical.pdf"
    
    # Chunk 应该还在
    db_chunk = await db_session.get(Chunk, chunk.id)
    assert db_chunk is not None

@pytest.mark.asyncio
async def test_delete_document_success(db_session, mock_minio):
    """
    测试正常删除流程
    """
    # 1. 准备数据
    kb = Knowledge(name="Normal KB")
    db_session.add(kb)
    await db_session.commit()
    
    doc = Document(
        knowledge_base_id=kb.id, 
        filename="normal.pdf", 
        file_path="1/normal.pdf",
        status="COMPLETED"
    )
    db_session.add(doc)
    await db_session.commit()
    
    # 2. 正常删除
    with patch("app.services.document_crud.VectorStoreManager") as MockVSM:
        mock_vsm_instance = MockVSM.return_value
        mock_vsm_instance.delete_vectors.return_value = True

        response = await document_crud.delete_document_and_vectors(db_session, doc.id)
        # 🟢 [FIX] 修改断言字符串，匹配代码返回的 "删除成功"
        assert "删除成功" in response["message"]

    # 3. 验证 DB 已删除
    db_doc = await db_session.get(Document, doc.id)
    assert db_doc is None

    # 4. 验证 MinIO 删除被调用
    assert mock_minio.remove_object.called