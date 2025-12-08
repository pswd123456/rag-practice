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
            rerank_service=rerank_service, # 传递给 RetrievalFactory (如果需要)
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
        [Smart Truncation] 智能截断策略
        基于 Rerank 分数动态决定是否保留超长文档。
        """
        MAX_TOTAL_TOKENS = settings.MAX_TOTAL_TOKENS
        HIGH_QUALITY_THRESHOLD = 0.75 # Rerank 分数阈值
        
        current_tokens = 0
        valid_docs = []
        
        logger.debug(f"Formatting {len(docs)} documents with Smart Truncation...")

        for doc in docs:
            # 简单估算 token 数 (char / 1.5 approx for Chinese/English mix)
            # 或者 len(doc.page_content)
            doc_len = len(doc.page_content) 
            score = doc.metadata.get("rerank_score", 0)
            
            # 预判加入该文档后是否超限
            if current_tokens + doc_len > MAX_TOTAL_TOKENS:
                # [智能策略] 如果这篇文档相关性极高，尝试保留（即使稍微超限），否则截断退出
                # 只有在还没填满 80% 的情况下才允许稍微溢出，避免无限膨胀
                if score > HIGH_QUALITY_THRESHOLD and current_tokens < MAX_TOTAL_TOKENS * 0.8:
                    logger.info(f"保留高分长文档 (Score: {score:.3f}, Len: {doc_len})，尽管即将超限。")
                    valid_docs.append(doc.page_content)
                    break # 强行塞入这一篇后停止
                else:
                    logger.warning(f"达到 Token 上限 ({current_tokens}) 且文档分数 ({score:.3f}) 未达豁免阈值，截断后续内容。")
                    break
            
            valid_docs.append(doc.page_content)
            current_tokens += doc_len
            
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

        # 1. Recall (检索 50 条 Children -> Collapse to Parents)
        # Retriever (ESHybridRetriever) 内部现在会做 Collapse
        recall_docs = await self.retrieval_service.afetch(
            search_query, 
            config=callbacks
        )
        
        # 2. Rerank (对 Parents 进行精排)
        # Retriever 返回的现在是 Parents (大块内容)
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

        # 1. Recall (Children -> Parents)
        recall_docs = await self.retrieval_service.afetch(
            search_query, 
            config=callbacks
        )

        # 2. Rerank (Parents)
        reranked_docs = await self.rerank_service.rerank_documents(
            query=search_query, 
            docs=recall_docs,
            top_n=top_k,
            threshold=threshold
        )
        
        # Yield 精排后的文档
        yield reranked_docs
        
        # 3. Generate (Smart Truncation is applied inside _format_docs called below)
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