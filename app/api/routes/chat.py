import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api import deps
from app.domain.schemas import QueryRequest, QueryResponse, Source
from app.core.config import settings    

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    pipeline_factory = Depends(deps.get_rag_pipeline_factory),
):  
    # 1. 创建 Pipeline
    # 注意：strategy 已移除，Factory 会默认使用 "hybrid" + "rerank" 架构
    rag_chain = await pipeline_factory(
        knowledge_id=request.knowledge_id,
        llm_model=request.llm_model,
        rerank_model_name=request.rerank_model_name
    )

    # 2. 执行查询 (Async)
    # 将 request.top_k (Final K) 传给 Pipeline 进行 Rerank 截断
    answer, docs = await rag_chain.async_query(
        request.query, 
        top_k=request.top_k
    )

    # 3. 构造响应
    sources_list = []
    for doc in docs:
        metadata = doc.metadata
        sources_list.append(Source(
            source_filename=metadata.get("source", "未知文件"),
            page_number=metadata.get("page"),
            chunk_content=doc.page_content,
            chunk_id=str(metadata.get("doc_id"))
            # 如果需要，可以在 Source schema 中扩展 score 字段
        ))

    return QueryResponse(
        answer=answer,
        sources=sources_list
    )


@router.post("/stream")
async def stream_query(
    request: QueryRequest,
    pipeline_factory = Depends(deps.get_rag_pipeline_factory),
):
    # 1. 创建 Pipeline
    rag_chain = await pipeline_factory(
        knowledge_id=request.knowledge_id,
        llm_model=request.llm_model,
        rerank_model_name=request.rerank_model_name
    )
    
    # 2. 流式生成
    async def event_generator():
        # 同样传入 top_k 用于 Rerank
        async for chunk in rag_chain.astream_with_sources(
            request.query, 
            top_k=request.top_k
        ):
            if isinstance(chunk, list):
                # 这是 Sources 列表 (Rerank 后的结果)
                sources_data = []
                for doc in chunk:
                    metadata = doc.metadata
                    src = Source(
                        source_filename=metadata.get("source", "未知文件"),
                        page_number=metadata.get("page"),
                        chunk_content=doc.page_content,
                        chunk_id=str(metadata.get("doc_id"))
                    )
                    # 将 Pydantic 对象转为 dict 并在需要时注入分数 (Optional)
                    src_dict = src.model_dump(mode='json')
                    if "rerank_score" in metadata:
                        src_dict["score"] = metadata["rerank_score"]
                        
                    sources_data.append(src_dict)
                    
                yield f"event: sources\ndata: {json.dumps(sources_data, ensure_ascii=False)}\n\n"
            
            elif isinstance(chunk, str):
                # 这是 LLM 生成的 Token
                yield f"event: message\ndata: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")