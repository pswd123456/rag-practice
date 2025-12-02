# tests/services/ingestion/test_crud_atomicity.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.knowledge import knowledge_crud
from app.domain.models import Knowledge, Document, KnowledgeStatus, User, UserKnowledgeLink, UserKnowledgeRole

@pytest.mark.asyncio
async def test_delete_knowledge_removes_es_index(db_session, mock_es_client):
    """
    [验证] 删除 Knowledge 时，应级联删除 ES Index (防止资源泄露)
    """
    # 1. 准备数据 (User + KB + Link)
    user = User(email="atomicity@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    kb = Knowledge(name="ES Deletion Test", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    link = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.OWNER)
    db_session.add(link)
    await db_session.commit()
    
    # 2. Mock 依赖
    with patch("app.services.knowledge.knowledge_crud.VectorStoreManager") as MockVSM, \
         patch("app.services.knowledge.knowledge_crud.setup_embed_model") as MockSetupEmbed:
        
        mock_vsm_instance = MockVSM.return_value
        mock_vsm_instance.delete_index.return_value = True
        
        # 3. 执行删除 (🟢 传入 user_id)
        await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id, user.id)
        
        # 4. 验证
        assert mock_vsm_instance.delete_index.called
        
        kb_in_db = await db_session.get(Knowledge, kb.id)
        assert kb_in_db is None