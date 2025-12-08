# app/services/generation/rewrite_service.py
import logging
from typing import List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse

logger = logging.getLogger(__name__)

class QueryRewriteService:
    """
    [Query Rewrite Node]
    职责：基于对话历史，将用户的 Follow-up Query 重写为 Standalone Query。
    """

    def __init__(self, llm, prompt_name: str = "rag-query-rewrite"):
        self.llm = llm
        self.langfuse = Langfuse()
        self.langfuse_prompt_obj = None
        
        
        try:
            logger.info(f"正在从 Langfuse 加载 Rewrite Prompt: {prompt_name}...")
            # fetch prompt from Langfuse
            self.langfuse_prompt_obj = self.langfuse.get_prompt(prompt_name)
            # convert to langchain prompt template
            self.prompt = self.langfuse_prompt_obj.get_langchain_prompt()
            logger.info(f"Rewrite Prompt 加载成功 (Version: {self.langfuse_prompt_obj.version})")
            
        except Exception as e:
            logger.warning(f"⚠️ Langfuse Prompt 加载失败 ({e})，回退到本地默认 Prompt。")
            self.prompt = self._get_default_prompt()

        if isinstance(self.prompt, str):
            self.prompt = ChatPromptTemplate.from_template(self.prompt)
        elif isinstance(self.prompt, list):
            self.prompt = ChatPromptTemplate.from_messages(self.prompt)
        else:
            self.prompt = self.prompt
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    def _get_default_prompt(self) -> ChatPromptTemplate:
        """
        本地默认的 Few-Shot Prompt (Fallback)
        """
        system_prompt = """
        You are a helpful assistant that rewrites a user's question based on the chat history to make it a standalone question.
        The rewritten question must explicitly include the subject (e.g., "Qwen", "Docker") referenced in the history.
        
        RULES:
        1. Do NOT answer the question.
        2. Do NOT add extra information not present in the history or question.
        3. Keep the rewritten question concise.
        4. If the user's question is already standalone, return it as is.
        5. If the user's question is essentially "Hello" or "Thanks", return it as is.

        EXAMPLES:
        
        Chat History:
        Human: How to install Docker?
        AI: You can install it via apt-get...
        User Input: "What about composed?"
        Rewritten: "How to install Docker Compose?"
        
        ---
        
        Chat History:
        Human: Introduce Qwen model.
        AI: Qwen is a LLM developed by Alibaba...
        User Input: "Is it open source?"
        Rewritten: "Is the Qwen model open source?"
        """
        
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ])
    

    async def rewrite(
        self, 
        query: str, 
        chat_history: List[BaseMessage], 
        config: Optional[RunnableConfig] = None
    ) -> str:
        """
        执行重写
        """
        # if not chat_history:
        #     logger.debug("无对话历史，跳过重写。")
        #     return query

        try:
            logger.debug(f"正在重写 Query: {query} (History Len: {len(chat_history)})")
            
            rewritten_query = await self.chain.ainvoke(
                {
                    "chat_history": chat_history,
                    "question": query
                },
                config=config
            )
            
            rewritten_query = rewritten_query.strip()
            logger.info(f"🔄 Query Rewrite: '{query}' -> '{rewritten_query}'")
            return rewritten_query

        except Exception as e:
            logger.error(f"❌ Query Rewrite 失败: {e}，回退到原始 Query", exc_info=True)
            return query