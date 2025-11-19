import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_rag_pipeline
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
    store_manager: VectorStoreManager = Depends(deps.get_vector_store_manager),
    qa_service: QAService = Depends(deps._get_qa_service)
):  
    """
    接收用户查询并返回 RAG 管道的答案。
    """
# 1. 基础过滤条件 (知识库隔离)
    search_kwargs: dict = {"k": settings.TOP_K}
    if request.knowledge_id:
        search_kwargs["filter"] = {"knowledge_id": request.knowledge_id}

    # 2. 根据 strategy 调整检索策略 (A/B 测试逻辑)
    if request.strategy == "dense_only":
        # 策略 A: 纯向量检索 (默认)
        logger.info(">>> 正在执行: 纯向量检索策略") # 👈 埋点 A
        retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)
        
    elif request.strategy == "hybrid":
        logger.info(">>> 正在执行: 混合检索策略 (暂未实现，回退到默认)")
        # 策略 B: 混合检索 (假设你未来实现了 hybrid_retriever)
        # retriever = HybridRetriever(..., search_kwargs=search_kwargs)
        # 暂时先用向量检索顶替，防止报错
        retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)
        
    elif request.strategy == "rerank":
        logger.info(f">>> 正在执行: 默认兜底策略 (strategy={request.strategy})")
        # 策略 C: 向量检索 + 重排序
        # retriever = store_manager.vector_store.as_retriever(search_kwargs={"k": 20}) # 先召回更多
        # retriever = RerankRetriever(base_retriever=retriever)
        # 暂时先用向量检索顶替，防止报错
        retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)
        
    else:
        # 默认兜底
        retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)

    # 3. 动态组装 Pipeline
    # 注意：这里不再使用 deps.get_rag_pipeline() 获取的单例
    # 而是现场组装一个临时的 Pipeline 对象
    retrieval_service = RetrievalService(retriever)
    rag_chain = RAGPipeline(retrieval_service, qa_service)

    # 4. 执行
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