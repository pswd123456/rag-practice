from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """
你是一个问答助手。请根据下面提供的“上下文”来回答问题。
如果你在上下文中找不到答案，就说你不知道。

上下文:
{context}

问题:
{question}
""".strip()


class QAService:
    """
    负责 Prompt 构建与 LLM 输出解析。
    """

    def __init__(self, llm: Any, template: str = DEFAULT_PROMPT):
        self.llm = llm
        self.template = template
        self.prompt = ChatPromptTemplate.from_template(template)
        self.output_parser = StrOutputParser()
        self.chain = self.prompt | self.llm | self.output_parser
        logger.debug("QAService 初始化完成。")

    def format_inputs(self, question: str, context: str) -> Dict[str, str]:
        return {"question": question, "context": context}

    def invoke(self, question: str, context: str) -> str:
        payload = self.format_inputs(question, context)
        logger.debug("执行 QAService.invoke()，问题: %s", question)
        return self.chain.invoke(payload)

    async def ainvoke(self, question: str, context: str) -> str:
        payload = self.format_inputs(question, context)
        logger.debug("执行 QAService.ainvoke()，问题: %s", question)
        return await self.chain.ainvoke(payload)

