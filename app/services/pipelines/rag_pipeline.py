# -*- coding: utf-8 -*-
"""
RAG 管道模块 (pipeline.py)

负责定义和创建 RAG (Retrieval-Augmented Generation) 链。
"""
import logging
from typing import List

from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from app.services.generation.qa_service import QAService
from app.services.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, retrieval_service: RetrievalService, qa_service: QAService):
        """
        初始化 RAG 管道，将检索与生成职责解耦。
        """
        logger.debug("初始化 RAGPipeline...")
        self.retrieval_service = retrieval_service
        self.qa_service = qa_service

        # 构建 LCEL 链以兼容 LangChain 生态
        self.generation_chain = self.qa_service.chain
        
        retrieval_node = RunnableLambda(
            func = self.retrieval_service.fetch,
            afunc = self.retrieval_service.afetch
        )
        
        self.rag_chain = (
            {
                "context": retrieval_node | self._format_docs,
                "question": RunnablePassthrough(),
            }
            | self.generation_chain
        )

        logger.info("RAG 管道已成功创建。")

    def _format_docs(self, docs: List[Document]) -> str:
        logger.debug("正在格式化 %s 个检索到的文档...", len(docs))
        formatted = "\n\n".join(doc.page_content for doc in docs)
        logger.debug("格式化后的上下文长度: %s 字符", len(formatted))
        return formatted

    def _prepare_answer(self, question: str, docs: List[Document]):
        """同步生成答案，返回答案和文档"""
        context = self._format_docs(docs)
        answer = self.qa_service.invoke(question, context)
        return answer, docs

    async def _prepare_answer_async(self, question: str, docs: List[Document]):
        """异步生成答案，返回答案和文档"""
        context = self._format_docs(docs)
        answer = await self.qa_service.ainvoke(question, context)
        return answer, docs

    def query(self, question: str):
        docs = self.retrieval_service.fetch(question)
        return self._prepare_answer(question, docs)

    async def async_query(self, question: str):
        docs = await self.retrieval_service.afetch(question)
        return await self._prepare_answer_async(question, docs)
    
    async def astream_answer(self, query: str):
        async for chunk in self.rag_chain.astream(query):
            yield chunk

    # def get_rag_chain(self):
    #     return self.rag_chain

    def get_retrieval_service(self) -> RetrievalService:
        return self.retrieval_service

    def get_generation_chain(self):
        return self.generation_chain