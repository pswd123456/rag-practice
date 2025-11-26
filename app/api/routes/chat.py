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
    # 🟢 修复：pipeline_factory 现在是一个异步函数，必须 await
    rag_chain = await pipeline_factory(
        knowledge_id=request.knowledge_id,
        strategy=request.strategy,
        top_k=settings.TOP_K,
        llm_model=request.llm_model
    )

    answer, docs = await rag_chain.async_query(request.query)

    sources_list = []
    for doc in docs:
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
    pipeline_factory = Depends(deps.get_rag_pipeline_factory),
):
    # 🟢 修复：pipeline_factory 必须 await
    rag_chain = await pipeline_factory(
        knowledge_id=request.knowledge_id,
        strategy=request.strategy,
        top_k=settings.TOP_K,
        llm_model=request.llm_model
    )
    
    async def event_generator():
        async for chunk in rag_chain.astream_with_sources(request.query):
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
                    sources_data.append(src.model_dump(mode='json'))
                yield f"event: sources\ndata: {json.dumps(sources_data, ensure_ascii=False)}\n\n"
            
            elif isinstance(chunk, str):
                yield f"event: message\ndata: {json.dumps(chunk)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")