import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_rag_pipeline
from app.domain.schemas import QueryRequest, QueryResponse, Source
from app.services.pipelines import RAGPipeline
from typing import List
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

router = APIRouter()
@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    rag_chain: RAGPipeline = Depends(get_rag_pipeline),
):
    """
    接收用户查询并返回 RAG 管道的答案。
    """
    if rag_chain is None:
        return {"answer": "错误：RAG 管道未初始化，请检查服务器日志。"}

    logger.debug(f"收到 API 查询: {request.query}")

    # 使用 .async_query()，它现在返回 (answer_text, docs)
    response_text, docs = await rag_chain.async_query(request.query)

    sources_list: List[Source] = []

    for doc in docs:
        metadata = doc.metadata
        
        # 从 metadata 中提取关键信息
        source_filename = metadata.get("source", "未知文件")
        page_number = metadata.get("page")
        chunk_id = metadata.get("doc_id") # 我们在 Worker 中注入的 doc_id (Document ID)

        sources_list.append(Source(
            source_filename=source_filename,
            page_number=int(page_number) if page_number is not None else None,
            chunk_content=doc.page_content, # 返回切片内容
            chunk_id=str(chunk_id) if chunk_id is not None else None,
        ))

    return QueryResponse(
            answer=response_text,
            sources=sources_list
        )


@router.post("/stream", response_model=QueryResponse)
async def stream_query(
    request: QueryRequest,
    rag_chain: RAGPipeline = Depends(get_rag_pipeline),
):
    """
    以流式方式返回回答，便于前端逐步渲染。
    """
    async def event_generator():
        """
        生成事件，每个事件包含一个回答片段。
        """
        logger.debug(f"收到 API 查询: {request.query}")        
            
        async for token in rag_chain.astream_answer(request.query):
            yield token
    
    return StreamingResponse(event_generator(), media_type="text/plain")