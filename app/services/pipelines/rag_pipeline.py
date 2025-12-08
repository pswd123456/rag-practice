"""
RAG 管道模块 (pipeline.py)

负责定义和创建 RAG (Retrieval-Augmented Generation) 链。
"""
import logging
from typing import AsyncGenerator, List, Optional, Union, Dict, Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.messages import BaseMessage
from langfuse.langchain import CallbackHandler 

from app.services.generation.qa_service import QAService
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.factories.llm_factory import setup_llm
from app.services.rerank.rerank_service import RerankService
from app.services.generation.rewrite_service import QueryRewriteService

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, 
                 retrieval_service: RetrievalService, 
                 qa_service: QAService,
                 rerank_service: RerankService,
                 rewrite_service: QueryRewriteService

    ):
        """
        初始化 RAG 管道，将检索与生成职责解耦。
        """
        logger.debug("初始化 RAGPipeline...")
        self.retrieval_service = retrieval_service
        self.qa_service = qa_service
        self.rerank_service = rerank_service
        self.langfuse_handler = CallbackHandler()
        self.generation_chain = self.qa_service.chain
        self.rewrite_service = rewrite_service
        
        self.rag_chain = (
            {
                "context": RunnableLambda(self.retrieval_service.afetch) | self._format_docs,
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

        rewrite_service = QueryRewriteService(llm=setup_llm("qwen-flash"))

        return cls(
            RetrievalService(retriever), 
            qa_service,
            rerank_service,
            rewrite_service
        )

    def _format_docs(self, docs: List[Document]) -> str:
        logger.debug("正在格式化 %s 个检索到的文档...", len(docs))
        formatted = "\n\n".join(doc.page_content for doc in docs)
        logger.debug("格式化后的上下文长度: %s 字符", len(formatted))

        return "\n\n".join(doc.page_content for doc in docs)

    # def _prepare_answer(self, inputs: Dict[str, Any], docs: List[Document]):
    #     """
    #     同步生成答案(Deprecated)
    #     :param inputs: 包含用户问题和其他变量的字典
    #     :param docs: 检索到的文档列表
    #     """
    #     # 1. 格式化上下文
    #     context = self._format_docs(docs)
        
    #     # 2. 注入上下文变量
    #     # 这里的 copy 是为了避免副作用修改传入的字典
    #     final_inputs = inputs.copy()
    #     final_inputs["context"] = context
        
    #     # 3. 调用 GenerationNode
    #     answer = self.qa_service.invoke(final_inputs)
    #     return answer, docs

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

    # def query(self, question: str, **kwargs):
    #     """
    #     同步入口 (Deprecated)
    #     """
    #     logger.warning("Synchronous query called. Reranking is skipped (Async required).")
    #     docs = self.retrieval_service.fetch(question)
    #     inputs = {"question": question, **kwargs}
    #     context = self._format_docs(docs)
    #     inputs["context"] = context
    #     answer = self.qa_service.invoke(inputs)
    #     return answer, docs

    async def async_query(self, question: str, 
                          top_k: int = 3, 
                          threshold: float = None,
                          chat_history: List[BaseMessage] = None,
                          **kwargs):
        """
        异步入口 (Standard: Recall -> Rerank -> Generate)
        :param top_k: 最终保留给 LLM 的切片数量 (Precision K)
        """
        callbacks = {"callbacks": [self.langfuse_handler]}

        search_query = await self.rewrite_service.rewrite(
            question, chat_history or [], config=callbacks
        )

        # 1. Recall (检索 50 条)
        # Retriever 已经在 build 时配置了 RECALL_TOP_K
        recall_docs = await self.retrieval_service.afetch(
            search_query, 
            config=callbacks
        )
        
        # 2. Rerank (精排取 top_k)
        reranked_docs = await self.rerank_service.rerank_documents(
            query=search_query,
            docs=recall_docs,
            top_n=top_k,
            threshold=threshold 
        )
        
        # 3. Generate
        inputs = {
            "question": question, 
            "chat_history": chat_history, # 确保 Prompt 模板支持 history
            **kwargs
        }

        return await self._prepare_answer_async(inputs, reranked_docs)

    async def astream_with_sources(self, 
                                   query: str, 
                                   top_k: int = 3,
                                   threshold: float = None, 
                                   chat_history: List[BaseMessage] = None,
                                   **kwargs) -> AsyncGenerator[Union[List[Document], str], None]:
        """
        流式生成 (支持 Rerank)
        """

        callbacks = {"callbacks": [self.langfuse_handler]}

        search_query = await self.rewrite_service.rewrite(
            query, chat_history or [], config=callbacks
        )

        # 1. Recall
        recall_docs = await self.retrieval_service.afetch(
            search_query, 
            config=callbacks
        )

        # 2. Rerank
        reranked_docs = await self.rerank_service.rerank_documents(
            query=search_query, 
            docs=recall_docs,
            top_n=top_k,
            threshold=threshold
        )
        
        # Yield 精排后的文档
        yield reranked_docs
        
        # 3. Generate
        context = self._format_docs(reranked_docs)
        inputs = {
            "question": query, 
            "context": context, 
            "chat_history": chat_history, 
            **kwargs
        }
        
        async for chunk in self.generation_chain.astream(
        inputs,
        config={"callbacks": [self.langfuse_handler]}
        ):
            # 1. 提取文本内容并 Yield 给前端
            if chunk.content:
                yield chunk.content
        
            # 2. 捕获 Usage 元数据 (通常在最后一个 chunk)
            if chunk.usage_metadata:
                # 以特殊字典形式 Yield 出去，供 Route 层捕获
                yield {"token_usage_payload": chunk.usage_metadata}
    def get_retrieval_service(self) -> RetrievalService:
        return self.retrieval_service

    def get_generation_chain(self):
        return self.generation_chain