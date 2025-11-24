# app/services/generation/qa_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse

logger = logging.getLogger(__name__)

class QAService:
    """
    [Generation Node]
    职责：管理 Prompt Template 和 LLM，提供纯粹的生成能力。
    输入：Dict (由 Pipeline 负责组装)
    输出：String
    """

    def __init__(self, llm: Any, prompt_name: str = "rag-default"):
        self.llm = llm
        self.langfuse = Langfuse()
        self.langfuse_prompt_obj = None
        
        try:
            # 1. 从 Langfuse 云端获取 Prompt
            logger.info(f"正在从 Langfuse 加载 Prompt: {prompt_name}...")
            self.langfuse_prompt_obj = self.langfuse.get_prompt(prompt_name)
            self.template = self.langfuse_prompt_obj.get_langchain_prompt()
            logger.info(f"Prompt 加载成功 (Version: {self.langfuse_prompt_obj.version})")
            
        except Exception as e:
            logger.error(f"❌ Langfuse Prompt 加载失败，回退到本地默认 Prompt: {e}", exc_info=True)
            # Fallback
            self.template = """
            你是一个智能助手。请基于以下上下文回答用户问题。
            
            上下文:
            {context}
            
            问题:
            {question}
            """.strip()

        # 确保 template 是 LangChain 的 PromptTemplate 对象
        if isinstance(self.template, str):
            self.prompt = ChatPromptTemplate.from_template(self.template)
        else:
            self.prompt = self.template

        self.output_parser = StrOutputParser()
        
        # 构建 Chain: Dict -> Prompt -> LLM -> String
        self.chain = self.prompt | self.llm | self.output_parser
        
        logger.debug("QAService (GenerationNode) 构建完成。")

    def invoke(self, input_dict: Dict[str, Any], config: Optional[RunnableConfig] = None) -> str:
        """
        同步调用生成
        :param input_dict: 包含 Prompt 所需变量的字典 (e.g. {"question": "...", "context": "..."})
        """
        config = self._inject_prompt_metadata(config)
        return self.chain.invoke(input_dict, config=config)

    async def ainvoke(self, input_dict: Dict[str, Any], config: Optional[RunnableConfig] = None) -> str:
        """
        异步调用生成
        """
        config = self._inject_prompt_metadata(config)
        return await self.chain.ainvoke(input_dict, config=config)

    def _inject_prompt_metadata(self, config: Optional[RunnableConfig]) -> RunnableConfig:
        """
        注入 Langfuse Prompt Metadata 用于 Trace 关联
        """
        new_config = config.copy() if config else {}
        
        if self.langfuse_prompt_obj:
            if "metadata" not in new_config:
                new_config["metadata"] = {}
            new_config["metadata"]["langfuse_prompt"] = self.langfuse_prompt_obj
            
        return new_config