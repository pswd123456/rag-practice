# -*- coding: utf-8 -*-
"""
RAG 管道模块 (pipeline.py)

负责定义和创建 RAG (Retrieval-Augmented Generation) 链。
"""
import logging
from typing import AsyncGenerator, List, Optional, Union

from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langfuse.langchain import CallbackHandler # 🟢 引入 Handler

from app.services.generation.qa_service import QAService
from app.services.retrieval.service import RetrievalService
from app.services.retrieval.vector_store_manager import VectorStoreManager

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, retrieval_service: RetrievalService, qa_service: QAService):
        """
        初始化 RAG 管道，将检索与生成职责解耦。
        """
        logger.debug("初始化 RAGPipeline...")
        self.retrieval_service = retrieval_service
        self.qa_service = qa_service
        
        # 🟢 1. 初始化 Langfuse Callback
        # 它会自动从环境变量读取 LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
        self.langfuse_handler = CallbackHandler()

        # 构建 LCEL 链 (保持原逻辑用于备用或 sync query)
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

    @classmethod
    def build(
        cls,
        store_manager:VectorStoreManager,
        qa_service: QAService,
        knowledge_id: Optional[int] = None,
        top_k: int = 3,
        strategy: str = "default"
    ) -> "RAGPipeline":
        """
        工厂方法：根据参数动态组装 RAGPipeline
        """
        search_kwargs = {"k": top_k}
        if knowledge_id:
            search_kwargs["filter"] = {"knowledge_id": knowledge_id}#type:ignore

        if strategy == "dense_only":
            retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)
                    
        elif strategy == "hybrid":
            # TODO: 实现混合检索逻辑
            # retriever = ...
            retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)
            
        elif strategy == "rerank":
            # TODO: 实现重排序逻辑
            # retriever = ...
            retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)
            
        else:
            # default
            retriever = store_manager.vector_store.as_retriever(search_kwargs=search_kwargs)

        return cls(RetrievalService(retriever), qa_service)

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
        """异步生成答案，注入 Tracing"""
        context = self._format_docs(docs)
        
        # 🟢 2. 注入 Callback 到生成环节
        # 这会自动记录 Generation Span (包括 Prompt、Completion、Token Usage)
        answer = await self.qa_service.ainvoke(
            question, 
            context, 
            config={"callbacks": [self.langfuse_handler]}
        )
        return answer, docs

    def query(self, question: str):
        docs = self.retrieval_service.fetch(question)
        return self._prepare_answer(question, docs)

    async def async_query(self, question: str):
        """执行完整 RAG 流程 (检索 + 生成)"""
        # 🟢 3. 注入 Callback 到检索环节
        # 这会自动记录 Retrieval Span (包括查询词、召回文档内容)
        docs = await self.retrieval_service.afetch(
            question, 
            config={"callbacks": [self.langfuse_handler]}
        )
        
        return await self._prepare_answer_async(question, docs)
    
    async def astream_answer(self, query: str):
        async for chunk in self.rag_chain.astream(query):
            yield chunk

    async def astream_with_sources(self, query: str) -> AsyncGenerator[Union[List[Document], str], None]:
        """
        流式生成：先 Yield 检索到的文档列表，再 Yield 生成的 Token。
        """
        # 🟢 4. 检索 Tracing
        docs = await self.retrieval_service.afetch(
            query,
            config={"callbacks": [self.langfuse_handler]}
        )
        yield docs
        
        context = self._format_docs(docs)
        payload = {"question": query, "context": context}
        
        # 🟢 5. 生成 Tracing (流式)
        # Langfuse 会自动聚合流式块，在 Trace 中显示完整回复
        async for token in self.generation_chain.astream(
            payload,
            config={"callbacks": [self.langfuse_handler]}
        ):
            yield token
    def get_retrieval_service(self) -> RetrievalService:
        return self.retrieval_service

    def get_generation_chain(self):
        return self.generation_chain