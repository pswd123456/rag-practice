# app/services/retrieval/service.py
from __future__ import annotations

import logging
from typing import List, Sequence, Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    对底层 Retriever 进行封装，使用统一的 Runnable 接口 (LCEL)。
    """

    def __init__(self, retriever: BaseRetriever):
        self.retriever = retriever

    def fetch(self, query: str, config: Optional[RunnableConfig] = None) -> List[Document]:
        """
        同步检索 (支持 Tracing)
        """
        logger.debug("RetrievalService.fetch -> %s", query)
        # 透传 config，确保 CallbackHandler 能捕获检索 Span
        return self.retriever.invoke(query, config=config)

    async def afetch(self, query: str, config: Optional[RunnableConfig] = None) -> List[Document]:
        """
        异步检索 (支持 Tracing)
        BaseRetriever 继承自 Runnable，原生支持 .ainvoke()
        """
        logger.debug("RetrievalService.afetch -> %s", query)
        return await self.retriever.ainvoke(query, config=config)

    def batch_fetch(self, queries: Sequence[str], config: Optional[RunnableConfig] = None) -> List[List[Document]]:
        """
        批量检索
        """
        logger.debug("RetrievalService.batch_fetch -> %s 条", len(queries))
        return self.retriever.batch(list(queries), config=config)