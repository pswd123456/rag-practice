import logging
from app.schemas.chat import QueryRequest, QueryResponse
from app.services.pipeline import RAGPipeline
from fastapi import APIRouter, Depends
from app.services.chat import run_rag_chain

logger = logging.getLogger(__name__)

router = APIRouter()
@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest, 
    rag_chain: RAGPipeline = Depends(run_rag_chain)
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