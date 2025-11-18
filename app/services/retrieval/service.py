from __future__ import annotations

import logging
from typing import List, Sequence

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    对底层 Retriever 进行封装，使用统一的 Runnable 接口 (LCEL)。
    """

    def __init__(self, retriever: BaseRetriever):
        self.retriever = retriever

    def fetch(self, query: str) -> List[Document]:
        """
        同步检索
        """
        logger.debug("RetrievalService.fetch -> %s", query)
        return self.retriever.invoke(query)

    async def afetch(self, query: str) -> List[Document]:
        """
        异步检索
        BaseRetriever 继承自 Runnable，原生支持 .ainvoke()
        """
        logger.debug("RetrievalService.afetch -> %s", query)
        return await self.retriever.ainvoke(query)

    def batch_fetch(self, queries: Sequence[str]) -> List[List[Document]]:
        """
        批量检索
        Runnable 接口原生支持 .batch()，会自动并行处理或使用线程池
        """
        logger.debug("RetrievalService.batch_fetch -> %s 条", len(queries))
        return self.retriever.batch(list(queries))