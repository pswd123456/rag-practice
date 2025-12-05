# app/api/routes/chat.py
import json
import logging
import uuid
from typing import List, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.domain.schemas.chat import (
    ChatSessionCreate, ChatSessionRead, ChatSessionUpdate,
    MessageRead, ChatRequest, ChatResponse
)
from app.domain.models import User
from app.services.chat import chat_service
from app.services.knowledge import knowledge_crud

logger = logging.getLogger(__name__)

router = APIRouter()

# ------------------ Session Management ------------------

@router.post("/sessions", response_model=ChatSessionRead)
async def create_chat_session(
    data: ChatSessionCreate,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user)
):
    """创建新的对话会话"""
    await knowledge_crud.get_knowledge_by_id(db, data.knowledge_id, current_user.id)
    
    session = await chat_service.create_session(
        db, 
        user_id=current_user.id, 
        knowledge_id=data.knowledge_id,
        title=data.title or "New Chat",
        icon=data.icon or "message-square"
    )
    return session

@router.patch("/sessions/{session_id}", response_model=ChatSessionRead)
async def update_chat_session(
    session_id: uuid.UUID,
    data: ChatSessionUpdate,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user)
):
    """更新会话设置 (Title, Icon, TopK, Knowledge IDs)"""
    if data.knowledge_ids:
        for kid in data.knowledge_ids:
             await knowledge_crud.get_knowledge_by_id(db, kid, current_user.id)

    session = await chat_service.update_session(
        db, session_id, current_user.id, data
    )
    return session

@router.get("/sessions", response_model=List[ChatSessionRead])
async def get_user_sessions(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user)
):
    """获取会话列表"""
    return await chat_service.get_user_sessions(db, current_user.id, skip, limit)

@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_session_detail(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user)
):
    """获取会话详情"""
    return await chat_service.get_session_by_id(db, session_id, current_user.id)

@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user)
):
    """删除会话"""
    await chat_service.delete_session(db, session_id, current_user.id)
    return {"message": "Session deleted"}

@router.get("/sessions/{session_id}/messages", response_model=List[MessageRead])
async def get_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user)
):
    """获取历史消息"""
    return await chat_service.get_session_history(db, session_id, current_user.id)

# ------------------ Chat Interaction ------------------

@router.post("/sessions/{session_id}/completion")
async def chat_completion(
    session_id: uuid.UUID,
    request: ChatRequest,
    db: AsyncSession = Depends(deps.get_db_session),
    current_user: User = Depends(deps.get_current_active_user),
    pipeline_factory = Depends(deps.get_rag_pipeline_factory)
):
    """
    核心对话接口
    """
    session = await chat_service.get_session_by_id(db, session_id, current_user.id)
    
    # 2. 持久化用户消息
    await chat_service.save_message(
        db, session_id, "user", request.query
    )
    
    # 3. 获取历史记录 (用于 Context)
    history_objs = await chat_service.get_session_history(db, session_id, current_user.id)
    
    from langchain_core.messages import HumanMessage, AIMessage
    chat_history = []
    for msg in history_objs:
        if msg.content == request.query and msg.role == "user" and msg == history_objs[-1]:
            continue
        if msg.role == "user":
            chat_history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            chat_history.append(AIMessage(content=msg.content))
    
    # 4. 初始化 Pipeline
    target_kb_ids = session.knowledge_ids if session.knowledge_ids else [session.knowledge_id]
    
    rag_chain = await pipeline_factory(
        knowledge_ids=target_kb_ids,
        llm_model=request.llm_model,
        rerank_model_name=request.rerank_model_name,
        prompt_name=request.prompt_name
    )
    
    # 确定 Top K: 请求参数优先，其次是会话设置，最后默认 3
    final_top_k = request.top_k if request.top_k is not None else session.top_k

    # ================= Stream Mode =================
    if request.stream:
        async def response_generator():
            full_answer = ""
            sources_data = []
            
            async for chunk in rag_chain.astream_with_sources(
                request.query, 
                top_k=final_top_k,
                chat_history=chat_history
            ):
                if isinstance(chunk, list):
                    # Sources
                    for doc in chunk:
                        src = {
                            "filename": doc.metadata.get("source"),
                            "page": doc.metadata.get("page_number") or doc.metadata.get("page"),
                            "content": doc.page_content,
                            "score": doc.metadata.get("rerank_score"),
                            "knowledge_id": doc.metadata.get("knowledge_id")
                        }
                        sources_data.append(src)
                    
                    yield f"event: sources\ndata: {json.dumps(sources_data, ensure_ascii=False)}\n\n"
                
                elif isinstance(chunk, str):
                    full_answer += chunk
                    yield f"event: message\ndata: {json.dumps(chunk)}\n\n"
            
            if full_answer:
                await chat_service.save_message(
                    db, session_id, "assistant", full_answer, sources=sources_data
                )

        return StreamingResponse(response_generator(), media_type="text/event-stream")

    # ================= Blocking Mode =================
    else:
        answer, docs = await rag_chain.async_query(
            request.query, 
            top_k=final_top_k,
            chat_history=chat_history
        )
        
        sources_list = []
        for doc in docs:
            sources_list.append({
                "filename": doc.metadata.get("source"),
                "page": doc.metadata.get("page"),
                "content": doc.page_content,
                "score": doc.metadata.get("rerank_score"),
                "knowledge_id": doc.metadata.get("knowledge_id")
            })
            
        await chat_service.save_message(
            db, session_id, "assistant", answer, sources=sources_list
        )
        
        return ChatResponse(answer=answer, sources=sources_list)