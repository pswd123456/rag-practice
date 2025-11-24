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
from app.services.retrieval.service import RetrievalService
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.factories.retrieval_factory import RetrievalFactory

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, retrieval_service: RetrievalService, qa_service: QAService):
        """
        初始化 RAG 管道，将检索与生成职责解耦。
        """
        logger.debug("初始化 RAGPipeline...")
        self.retrieval_service = retrieval_service
        self.qa_service = qa_service
        self.langfuse_handler = CallbackHandler()

        # [Pipeline 职责]: 编排 Retrieval 和 Generation
        # qa_service.chain 现在期望接收 Dict
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
        knowledge_id: Optional[int] = None,
        top_k: int = 3,
        strategy: str = "default",
        **kwargs  #允许透传额外参数给 Factory (如 hybrid_alpha)
    ) -> "RAGPipeline":
        """
        工厂方法：组装 RAGPipeline
        """
        # 使用 RetrievalFactory 创建检索器，彻底解耦
        retriever = RetrievalFactory.create_retriever(
            store_manager=store_manager,
            strategy=strategy,
            top_k=top_k,
            knowledge_id=knowledge_id,
            **kwargs
        )

        return cls(RetrievalService(retriever), qa_service)

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

    def query(self, question: str, **kwargs):
        """
        同步入口
        :param question: 必选，用于检索
        :param kwargs: 可选，其他传递给 Prompt 的变量 (e.g. chat_history=[...])
        """
        # 1. 检索 (依然主要依赖 question)
        docs = self.retrieval_service.fetch(question)
        
        # 2. 组装输入
        inputs = {"question": question, **kwargs}
        
        return self._prepare_answer(inputs, docs)

    async def async_query(self, question: str, **kwargs):
        """
        异步入口
        """
        # 1. 检索
        docs = await self.retrieval_service.afetch(
            question, 
            config={"callbacks": [self.langfuse_handler]}
        )
        
        # 2. 组装输入
        inputs = {"question": question, **kwargs}
        
        return await self._prepare_answer_async(inputs, docs)

    async def astream_with_sources(self, query: str, **kwargs) -> AsyncGenerator[Union[List[Document], str], None]:
        """
        流式生成：先 Yield 文档，再 Yield Token
        """
        # 1. 检索
        docs = await self.retrieval_service.afetch(
            query,
            config={"callbacks": [self.langfuse_handler]}
        )
        yield docs
        
        # 2. 组装输入 (支持 kwargs)
        context = self._format_docs(docs)
        inputs = {"question": query, "context": context, **kwargs}
        
        # 3. 生成
        async for token in self.generation_chain.astream(
            inputs,
            config={"callbacks": [self.langfuse_handler]}
        ):
            yield token
    def get_retrieval_service(self) -> RetrievalService:
        return self.retrieval_service

    def get_generation_chain(self):
        return self.generation_chain