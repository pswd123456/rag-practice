# tests/test_crud_atomicity.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.knowledge import knowledge_crud
from app.domain.models import Knowledge, Document, KnowledgeStatus

@pytest.mark.asyncio
async def test_delete_knowledge_removes_es_index(db_session, mock_es_client):
    """
    [验证] 删除 Knowledge 时，应级联删除 ES Index (防止资源泄露)
    """
    # 1. 准备数据
    kb = Knowledge(name="ES Deletion Test", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    # 2. Mock 依赖
    # 注意：我们要 Mock knowledge_crud 模块内部引用的 VectorStoreManager
    # 同时也要 Mock setup_embed_model，因为它在初始化 Manager 时会被调用
    with patch("app.services.knowledge.knowledge_crud.VectorStoreManager") as MockVSM, \
         patch("app.services.knowledge.knowledge_crud.setup_embed_model") as MockSetupEmbed:
        
        mock_vsm_instance = MockVSM.return_value
        mock_vsm_instance.delete_index.return_value = True
        
        # 3. 执行删除
        await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id)
        
        # 4. 验证
        # 验证 ES 索引删除方法被调用
        assert mock_vsm_instance.delete_index.called, "删除知识库时未调用 delete_index，存在资源泄露风险"
        
        # 验证数据库记录已删除
        kb_in_db = await db_session.get(Knowledge, kb.id)
        assert kb_in_db is None