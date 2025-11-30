# -*- coding: utf-8 -*-
"""
RAG 管道模块 (pipeline.py)

负责定义和创建 RAG (Retrieval-Augmented Generation) 链。
"""
import logging
from typing import AsyncGenerator, List, Optional, Union, Dict, Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langfuse.langchain import CallbackHandler # 🟢 引入 Handler

from app.services.generation.qa_service import QAService
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.rerank.rerank_service import RerankService

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, 
                 retrieval_service: RetrievalService, 
                 qa_service: QAService,
                 rerank_service: RerankService

    ):
        """
        初始化 RAG 管道，将检索与生成职责解耦。
        """
        logger.debug("初始化 RAGPipeline...")
        self.retrieval_service = retrieval_service
        self.qa_service = qa_service
        self.rerank_service = rerank_service
        self.langfuse_handler = CallbackHandler()

        # [Pipeline 职责]: 编排 Retrieval 和 Generation
        # qa_service.chain 期望接收 Dict
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
        store_manager: VectorStoreManager,
        qa_service: QAService,
        rerank_service: RerankService, 
        knowledge_id: Optional[int] = None,
        recall_top_k: int = 50, 
        strategy: str = "hybrid", 
        **kwargs
    ) -> "RAGPipeline":
        """
        工厂方法：组装 RAGPipeline
        """
        
        retriever = RetrievalFactory.create_retriever(
            store_manager=store_manager,
            strategy=strategy,
            top_k=recall_top_k, 
            knowledge_id=knowledge_id,
            **kwargs
        )

        return cls(
            RetrievalService(retriever), 
            qa_service,
            rerank_service
        )

    def _format_docs(self, docs: List[Document]) -> str:
        logger.debug("正在格式化 %s 个检索到的文档...", len(docs))
        formatted = "\n\n".join(doc.page_content for doc in docs)
        logger.debug("格式化后的上下文长度: %s 字符", len(formatted))

        return "\n\n".join(doc.page_content for doc in docs)

    def _prepare_answer(self, inputs: Dict[str, Any], docs: List[Document]):
        """
        同步生成答案
        :param inputs: 包含用户问题和其他变量的字典
        :param docs: 检索到的文档列表
        """
        # 1. 格式化上下文
        context = self._format_docs(docs)
        
        # 2. 注入上下文变量
        # 这里的 copy 是为了避免副作用修改传入的字典
        final_inputs = inputs.copy()
        final_inputs["context"] = context
        
        # 3. 调用 GenerationNode
        answer = self.qa_service.invoke(final_inputs)
        return answer, docs

    async def _prepare_answer_async(self, inputs: Dict[str, Any], docs: List[Document]):
        """
        异步生成答案
        """
        context = self._format_docs(docs)
        
        final_inputs = inputs.copy()
        final_inputs["context"] = context
        
        # 注入 Trace
        answer = await self.qa_service.ainvoke(
            final_inputs, 
            config={"callbacks": [self.langfuse_handler]}
        )
        return answer, docs

    # 同步 query 方法暂不支持 Rerank (因为 RerankService 是 async 的)
    # 如果必须同步调用，需使用 asyncio.run 或降级为仅 Retrieve
    def query(self, question: str, **kwargs):
        """
        同步入口 (Legacy: 暂不支持 Rerank，直接返回 Retrieve 结果)
        """
        logger.warning("Synchronous query called. Reranking is skipped (Async required).")
        docs = self.retrieval_service.fetch(question)
        inputs = {"question": question, **kwargs}
        # 使用 QAService 的同步 invoke
        context = self._format_docs(docs)
        inputs["context"] = context
        answer = self.qa_service.invoke(inputs)
        return answer, docs

    async def async_query(self, question: str, top_k: int = 3, **kwargs):
        """
        异步入口 (Standard: Recall -> Rerank -> Generate)
        :param top_k: 最终保留给 LLM 的切片数量 (Precision K)
        """
        # 1. Recall (检索 50 条)
        # Retriever 已经在 build 时配置了 RECALL_TOP_K
        recall_docs = await self.retrieval_service.afetch(
            question, 
            config={"callbacks": [self.langfuse_handler]}
        )
        
        # 2. Rerank (精排取 top_k)
        reranked_docs = await self.rerank_service.rerank_documents(
            query=question,
            docs=recall_docs,
            top_n=top_k
        )
        
        # 3. Generate
        inputs = {"question": question, **kwargs}
        return await self._prepare_answer_async(inputs, reranked_docs)

    async def astream_with_sources(self, query: str, top_k: int = 3, **kwargs) -> AsyncGenerator[Union[List[Document], str], None]:
        """
        流式生成 (支持 Rerank)
        """
        # 1. Recall
        recall_docs = await self.retrieval_service.afetch(
            query,
            config={"callbacks": [self.langfuse_handler]}
        )
        
        # 2. Rerank
        reranked_docs = await self.rerank_service.rerank_documents(
            query=query,
            docs=recall_docs,
            top_n=top_k
        )
        
        # Yield 精排后的文档
        yield reranked_docs
        
        # 3. Generate
        context = self._format_docs(reranked_docs)
        inputs = {"question": query, "context": context, **kwargs}
        
        async for token in self.generation_chain.astream(
            inputs,
            config={"callbacks": [self.langfuse_handler]}
        ):
            yield token
    def get_retrieval_service(self) -> RetrievalService:
        return self.retrieval_service

    def get_generation_chain(self):
        return self.generation_chain