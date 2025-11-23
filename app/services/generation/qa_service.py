# app/services/generation/qa_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse # 🟢 仅导入主入口即可

logger = logging.getLogger(__name__)

class QAService:
    """
    负责 Prompt 构建与 LLM 输出解析。
    集成 Langfuse Prompt Management 实现云端 Prompt 版本管理。
    """

    def __init__(self, llm: Any, prompt_name: str = "rag-default"):
        """
        初始化 QA 服务。
        
        :param llm: LangChain LLM 对象
        :param prompt_name: Langfuse 中的 Prompt 名称 (默认: "rag-default")
        """
        self.llm = llm
        self.langfuse = Langfuse()
        self.langfuse_prompt_obj = None # 🟢 保存 Prompt 对象备用
        
        try:
            # 1. 从 Langfuse 云端获取 Prompt
            logger.info(f"正在从 Langfuse 加载 Prompt: {prompt_name}...")
            self.langfuse_prompt_obj = self.langfuse.get_prompt(prompt_name)
            
            # 2. 转换为 LangChain 格式
            self.template = self.langfuse_prompt_obj.get_langchain_prompt()
            logger.info(f"Prompt 加载成功 (Version: {self.langfuse_prompt_obj.version})")
            
        except Exception as e:
            logger.error(f"❌ Langfuse Prompt 加载失败，回退到本地默认 Prompt: {e}", exc_info=True)
            # Fallback (兜底逻辑)
            self.template = """
            你是一个智能助手。请基于以下上下文回答用户问题。
            如果无法回答，请直接说明。
            
            上下文:
            {context}
            
            问题:
            {question}
            """.strip()

        self.prompt = ChatPromptTemplate.from_template(self.template)
        self.output_parser = StrOutputParser()
        
        # 构建 Chain
        self.chain = self.prompt | self.llm | self.output_parser
        
        logger.debug("QAService 链构建完成。")

    def format_inputs(self, question: str, context: str) -> Dict[str, str]:
        return {"question": question, "context": context}

    def invoke(self, question: str, context: str, config: Optional[RunnableConfig] = None) -> str:
        """同步调用"""
        # 复用异步的配置逻辑（如果有需要，也可以单独写）
        config = self._inject_prompt_metadata(config)
        payload = self.format_inputs(question, context)
        return self.chain.invoke(payload, config=config)

    async def ainvoke(self, question: str, context: str, config: Optional[RunnableConfig] = None) -> str:
        """
        异步调用 (支持传入 config 以启用 Tracing)
        """
        # 🟢 [修改点] 注入 Prompt Metadata
        # Langfuse CallbackHandler 会自动读取这个 metadata 并进行关联
        config = self._inject_prompt_metadata(config)

        payload = self.format_inputs(question, context)
        return await self.chain.ainvoke(payload, config=config)

    def _inject_prompt_metadata(self, config: Optional[RunnableConfig]) -> RunnableConfig:
        """
        辅助方法：将 Langfuse Prompt 对象注入到 metadata 中
        """
        # 确保 config 是一个字典
        new_config = config.copy() if config else {}
        
        if self.langfuse_prompt_obj:
            # 确保 metadata 存在
            if "metadata" not in new_config:
                new_config["metadata"] = {}
            
            # 🟢 关键：将 Prompt 对象放入 metadata，Key 必须是 'langfuse_prompt'
            new_config["metadata"]["langfuse_prompt"] = self.langfuse_prompt_obj
            
        return new_config