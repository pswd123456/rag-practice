"""
RAG 管道模块 (pipeline.py)

负责定义和创建 RAG (Retrieval-Augmented Generation) 链。
"""
import logging
from typing import AsyncGenerator, List, Optional, Union, Dict, Any

import tiktoken
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.messages import BaseMessage
from langfuse.langchain import CallbackHandler 
from langfuse import observe 

from app.services.generation.qa_service import QAService
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.services.factories.retrieval_factory import RetrievalFactory
from app.services.factories.llm_factory import setup_llm
from app.services.rerank.rerank_service import RerankService
from app.services.generation.rewrite_service import QueryRewriteService

from app.core.config import settings

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
        
        # 初始化 Tokenizer
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
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
            rerank_service=rerank_service, 
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
        """
        [Smart Truncation v2] 智能截断策略 (Token Aware)
        """
    
        max_total_tokens = settings.MAX_TOTAL_TOKENS    
        HIGH_QUALITY_THRESHOLD = 0.75 # Rerank 分数阈值
        
        current_tokens = 0
        valid_docs = []
        
        logger.debug(f"Formatting {len(docs)} documents with Token-Aware Smart Truncation...")

        for doc in docs:
            # 1. 获取或计算 Token 数
            if "token_count" in doc.metadata:
                doc_tokens = doc.metadata["token_count"]
            else:
                doc_tokens = len(self.tokenizer.encode(doc.page_content))
            
            score = doc.metadata.get("rerank_score", 0)
            
            # 2. 预判是否超限
            if current_tokens + doc_tokens > max_total_tokens:
                if score > HIGH_QUALITY_THRESHOLD and current_tokens < max_total_tokens * 0.9:
                    logger.info(f"保留高分文档 (Score: {score:.3f}, Tokens: {doc_tokens})，尽管即将超限 (Current: {current_tokens})。")
                    valid_docs.append(doc.page_content)
                    break 
                else:
                    logger.warning(f"达到 Token 上限 ({current_tokens}/{max_total_tokens})，截断后续内容。")
                    break
            
            valid_docs.append(doc.page_content)
            current_tokens += doc_tokens
            
        logger.info(f"Context 组装完成: {len(valid_docs)} docs, ~{current_tokens} tokens.")
        return "\n\n".join(valid_docs)

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

    @observe(name="rag_pipeline_run", as_type="chain")
    async def async_query(self, question: str, 
                          top_k: int = 3, 
                          threshold: float = None,
                          chat_history: List[BaseMessage] = None,
                          **kwargs):
        """
        异步入口 (Standard: Recall -> Rerank -> Generate)
        """
        callbacks = {"callbacks": [self.langfuse_handler]}

        search_query = await self.rewrite_service.rewrite(
            question, chat_history or [], config=callbacks
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
        
        # 3. Generate
        inputs = {
            "question": question, 
            "chat_history": chat_history, 
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
            if chunk.content:
                yield chunk.content
        
            if chunk.usage_metadata:
                yield {"token_usage_payload": chunk.usage_metadata}
    
    def get_retrieval_service(self) -> RetrievalService:
        return self.retrieval_service

    def get_generation_chain(self):
        return self.generation_chain