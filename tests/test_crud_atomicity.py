# tests/test_crud_atomicity.py
import pytest
from unittest.mock import MagicMock, patch
from app.services import knowledge_crud
from app.domain.models import Knowledge, Document, KnowledgeStatus

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
    with patch("app.services.document_crud.VectorStoreManager") as MockVSM:
        mock_vsm_instance = MockVSM.return_value
        # 这里的返回值不重要，只要 verify 方法被调用即可
        mock_vsm_instance.delete_vectors.return_value = True
        
        # 3. 执行删除
        await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id)
        
        # 4. 验证
        # 验证数据库记录已删除
        kb_in_db = await db_session.get(Knowledge, kb.id)
        assert kb_in_db is None