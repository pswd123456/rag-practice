import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_rag_pipeline_factory
from app.domain.schemas import QueryRequest, QueryResponse, Source
from app.services.generation import QAService
from app.services.pipelines import RAGPipeline
from app.core.config import settings    
from app.api import deps
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.retrieval import RetrievalService
from typing import List
from langchain_core.documents import Document
from typing import Any

logger = logging.getLogger(__name__)

router = APIRouter()
@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    # 统一使用工厂，不再需要单独注入 store_manager 或 qa_service
    pipeline_factory = Depends(deps.get_rag_pipeline_factory),
):  
    # 1. 一行代码创建 Pipeline，策略逻辑被封装了
    rag_chain = pipeline_factory(
        knowledge_id=request.knowledge_id,
        strategy=request.strategy, # 👈 传入前端请求的策略
        top_k=settings.TOP_K
    )

    # 2. 执行查询
    # async_query 返回 (answer, docs) 元组
    answer, docs = await rag_chain.async_query(request.query)

    # 3. 格式化来源 (保持原有逻辑)
    sources_list = []
    for doc in docs:
        # ... (原有的 metadata 提取代码保持不变) ...
        metadata = doc.metadata
        sources_list.append(Source(
            source_filename=metadata.get("source", "未知文件"),
            page_number=metadata.get("page"),
            chunk_content=doc.page_content,
            chunk_id=str(metadata.get("doc_id"))
        ))

    return QueryResponse(
        answer=answer,
        sources=sources_list
    )


@router.post("/stream", response_model=QueryResponse)
async def stream_query(
    request: QueryRequest,
    pipeline_factory = Depends(get_rag_pipeline_factory),
):
    """
    以流式方式返回回答，便于前端逐步渲染。
    """
    rag_chain = pipeline_factory(
        knowledge_id=request.knowledge_id,
        strategy=request.strategy,
        top_k=settings.TOP_K
    )
    
    async def event_generator():
        """
        生成事件，每个事件包含一个回答片段。
        """
        logger.debug(f"收到 API 查询: {request.query}")        
            
        async for token in rag_chain.astream_answer(request.query):
            yield token
    
    return StreamingResponse(event_generator(), media_type="text/plain")