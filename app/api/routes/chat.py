import json
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


@router.post("/stream")
async def stream_query(
    request: QueryRequest,
    pipeline_factory = Depends(get_rag_pipeline_factory),
):
    """
    SSE (Server-Sent Events) 流式返回。
    事件流顺序:
    1. event: sources \n data: [JSON List of Sources]
    2. event: message \n data: "Token String"  <-- 修改点：使用 JSON 字符串
    ...
    """
    rag_chain = pipeline_factory(
        knowledge_id=request.knowledge_id,
        strategy=request.strategy,
        top_k=settings.TOP_K
    )
    
    async def event_generator():
        logger.debug(f"收到 Stream API 查询: {request.query}")        
        
        # 迭代器会先返回 List[Document]，然后返回 str (token)
        async for chunk in rag_chain.astream_with_sources(request.query):
            
            # 如果是文档列表，构造 sources 事件
            if isinstance(chunk, list):
                sources_data = []
                for doc in chunk:
                    metadata = doc.metadata
                    src = Source(
                        source_filename=metadata.get("source", "未知文件"),
                        page_number=metadata.get("page"),
                        chunk_content=doc.page_content,
                        chunk_id=str(metadata.get("doc_id"))
                    )
                    # Pydantic model_dump 需要 mode='json' 来处理一些特殊类型
                    sources_data.append(src.model_dump(mode='json'))
                
                # 发送 sources 事件
                yield f"event: sources\ndata: {json.dumps(sources_data, ensure_ascii=False)}\n\n"
            
            # 如果是字符串，构造 message 事件 (或者直接 data)
            elif isinstance(chunk, str):
                # [修改] 使用 json.dumps 包装 chunk，保护空格和特殊字符
                yield f"event: message\ndata: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")