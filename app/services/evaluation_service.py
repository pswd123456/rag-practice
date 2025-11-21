# app/services/evaluation_service.py
import json
import logging
import pandas as pd
import io
import nest_asyncio
from typing import List, Any, cast
import ast # 用于安全地把字符串转回列表

from sqlmodel import Session
from langchain_core.documents import Document
from datasets import Dataset

# 复用已有的 Ragas 逻辑
from ragas.testset import TestsetGenerator
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

# 复用项目基础设施
from app.core.config import settings
from app.domain.models import Testset, Experiment, Knowledge, KnowledgeStatus
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.file_storage import save_bytes_to_minio, get_file_from_minio
from app.services.loader import load_single_document, normalize_metadata
from app.services.retrieval import VectorStoreManager, RetrievalService
from app.services.pipelines import RAGPipeline
from app.services.generation import QAService
from app.services.file_storage import get_minio_client, save_bytes_to_minio, get_file_from_minio
import tempfile
from pathlib import Path

# 复用 Evaluator 类
from evaluation.runner import RAGEvaluator

logger = logging.getLogger(__name__)

# 应用 nest_asyncio 防止事件循环冲突 (Ragas 内部可能需要)
nest_asyncio.apply()

# ==========================================
# 1. 测试集生成 (Generate Testset)
# ==========================================

def generate_testset_pipeline(db: Session, testset_id: int, source_doc_ids: List[int]):
    """
    根据指定的源文档生成测试集，并存入 MinIO 和 DB
    """
    from app.domain.models import Document as DBDocument # 避免命名冲突
    
    testset = db.get(Testset, testset_id)
    if not testset:
        logger.error(f"Testset {testset_id} not found")
        return

    try:
        logger.info(f"开始为 Testset {testset_id} 生成数据，源文档ID: {source_doc_ids}")
        testset.status = "GENERATING"
        db.add(testset)
        db.commit()
        # 1. 加载源文档 (从 MinIO 下载 -> LangChain Document)
        langchain_docs = []
        minio_client = get_minio_client()
        
        for doc_id in source_doc_ids:
            db_doc = db.get(DBDocument, doc_id)
            if not db_doc: 
                continue
            
            # 临时下载文件以读取内容
            suffix = Path(db_doc.filename).suffix
            with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
                minio_client.fget_object(settings.MINIO_BUCKET_NAME, db_doc.file_path, tmp.name)
                loaded = load_single_document(tmp.name)
                # 标准化 Metadata
                normalized = normalize_metadata(loaded)
                langchain_docs.extend(normalized)
        
        if not langchain_docs:
            raise ValueError("没有加载到任何有效文档，无法生成测试集")

        # 2. 初始化 Generator (复用 testset.py 的逻辑)
        # 注意：生成测试集通常需要较强的模型 (Generator LLM)
        # 这里暂时复用 qwen-flash，实际生产建议换成 qwen-max 或 gpt-4
        generator_llm = setup_qwen_llm("qwen-max") # 建议用强模型
        generator_embed = setup_embed_model("text-embedding-v4")
        
        generator = TestsetGenerator(
            llm=LangchainLLMWrapper(generator_llm), 
            embedding_model=LangchainEmbeddingsWrapper(generator_embed)
        )
        
        # 3. 执行生成 (Ragas Core)
        # testset_size 可以在 testset 表里加字段控制，这里先写死或读配置
        dataset = generator.generate_with_langchain_docs(
            langchain_docs, 
            testset_size=settings.TESTSET_SIZE
        )
        
        # 4. 转 CSV 并保存到 MinIO
        df = dataset.to_pandas() #type: ignore
        json_str = df.to_json(orient="records", lines=True, force_ascii=False)
        json_bytes = json_str.encode('utf-8')
        
        # 改后缀为 .jsonl
        file_path = f"testsets/{testset.id}_{testset.name}.jsonl"
        # content_type 改为 json
        save_bytes_to_minio(json_bytes, file_path, "application/json")
        
        # 5. 更新 DB
        testset.file_path = file_path
        testset.description = f"Generated from {len(source_doc_ids)} docs. Size: {len(df)}"
        testset.status = "COMPLETED" # <--- 标记完成
        testset.error_message = None
        db.add(testset)
        db.commit()
        logger.info(f"Testset {testset_id} 生成完成并保存到 {file_path}")

    except Exception as e:
        logger.error(f"Testset 生成失败: {e}", exc_info=True)
        # [修改] 标记失败
        # 重新获取对象防止 session 脱离
        testset = db.get(Testset, testset_id) 
        if testset:
            testset.status = "FAILED"
            testset.error_message = str(e)
            db.add(testset)
            db.commit()
        raise e

# ==========================================
# 2. 运行实验 (Run Experiment)
# ==========================================

def run_experiment_pipeline(db: Session, experiment_id: int):
    """
    执行一次 RAG 评测实验
    """
    exp = db.get(Experiment, experiment_id)
    if not exp:
        return

    try:
        logger.info(f"开始执行实验 {experiment_id}...")
        exp.status = "RUNNING"
        db.add(exp)
        db.commit()

        # 1. 准备组件
        kb = exp.knowledge
        testset_record = exp.testset
        
        # 1.1 加载 Testset CSV
        csv_bytes = get_file_from_minio(testset_record.file_path)
        # 保存为临时文件供 datasets 库读取 (ragas 内部依赖 datasets.load_dataset)
        json_str = csv_bytes.decode("utf-8")
        data_list = [json.loads(line) for line in json_str.splitlines() if line.strip()]
        
        # 直接从内存构建 Dataset
        from datasets import Dataset
        hf_dataset = Dataset.from_list(data_list)
            
        # 1.2 初始化 RAG Pipeline (根据 KB 配置 + 实验运行时参数)
        # [关键] 这里体现了架构的灵活性：
        # KB 决定了 collection_name 和 embed_model
        # Experiment 决定了 top_k, strategy, student_llm
        
        embed_model = setup_embed_model(kb.embed_model)
        vector_store_manager = VectorStoreManager(
            collection_name=f"kb_{kb.id}", 
            embed_model=embed_model
        )
        # 确保连接，但不自动填充 (auto_ingest=False)
        vector_store_manager.ensure_collection()
        
        # 读取运行时参数
        params = exp.runtime_params or {}
        top_k = params.get("top_k", settings.TOP_K)
        strategy = params.get("strategy", "default")
        student_llm_name = params.get("llm", "qwen-flash") # 被测模型
        
        student_llm = setup_qwen_llm(student_llm_name)
        qa_service = QAService(student_llm)
        
        # 动态构建 Pipeline
        pipeline = RAGPipeline.build(
            store_manager=vector_store_manager,
            qa_service=qa_service,
            top_k=top_k,
            strategy=strategy
        )
        
        # 2. 初始化 Evaluator (复用 runner.py 中的类)
        # 注意：Evaluator 需要 Judge LLM，通常需要较强的模型
        judge_llm = setup_qwen_llm("qwen-max") 
        
        evaluator = RAGEvaluator(
            rag_pipeline=pipeline,
            llm=judge_llm,         # Judge
            embed_model=embed_model # Metric 计算用的 Embed
        )
        
        # 3. 注入数据 (Hack RAGEvaluator)
        # RAGEvaluator原本是从配置读路径，现在我们要让它读我们刚才下载的临时 CSV
        # 我们手动加载 dataset
        from datasets import Dataset
        hf_dataset = Dataset.from_list(data_list)

        current_cols = hf_dataset.column_names
        rename_map = {"user_input": "question", "reference": "ground_truth"}
        if "user_input" in current_cols:
            hf_dataset = hf_dataset.rename_columns(rename_map)
            
        evaluator.test_dataset = hf_dataset
        
        # 4. 执行生成与评估
        # 先生成 answer/context (使用 Student LLM)
        evaluator.load_and_process_testset() 
        # 再跑分 (使用 Judge LLM)
        result = evaluator.run_evaluation()
        
        # Ragas Result -> Dict
        def get_score(res, key: str) -> float:
            val = 0.0
            try:
                # 方案 A: 尝试标准下标访问
                val = res[key]
                
                # === [优化] 针对 Ragas 返回 list 的情况 ([1.0]) 进行拆包 ===
                if isinstance(val, list):
                    if len(val) > 0:
                        val = val[0] # 取第一个元素
                    else:
                        return 0.0 # 空列表
                # ========================================================

                return float(val)
            except Exception as e_a:
                # 如果方案 A 失败，记录日志并尝试方案 B
                logger.warning(f"[GetScore] 方案A获取 {key} 失败: {e_a}")
                
                try:
                    # 方案 B: 暴力解析字符串 (保持不变作为最后防线)
                    res_str = str(res)
                    res_dict = ast.literal_eval(res_str)
                    if isinstance(res_dict, dict) and key in res_dict:
                        return float(res_dict[key])
                except Exception as e_b:
                    logger.error(f"[GetScore] 方案B也失败了: {e_b}")
            
            return 0.0
        
        # 5. 更新结果到 DB
        exp.faithfulness = get_score(result, "faithfulness")
        exp.answer_relevancy = get_score(result, "answer_relevancy")
        exp.context_recall = get_score(result, "context_recall")
        exp.context_precision = get_score(result, "context_precision")
        
        exp.status = "COMPLETED"
        db.add(exp)
        db.commit()
        logger.info(f"实验 {experiment_id} 完成。Scores: {result}")

    except Exception as e:
        logger.error(f"实验 {experiment_id} 失败: {e}", exc_info=True)
        exp.status = "FAILED"
        exp.error_message = str(e)
        db.add(exp)
        db.commit()