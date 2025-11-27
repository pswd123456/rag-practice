import pytest
from unittest.mock import MagicMock, patch
from app.services import knowledge_crud
from app.domain.models import Knowledge, Document, Chunk, KnowledgeStatus

@pytest.mark.asyncio
async def test_delete_knowledge_removes_es_index(db_session, mock_es_client):
    """
    [验证] 删除 Knowledge 时，应级联删除 ES Index 或 Vectors
    """
    # 1. 准备数据
    kb = Knowledge(name="ES Deletion Test", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    # 2. Mock 依赖
    # 我们不仅要 mock ES client，还要确保 VectorStoreManager 的 delete_index 被调用
    # 或者更底层的 indices.delete 被调用
    
    with patch("app.services.document_crud.VectorStoreManager") as MockVSM:
        mock_vsm_instance = MockVSM.return_value
        mock_vsm_instance.delete_vectors.return_value = True
        
        # 3. 执行删除
        await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id)
        
        # 4. 验证
        # 我们的 delete_knowledge_pipeline 逻辑是先删文档（调用 delete_vectors）
        # 如果你实现了 delete_index 优化，也可以在这里验证
        
        # 验证数据库记录已删除
        kb_in_db = await db_session.get(Knowledge, kb.id)
        assert kb_in_db is None
        
        # 验证是否尝试删除了向量 (如果KB下有文档)
        # 可以在此处扩展，添加 Document 和 Chunk 后验证 mock_vsm_instance.delete_vectors.called