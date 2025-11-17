# -*- coding: utf-8 -*-
"""
RAG 管道模块 (pipeline.py)

负责定义和创建 RAG (Retrieval-Augmented Generation) 链。
"""
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from typing import List

# 获取 'core.pipeline' 模块的 logger
logger = logging.getLogger(__name__)
class RAGPipeline:
    def __init__(self, llm, retriever):
        """
        初始化 RAG 管道。
        
        :param vector_store: 已经加载的 Chroma 向量数据库实例。
        :param search_k: 检索器在搜索时返回的文档数量 (k)。
        """
        logger.debug("初始化 RAGPipeline...")
        
        # --- 1. 定义所有组件 ---

        logger.debug("设置 LLM...")
        self.llm = llm
        
        logger.debug("设置 Retriever...")
        self.retriever = retriever
        
        # 定义 RAG 提示词模板
        template = """
        你是一个问答助手。请根据下面提供的“上下文”来回答问题。
        如果你在上下文中找不到答案，就说你不知道。

        上下文:
        {context}

        问题:
        {question}
        """
        self.prompt = ChatPromptTemplate.from_template(template)

        # --- 2. 组装 RAG 链 (LCEL) ---
        # 此时 self.retriever, self.prompt, 和 self.llm 都已定义
        
        logger.debug("组装 RAG 链...")
        # 流程解释:
        # 1. (并行执行) {"context": ..., "question": ...}
        #    - "context": 
        #       a. 输入 (query) 被传递给 self.retriever
        #       b. retriever 返回的 'docs' 列表被传递给 _format_docs 函数进行格式化
        #    - "question": 
        #       a. 输入 (query) 被 RunnablePassthrough() 按原样传递
        # 2. 上一步的字典 {context: ..., question: ...} 被传递给 self.prompt
        # 3. prompt 的输出 (格式化后的提示) 被传递给 self.llm
        # 4. llm 的输出 (ChatMessage) 被 StrOutputParser() 解析为纯字符串
        self.generation_chain = (
            self.prompt
            | self.llm
            | StrOutputParser()
        )
        
        self.rag_chain = (
            {"context": self.retriever | self._format_docs, "question": RunnablePassthrough()}
            | self.generation_chain
        )
        
        logger.info("RAG 管道已成功创建。")

    def get_rag_chain(self):
        """获取已组装的 RAG 链。"""
        return self.rag_chain
    
    def get_retriever(self):
        """获取检索器实例。"""
        return self.retriever
    
    def async_query(self, query:str):
        return self.rag_chain.ainvoke(query)

    def get_llm(self):
        """获取 LLM 实例。"""
        return self.llm
    
    def get_generation_chain(self):
        """
        返回仅用于生成的链
        输入: {"context":str, "question":str}
        输出: str
        """
        return self.generation_chain

    def _format_docs(self, docs: List[Document]) -> str:
        """
        一个辅助函数，用于将检索到的 Document 列表格式化为单个字符串，
        用作 LLM 的上下文。
        
        :param docs: Document 对象列表
        :return: 拼接后的字符串
        """
        logger.debug(f"正在格式化 {len(docs)} 个检索到的文档...")
        formatted = "\n\n".join(doc.page_content for doc in docs)
        logger.debug(f"格式化后的上下文长度: {len(formatted)} 字符")
        return formatted