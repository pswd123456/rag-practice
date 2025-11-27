import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import select

from app.domain.models import Knowledge, Document, KnowledgeCreate, KnowledgeStatus, Chunk
from app.services import knowledge_crud
from app.services import document_crud

@pytest.mark.asyncio
async def test_create_knowledge(db_session):
    """
    测试创建知识库
    """
    knowledge_in = KnowledgeCreate(
        name="Test KB",
        description="A test knowledge base",
        chunk_size=1024,
        chunk_overlap=100
    )
    
    kb = await knowledge_crud.create_knowledge(db_session, knowledge_in)
    
    assert kb.id is not None
    assert kb.name == "Test KB"
    assert kb.chunk_size == 1024
    assert kb.status == KnowledgeStatus.NORMAL

@pytest.mark.asyncio
async def test_get_knowledge_not_found(db_session):
    """
    测试获取不存在的知识库抛出异常
    """
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        await knowledge_crud.get_knowledge_by_id(db_session, 9999)
    assert excinfo.value.status_code == 404

@pytest.mark.asyncio
async def test_delete_knowledge_cascading(db_session, mock_minio, mock_chroma):
    """
    [关键] 测试级联删除管道：
    Knowledge -> Documents -> Chunks -> MinIO & Vectors
    """
    # 1. 准备数据：1个 KB，下挂 2个 Document
    kb = Knowledge(name="Cascade Del KB", status=KnowledgeStatus.DELETING)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    doc1 = Document(
        knowledge_base_id=kb.id, 
        filename="doc1.pdf", 
        file_path="1/doc1.pdf", 
        status="COMPLETED"
    )
    doc2 = Document(
        knowledge_base_id=kb.id, 
        filename="doc2.txt", 
        file_path="1/doc2.txt", 
        status="COMPLETED"
    )
    db_session.add(doc1)
    db_session.add(doc2)
    await db_session.commit()
    
    # 添加 Chunk
    chunk1 = Chunk(document_id=doc1.id, chroma_id="uuid-1", chunk_index=0, content="abc")
    
    # 🟢 [FIX] 给 doc2 也添加 Chunk，确保它也会触发向量删除逻辑
    chunk2 = Chunk(document_id=doc2.id, chroma_id="uuid-2", chunk_index=0, content="def")
    
    db_session.add(chunk1)
    db_session.add(chunk2)
    await db_session.commit()
    
    # 2. 执行级联删除
    with patch("app.services.document_crud.VectorStoreManager") as MockVSM:
        mock_vsm_instance = MockVSM.return_value
        mock_vsm_instance.delete_vectors = MagicMock(return_value=True)

        await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id)
        
        # 验证 Chroma 删除了向量
        # 因为 doc1 和 doc2 都有 Chunk，所以 delete_vectors 应该被调用 2 次
        assert mock_vsm_instance.delete_vectors.call_count == 2
    
    # 3. 验证数据库记录已清除
    result_kb = await db_session.get(Knowledge, kb.id)
    assert result_kb is None
    
    result_doc = await db_session.exec(select(Document).where(Document.knowledge_base_id == kb.id))
    assert len(result_doc.all()) == 0
    
    result_chunk = await db_session.get(Chunk, chunk1.id)
    assert result_chunk is None

    # 4. 验证外部资源调用
    # 验证 MinIO 删除了文件
    assert mock_minio.remove_object.call_count >= 2 
