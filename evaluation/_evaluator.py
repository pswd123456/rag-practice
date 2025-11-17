# -*- coding: utf-8 -*-
"""
RAG 评估器 (evaluator.py)

负责:
1. 加载和预处理 Ragas 测试集 (testset)。
2. 使用 RAG 管道为测试集生成 'answer' 和 'contexts'。
3. 运行 Ragas 指标 (Faithfulness, AnswerRelevancy等) 进行评估。
4. 保存评估分数。
5. 可通过 `python -m evaluation.evaluator` 独立运行。
"""

# --- Ragas 和 Datasets 导入 ---
from datasets import load_dataset, Dataset
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextRecall,
    ContextPrecision
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas import evaluate

# --- 项目内部导入 ---
from app.core.config import settings
from app.services import ingest
from app.services.llm.llm_factory import setup_qwen_llm
from app.services.embedding.embedding_factory import setup_hf_embed_model
from app.services.pipeline import RAGPipeline

# --- 日志和标准库导入 ---
import logging
import logging.config
import os
import sys
from app.core.logging_setup import get_logging_config
import warnings

warnings.filterwarnings(
    "ignore", 
    message=".*Torch was not compiled with flash attention.*"
)

# --- 配置全局日志 (从配置加载) ---
# (确保 'logs' 文件夹存在)
os.makedirs(settings.LOG_DIR, exist_ok=True) 
logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))
logging.config.dictConfig(logging_config_dict)
# --- 配置完成 ---

# 获取 'evaluator' 模块的 logger
logger = logging.getLogger(__name__)


class RAGEvaluator:
    """
    封装了 RAG 评估所需的所有逻辑，包括:
    - 数据加载和处理 (load_and_process_testset)
    - RAG 管道集成 (_integrate_testset)
    - Ragas 评估执行 (run_evaluation)
    - 结果保存 (save_results)
    """
    def __init__(self, rag_pipeline: RAGPipeline,llm,embed_model):
        """
        初始化评估器。

        参数:
            rag_pipeline (RAGPipeline): 一个已实例化的、准备就绪的 RAG 管道对象。
        """
        self.pipeline = rag_pipeline

        logger.debug("正在初始化 Ragas LLM 和 Embeddings 包装器...")
        ragas_llm = LangchainLLMWrapper(llm)
        ragas_embed = LangchainEmbeddingsWrapper(embed_model)
        
        self.metrics = [
            Faithfulness(llm=ragas_llm),
            AnswerRelevancy(llm=ragas_llm, embeddings=ragas_embed),
            ContextRecall(llm=ragas_llm),
            ContextPrecision(llm=ragas_llm)     
        ]
        logger.info("Ragas 评估指标已初始化。")

        self.test_dataset = None
        self.scores_df = None

    def load_and_process_testset(self):
        """
        加载原始测试集 (CSV), 并将其处理为 Ragas 评估所需的格式。
        
        步骤:
        1. 从 TESTSET_OUTPUT_PATH 加载 CSV。
        2. 重命名列 (e.g., 'user_input' -> 'question', 'reference' -> 'ground_truth')。
        3. 删除评估不需要的原始列。
        4. 通过 .map() 调用 RAG 管道 (_integrate_testset)，
           为数据集动态生成 'answer' 和 'contexts' 列。
        
        返回:
            datasets.Dataset: 处理完成并包含 RAG 输出的测试集。
        """
        logger.info("开始加载和处理测试集...")
        hf_dataset =  load_dataset("csv", data_files=str(settings.TESTSET_OUTPUT_PATH))

        self.test_dataset = hf_dataset["train"]
        assert isinstance(self.test_dataset, Dataset)    

        logger.debug("重命名列以匹配 Ragas schema (question, ground_truth)...")
        rename_columns_dict = {
            "user_input": "question",
            "reference": "ground_truth",
        }
        self.test_dataset = self.test_dataset.rename_columns(rename_columns_dict)
        
        logger.debug("删除不必要的原始列...")
        self.test_dataset = self.test_dataset.remove_columns(["reference_contexts", 'synthesizer_name'])
        
        logger.info("开始使用 RAG 管道为测试集生成 'answer' 和 'contexts' (map)...")
        self.test_dataset = self.test_dataset.map(
            self._integrate_testset, 
            batched=True, 
            batch_size=16  # (可以调整批次大小)
        )
        logger.info("测试集处理和 RAG 管道集成完成。")
        return self.test_dataset
    
    def _integrate_testset(self, batch):
        """
        (内部辅助函数) 由 .map() 调用，用于批量处理测试集。
        
        参数:
            batch (dict): Hugging Face Datasets 传递的批处理数据。

        返回:
            dict: 包含 'answer' 和 'contexts' 列表的字典，将作为新列添加。
        """
        logger.debug(f"正在处理批次，大小: {len(batch['question'])}")
        questions  = batch["question"]

        # 1. 批量检索
        retriever = self.pipeline.get_retriever()
        contexts_docs = retriever.batch(questions)

        # (将 Document 列表转换为 Ragas 期望的 str 列表)
        contexts_str_lists = [
            [doc.page_content for doc in doc_list] 
            for doc_list in contexts_docs
        ]

        # 2. 批量生成
        generation_chain = self.pipeline.get_generation_chain()
        inputs_for_chain = []
        for q, c_list in zip(questions, contexts_str_lists):
            formatted_context = "\n\n".join(c_list)
            inputs_for_chain.append({
                "question": q,
                "context": formatted_context
            })

        answer_list = generation_chain.batch(inputs_for_chain)

        return {
            "answer": answer_list,
            "contexts": contexts_str_lists
        }

    def run_evaluation(self):
        """
        执行 Ragas 评估。
        
        如果测试集未加载，会自动调用 load_and_process_testset()。
        评估结果 (字典) 会被打印，并转换为 Pandas DataFrame 存储在 self.scores_df 中。
        
        返回:
            ragas.Result: Ragas 评估结果对象。
        """
        logger.info("开始执行 Ragas 评估...")
        if self.test_dataset is None:
            logger.info("测试集 (self.test_dataset) 未加载，自动开始加载和处理...")
            self.load_and_process_testset()

        result = evaluate(
            self.test_dataset, #type: ignore
            metrics=self.metrics     
        )

        logger.info(f"Ragas 评估结果 (字典): {result}")

        self.scores_df = result.to_pandas()#type: ignore
        logger.info("评估分数已转换为 Pandas DataFrame。")
        return result
    
    def save_results(self):
        """
        将评估结果 (Pandas DataFrame) 保存到 CSV 文件。
        路径由 config.SCORE_CSV_PATH 定义。
        """
        if self.scores_df is None:
            logger.warning("评估分数 (scores_df) 为空，无法保存。请先调用 run_evaluation()。")
            return
        
        output_csv_path = settings.EVALUATION_CSV_PATH
        try:
            self.scores_df.to_csv(output_csv_path, index=False) 
            logger.info(f"评估结果已成功保存到: {output_csv_path}")
        except Exception as e:
            logger.error(f"保存评估结果到 {output_csv_path} 失败: {e}", exc_info=True)


if __name__ == "__main__":
    """
    当文件作为主程序 (python -m evaluation.evaluator) 运行时的主入口。
    """
    logger.info("===================")
    logger.info("RAG 评估器 (evaluator.py) 启动...")
    logger.info("===================")
    
    try:
        logger.info("🛠️ 正在设置 RAG 管道...")
        collection_name = settings.CHROMADB_COLLECTION_NAME

        embeddings_name = "Qwen3-Embedding-0.6B"
        embeddings = setup_hf_embed_model(embeddings_name)
        logger.info(f" embeddings 模型已就绪: {embeddings_name}") 

        vector_store = ingest.build_or_get_vector_store(collection_name,embeddings)
        
        llm_name = "qwen-flash"
        llm = setup_qwen_llm(llm_name)
        logger.info(f" LLM 模型已就绪: {llm_name}")
        
        retriever = vector_store.as_retriever() 
        rag_pipeline = RAGPipeline(llm=llm, retriever=retriever)
        logger.info("RAG 管道已就绪。")

        logger.info(" evaluator...")
        evaluator = RAGEvaluator(rag_pipeline=rag_pipeline,llm=llm,embed_model=embeddings)
        
        logger.info("⚙️ 正在加载和处理测试集...")
        # (注意: 即使 run_evaluation 有检查，这里也保持原始逻辑显式调用)
        evaluator.load_and_process_testset()
        
        logger.info("⚙️ 正在运行评估...")
        results = evaluator.run_evaluation()

        logger.info("✅ 评估完成!")
        
        if evaluator.scores_df is not None:
            logger.info(f"评估分数 (DataFrame 摘要):\n{evaluator.scores_df.describe()}")
        else:
            logger.warning("评估未生成 scores_df。")

        evaluator.save_results()

    except Exception as e:
        logger.critical(f"评估器主程序运行失败: {e}", exc_info=True)
        sys.exit(1)

    logger.info("===================")
    logger.info("评估器 (evaluator.py) 运行结束。")
    logger.info("===================")