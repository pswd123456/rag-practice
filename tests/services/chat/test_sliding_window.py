import pytest
import uuid
from app.domain.models import Message, ChatSession, User
from app.services.chat import chat_service

@pytest.mark.asyncio
async def test_get_session_history_sliding_window(db_session):
    # 1. 准备数据
    user = User(email="window@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    session = ChatSession(user_id=user.id, knowledge_id=1, title="Window Test")
    db_session.add(session)
    await db_session.commit()
    
    # 插入 10 条消息 (Msg 1 ~ Msg 10)
    for i in range(1, 11):
        msg = Message(
            session_id=session.id, 
            role="user" if i % 2 else "assistant", 
            content=f"Msg {i}"
        )
        db_session.add(msg)
    await db_session.commit()
    
    # 2. 测试滑动窗口 (取最近 3 条)
    # 预期结果: Msg 8, Msg 9, Msg 10 (按时间正序)
    history = await chat_service.get_session_history(
        db_session, 
        session.id, 
        user.id, 
        limit=3
    )
    
    # 3. 验证
    assert len(history) == 3
    assert history[0].content == "Msg 8"
    assert history[-1].content == "Msg 10"
    
    # 验证顺序 (Msg 8 应该比 Msg 10 早)
    assert history[0].created_at < history[-1].created_at