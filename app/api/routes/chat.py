import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_rag_pipeline
from app.domain.schemas import QueryRequest, QueryResponse
from app.services.pipelines import RAGPipeline

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

    # 使用 .ainvoke() 来进行异步调用 (FastAPI 的最佳实践)
    response_text = await rag_chain.async_query(request.query)

    return {"answer": response_text}


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