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
    ChatSessionCreate, ChatSessionRead, 
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
    # 校验 Knowledge 权限
    await knowledge_crud.get_knowledge_by_id(db, data.knowledge_id, current_user.id)
    
    session = await chat_service.create_session(
        db, 
        user_id=current_user.id, 
        knowledge_id=data.knowledge_id,
        title=data.title
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
    核心对话接口：
    1. 校验 Session
    2. 保存 User Message
    3. 检索历史记录
    4. RAG 推理 (流式/非流式)
    5. 保存 Assistant Message
    """
    # 1. 获取 Session (包含权限校验)
    session = await chat_service.get_session_by_id(db, session_id, current_user.id)
    
    # 2. 持久化用户消息
    await chat_service.save_message(
        db, session_id, "user", request.query
    )
    
    # 3. 获取历史记录 (用于 Context)
    # 这里的 history 是 Message 对象列表
    history_objs = await chat_service.get_session_history(db, session_id, current_user.id)
    
    # 转换为 LangChain 友好的格式 (或直接传给 QAService 处理)
    # 假设 QAService 接受 list[("role", "content")] 或类似格式
    # 我们这里简单处理为 list[BaseMessage]
    from langchain_core.messages import HumanMessage, AIMessage
    chat_history = []
    for msg in history_objs:
        # 跳过刚刚保存的当前问题，避免重复
        if msg.content == request.query and msg.role == "user" and msg == history_objs[-1]:
            continue
            
        if msg.role == "user":
            chat_history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            chat_history.append(AIMessage(content=msg.content))
    
    # 4. 初始化 Pipeline
    rag_chain = await pipeline_factory(
        knowledge_id=session.knowledge_id,
        llm_model=request.llm_model,
        rerank_model_name=request.rerank_model_name
    )

    # ================= Stream Mode =================
    if request.stream:
        async def response_generator():
            full_answer = ""
            sources_data = []
            
            async for chunk in rag_chain.astream_with_sources(
                request.query, 
                top_k=request.top_k,
                chat_history=chat_history # 注入历史
            ):
                if isinstance(chunk, list):
                    # Sources
                    for doc in chunk:
                        src = {
                            "filename": doc.metadata.get("source"),
                            "page": doc.metadata.get("page"),
                            "content": doc.page_content,
                            "score": doc.metadata.get("rerank_score")
                        }
                        sources_data.append(src)
                    
                    yield f"event: sources\ndata: {json.dumps(sources_data, ensure_ascii=False)}\n\n"
                
                elif isinstance(chunk, str):
                    full_answer += chunk
                    yield f"event: message\ndata: {json.dumps(chunk)}\n\n"
            
            # 流式结束后，持久化 AI 回复
            if full_answer:
                await chat_service.save_message(
                    db, session_id, "assistant", full_answer, sources=sources_data
                )

        return StreamingResponse(response_generator(), media_type="text/event-stream")

    # ================= Blocking Mode =================
    else:
        answer, docs = await rag_chain.async_query(
            request.query, 
            top_k=request.top_k,
            chat_history=chat_history
        )
        
        sources_list = []
        for doc in docs:
            sources_list.append({
                "filename": doc.metadata.get("source"),
                "page": doc.metadata.get("page"),
                "content": doc.page_content,
                "score": doc.metadata.get("rerank_score")
            })
            
        # 持久化 AI 回复
        await chat_service.save_message(
            db, session_id, "assistant", answer, sources=sources_list
        )
        
        return ChatResponse(answer=answer, sources=sources_list)