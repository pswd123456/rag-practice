# -*- coding: utf-8 -*-
"""
RAG 评估器 (runner.py)
"""
import logging
from typing import Dict, Optional

from langfuse.langchain import CallbackHandler

# Ragas & Datasets
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)
from ragas.dataset_schema import SingleTurnSample

# App Modules
from app.core.config import settings
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.generation import QAService
from app.services.ingest import build_or_get_vector_store
from app.services.pipelines import RAGPipeline
from app.services.retrieval import RetrievalService
from app.services.evaluation.config import EvaluationConfig, get_default_config

# 移除模块级别的 logging 配置代码
# 只获取 logger 实例
logger = logging.getLogger("evaluation.runner")


class RAGEvaluator:
    """
    封装了 RAG 评估所需的所有逻辑
    """
    def __init__(
        self,
        rag_pipeline: RAGPipeline,
        llm,
        embed_model,
        config: Optional[EvaluationConfig] = None,
    ):
        self.pipeline = rag_pipeline
        self.config = config or get_default_config()
        self.langfuse_handler = CallbackHandler()

        logger.debug("正在初始化 Ragas LLM 和 Embeddings 包装器...")

        ragas_llm = LangchainLLMWrapper(llm)
        ragas_llm.langchain_llm.callbacks = [self.langfuse_handler]

        ragas_embed = LangchainEmbeddingsWrapper(embed_model)
        self.metrics = self._build_metrics(ragas_llm, ragas_embed)
        self.test_dataset = None
        self.scores_df = None

    async def adapt_metrics(self, language: str = "chinese"):
        """
        利用 LLM 自动将评估指标的 Prompt 适配到指定语言。
        """
        logger.info(f"正在将 Ragas 评估指标 Prompt 适配为: {language}...")
        
        adapted_count = 0
        for metric in self.metrics:
            try:

                if metric.name == "answer_relevancy":
                    logger.info(f"指标 [{metric.name}] 已跳过中文适配")
                    continue

                # 检查指标是否支持 Prompt 适配 (BaseMetric 通常都支持)
                if hasattr(metric, "adapt_prompts") and hasattr(metric, "set_prompts"):
                    # 使用指标自带的 LLM (即我们在 __init__ 传入的 ragas_llm)
                    # 注意：adapt_prompts 是异步方法
                    adapted_prompts = await metric.adapt_prompts(language=language, llm=metric.llm)
                    
                    # 将适配后的 Prompts 应用回指标实例
                    metric.set_prompts(**adapted_prompts)
                    adapted_count += 1
                    logger.debug(f"指标 [{metric.name}] 语言适配成功")
                else:
                    logger.warning(f"指标 [{metric.name}] 不支持 adapt_prompts，已跳过")
            
            except Exception as e:
                logger.warning(f"指标 [{metric.name}] 语言适配失败: {e}，将保持默认(英语) Prompt")

        logger.info(f"语言适配完成: {adapted_count}/{len(self.metrics)} 个指标已更新为 {language} 环境。")
    def _build_metrics(self, ragas_llm, ragas_embed):
        metric_builders = {
            "faithfulness": lambda: Faithfulness(llm=ragas_llm),
            "answer_relevancy": lambda: AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embed),
            "context_recall": lambda: ContextRecall(llm=ragas_llm),
            "context_precision": lambda: ContextPrecision(llm=ragas_llm),
        }

        metrics = []
        for name in self.config.metrics:
            builder = metric_builders.get(name)
            if builder:
                metrics.append(builder())
            else:
                logger.warning("未知指标 %s，已跳过。", name)
        return metrics
    
    def _integrate_testset(self, batch):
        questions  = batch["question"]
        
        # 批量检索
        retrieval_service = self.pipeline.get_retrieval_service()
        contexts_docs = retrieval_service.batch_fetch(questions)
        
        contexts_str_lists = [
            [doc.page_content for doc in doc_list] 
            for doc_list in contexts_docs
        ]

        # 批量生成
        generation_chain = self.pipeline.get_generation_chain()
        inputs_for_chain = []
        for q, c_list in zip(questions, contexts_str_lists):
            formatted_context = "\n\n".join(c_list)
            inputs_for_chain.append({"question": q, "context": formatted_context})

        answer_list = generation_chain.batch(inputs_for_chain)

        return {
            "answer": answer_list,
            "contexts": contexts_str_lists
        }
    
    async def score_single_item(self, question: str, answer: str, contexts: list[str], ground_truth: str) -> Dict[str, float]:
        """
        计算单条数据的 Ragas 分数，用于 Langfuse Experiment Loop
        """
        sample = SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth
        )
        
        scores = {}
        for metric in self.metrics:
            try:
                # 针对单个样本进行评分
                val = await metric.single_turn_ascore(sample)
                scores[metric.name] = val
            except Exception as e:
                logger.error(f"Metric {metric.name} calculation failed: {e}")
                scores[metric.name] = 0.0
        
        return scores
    
def prepare_pipeline(force_rebuild: bool = False):
    collection_name = settings.CHROMADB_COLLECTION_NAME
    embeddings = setup_embed_model("text-embedding-v4")
    vector_store = build_or_get_vector_store(collection_name, embeddings, force_rebuild=force_rebuild)
    llm = setup_qwen_llm("qwen-flash")

    retriever = vector_store.as_retriever()
    rag_pipeline = RAGPipeline(
        retrieval_service=RetrievalService(retriever),
        qa_service=QAService(llm),
    )
    return rag_pipeline, llm, embeddings
