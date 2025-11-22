from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

# 🟢 引入新建立的 Prompt 注册表
from app.core.prompts import PROMPT_REGISTRY, PromptStyle, DEFAULT_RAG_PROMPT

logger = logging.getLogger(__name__)

class QAService:
    """
    负责 Prompt 构建与 LLM 输出解析。
    支持动态切换 Prompt 模板。
    """

    def __init__(self, llm: Any, prompt_template: Optional[str] = None, prompt_name: str = "default"):
        """
        初始化 QA 服务。
        
        :param llm: LangChain LLM 对象
        :param prompt_template: 自定义 Prompt 字符串 (优先级最高)
        :param prompt_name: 从注册表中选择的 Prompt 名称 (default, strict, chain_of_thought)
        """
        self.llm = llm
        
        # 🟢 逻辑优化：优先使用传入的 template，否则从注册表查，再兜底使用默认
        if prompt_template:
            self.template = prompt_template
            logger.info("QAService 使用自定义 Prompt Template 初始化")
        else:
            # 尝试从注册表获取，如果 key 不存在则回退到 DEFAULT
            self.template = PROMPT_REGISTRY.get(prompt_name, DEFAULT_RAG_PROMPT)
            logger.info(f"QAService 使用预设 Prompt 初始化: {prompt_name}")

        self.prompt = ChatPromptTemplate.from_template(self.template)
        self.output_parser = StrOutputParser()
        self.chain = self.prompt | self.llm | self.output_parser
        
        logger.debug("QAService 链构建完成。")

    def format_inputs(self, question: str, context: str) -> Dict[str, str]:
        return {"question": question, "context": context}

    def invoke(self, question: str, context: str) -> str:
        payload = self.format_inputs(question, context)
        # logger.debug("执行 QAService.invoke()，问题: %s", question)
        return self.chain.invoke(payload)

    async def ainvoke(self, question: str, context: str) -> str:
        payload = self.format_inputs(question, context)
        # logger.debug("执行 QAService.ainvoke()，问题: %s", question)
        return await self.chain.ainvoke(payload)