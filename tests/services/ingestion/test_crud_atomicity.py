# tests/services/ingestion/test_crud_atomicity.py
import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import select
from app.services.knowledge import knowledge_crud
from app.domain.models import Knowledge, Document, KnowledgeStatus, User, UserKnowledgeLink, UserKnowledgeRole, ChatSession

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

@pytest.mark.asyncio
async def test_delete_knowledge_cascades_chat_sessions(db_session):
    """
    [BugFix] 验证删除 Knowledge 时，是否会级联删除关联的 ChatSession，
    防止出现 'null value in column knowledge_id violates not-null constraint' 错误。
    """
    # 1. 准备数据
    user = User(email="cascade_chat@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    kb = Knowledge(name="Cascade Chat KB", status=KnowledgeStatus.NORMAL)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    
    link = UserKnowledgeLink(user_id=user.id, knowledge_id=kb.id, role=UserKnowledgeRole.OWNER)
    db_session.add(link)
    await db_session.commit()

    # 2. 创建关联的 ChatSession
    session = ChatSession(
        user_id=user.id,
        knowledge_id=kb.id,
        title="Dependent Session"
    )
    db_session.add(session)
    await db.commit()

    # 3. 执行删除管道
    # 如果没有修复，这里会抛出 IntegrityError
    await knowledge_crud.delete_knowledge_pipeline(db_session, kb.id, user.id)

    # 4. 验证 Session 是否被删除
    # session_in_db = await db_session.get(ChatSession, session.id)
    # assert session_in_db is None 
    # 注意：get 可能被缓存，使用 select 确认
    stmt = select(ChatSession).where(ChatSession.id == session.id)
    result = await db_session.exec(stmt)
    assert result.first() is None