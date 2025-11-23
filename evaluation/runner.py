# -*- coding: utf-8 -*-
"""
RAG 评估器 (runner.py)
"""
import os
import logging
import warnings
from typing import Dict, Optional
import typer

from langfuse.langchain import CallbackHandler

# Ragas & Datasets
from datasets import load_dataset, Dataset
from ragas import evaluate
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
from app.core.logging_setup import setup_logging
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.generation import QAService
from app.services.ingest import build_or_get_vector_store
from app.services.pipelines import RAGPipeline
from app.services.retrieval import RetrievalService
from evaluation.config import EvaluationConfig, get_default_config

warnings.filterwarnings("ignore", message=".*Torch was not compiled with flash attention.*")

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

    def load_and_process_testset(self):
        if self.test_dataset is None:
            logger.info(f"TestDataset 为空，尝试从默认路径加载: {settings.TESTSET_OUTPUT_PATH}")
            try:
                hf_dataset = load_dataset("csv", data_files=str(settings.TESTSET_OUTPUT_PATH))
                self.test_dataset = hf_dataset["train"] # type: ignore
                
                # 重命名
                rename_columns_dict = {"user_input": "question", "reference": "ground_truth"}
                if "user_input" in self.test_dataset.column_names:
                    self.test_dataset = self.test_dataset.rename_columns(rename_columns_dict)
                
                # 清洗
                cols_to_remove = ["reference_contexts", 'synthesizer_name']
                existing_cols = self.test_dataset.column_names
                self.test_dataset = self.test_dataset.remove_columns([c for c in cols_to_remove if c in existing_cols])
                
            except Exception as e:
                logger.error(f"默认路径加载失败: {e}")
                raise e

        logger.info("开始使用 RAG 管道为测试集生成 'answer' 和 'contexts'...")
        self.test_dataset = self.test_dataset.map(
            self._integrate_testset,
            batched=True,
            batch_size=self.config.batch_size,
        )
        return self.test_dataset
    
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

    def run_evaluation(self):
        logger.info("开始执行 Ragas 评估...")
        if self.test_dataset is None:
            self.load_and_process_testset()

        result = evaluate(
            self.test_dataset, # type: ignore
            metrics=self.metrics     
        )

        logger.info(f"Ragas 评估结果: {result}")
        self.scores_df = result.to_pandas() # type: ignore
        return result
    
    def save_results(self):
        if self.scores_df is None:
            logger.warning("评估分数为空，跳过保存。")
            return
        
        output_csv_path = settings.EVALUATION_CSV_PATH
        try:
            self.scores_df.to_csv(output_csv_path, index=False) 
            logger.info(f"评估结果已保存至: {output_csv_path}")
        except Exception as e:
            logger.error(f"保存失败: {e}", exc_info=True)
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

# --- CLI App ---
app = typer.Typer(help="RAG 评估 CLI")

@app.command()
def benchmark(
    force_rebuild: bool = typer.Option(False, "--force-rebuild", help="强制重建向量库"),
    export: Optional[str] = typer.Option(None, "--export", help="额外导出评分 CSV 路径"),
):
    """
    运行完整的 RAG 评估流程。
    """
    # 仅在 CLI 模式下初始化日志，避免作为模块导入时污染 API 日志配置
    setup_logging(str(settings.LOG_FILE_PATH), log_level="INFO")
    
    logger.info("===================")
    logger.info("RAG 评估器启动 (CLI)")
    logger.info("===================")

    try:
        rag_pipeline, llm, embeddings = prepare_pipeline(force_rebuild=force_rebuild)
        evaluator = RAGEvaluator(rag_pipeline=rag_pipeline, llm=llm, embed_model=embeddings)

        evaluator.load_and_process_testset()
        evaluator.run_evaluation()
        evaluator.save_results()

        if export and evaluator.scores_df is not None:
            evaluator.scores_df.to_csv(export, index=False)
            typer.echo(f"评估结果已额外导出至 {export}")

        typer.echo("评估完成。")
    except Exception as exc:
        logger.critical("评估器运行失败: %s", exc, exc_info=True)
        raise typer.Exit(code=1) from exc

if __name__ == "__main__":
    app()