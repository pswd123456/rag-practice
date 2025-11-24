# app/services/evaluation_service.py
import asyncio
import logging
import nest_asyncio
import tempfile
from pathlib import Path
from typing import List
from sqlmodel import Session
from langfuse import Langfuse

# 复用已有的 Ragas 逻辑
from ragas.testset import TestsetGenerator
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

# 复用项目基础设施
from app.core.config import settings
from app.domain.models import Testset, Experiment
# [修改] 引入通用工厂 setup_llm，移除 setup_qwen_llm
from app.services.factories import setup_embed_model, setup_llm
from app.services.file_storage import save_bytes_to_minio, get_minio_client
from app.services.loader import load_single_document
from app.services.retrieval import VectorStoreManager
from app.services.pipelines import RAGPipeline
from app.services.generation import QAService
from app.services.evaluation.runner import RAGEvaluator

logger = logging.getLogger(__name__)

# 应用 nest_asyncio 防止事件循环冲突
nest_asyncio.apply()

# ==========================================
# 1. 测试集生成 (Generate Testset)
# ==========================================

def generate_testset_pipeline(db: Session, testset_id: int, source_doc_ids: List[int]):
    """
    根据指定的源文档生成测试集
    """
    from app.domain.models import Document as DBDocument
    
    langfuse = Langfuse()
    testset = db.get(Testset, testset_id)
    if not testset:
        logger.error(f"Testset {testset_id} not found")
        return

    try:
        logger.info(f"开始为 Testset {testset_id} 生成数据，源文档ID: {source_doc_ids}")
        testset.status = "GENERATING"
        db.add(testset)
        db.commit()
        
        # 1. 加载源文档
        langchain_docs = []
        minio_client = get_minio_client()
        
        for doc_id in source_doc_ids:
            db_doc = db.get(DBDocument, doc_id)
            if not db_doc: 
                continue
            
            suffix = Path(db_doc.filename).suffix
            with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
                minio_client.fget_object(settings.MINIO_BUCKET_NAME, db_doc.file_path, tmp.name)
                loaded = load_single_document(tmp.name)
                langchain_docs.extend(loaded)
        
        if not langchain_docs:
            raise ValueError("没有加载到任何有效文档，无法生成测试集")

        # 2. 初始化 Generator
        # [修改] 使用 setup_llm 替代 setup_qwen_llm，默认使用强模型生成数据
        # 未来这里也可以从配置读取生成器模型
        generator_llm = setup_llm("qwen-max") 
        generator_embed = setup_embed_model("text-embedding-v4")
        
        generator = TestsetGenerator(
            llm=LangchainLLMWrapper(generator_llm), 
            embedding_model=LangchainEmbeddingsWrapper(generator_embed)
        )
        
        # 3. 执行生成
        dataset = generator.generate_with_langchain_docs(
            langchain_docs, 
            testset_size=settings.TESTSET_SIZE
        )
        
        # 4. 转 CSV 并保存到 MinIO
        df = dataset.to_pandas() #type: ignore
        json_str = df.to_json(orient="records", lines=True, force_ascii=False)
        json_bytes = json_str.encode('utf-8')
        
        file_path = f"testsets/{testset.id}_{testset.name}.jsonl"
        save_bytes_to_minio(json_bytes, file_path, "application/json")
        
        # 5. 同步上传到 Langfuse Datasets
        lf_dataset_name = f"testset_{testset.id}_{testset.name}"
        logger.info(f"正在同步测试集到 Langfuse: {lf_dataset_name}")
        
        langfuse.create_dataset(
            name=lf_dataset_name,
            description=f"Auto-generated from docs: {source_doc_ids}",
            metadata={"testset_id": testset_id, "source": "rag-practice"}
        )
        
        for _, row in df.iterrows():
            langfuse.create_dataset_item(
                dataset_name=lf_dataset_name,
                input=row["user_input"],
                expected_output=row["reference"],
                metadata={
                    "source_context": row.get("reference_contexts")
                }
            )

        # 6. 更新 DB
        testset.file_path = file_path
        testset.description = f"Generated from {len(source_doc_ids)} docs. Size: {len(df)}"
        testset.status = "COMPLETED"
        testset.error_message = None
        db.add(testset)
        db.commit()
        logger.info(f"Testset {testset_id} 生成完成")

    except Exception as e:
        logger.error(f"Testset 生成失败: {e}", exc_info=True)
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
    执行 RAG 评测实验：Langfuse Experiment Runner 模式
    支持动态选择 Student LLM 和 Judge LLM
    """
    langfuse = Langfuse()
    
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
        ts = exp.testset
        dataset_name = f"testset_{ts.id}_{ts.name}"
        
        # 获取运行时参数
        params = exp.runtime_params or {}
        
        # --- [核心修改] 动态加载模型 ---
        # 1. Student Model: 负责回答问题
        # 如果参数里叫 'llm' (兼容旧版) 或 'student_model' (新版)，没传则默认 qwen-flash
        student_model_name = params.get("student_model") or params.get("llm") or "qwen-flash"
        logger.info(f"Experiment Student Model: {student_model_name}")
        student_llm = setup_llm(student_model_name)
        
        # 2. Judge Model: 负责 Ragas 评分
        # 默认为 qwen-max，也可以配置为 google/gemini-pro 以节省成本
        judge_model_name = params.get("judge_model", "qwen-max")
        logger.info(f"Experiment Judge Model: {judge_model_name}")
        judge_llm = setup_llm(judge_model_name)
        # -----------------------------
        
        embed_model = setup_embed_model(kb.embed_model)
        vector_store_manager = VectorStoreManager(f"kb_{kb.id}", embed_model)
        vector_store_manager.ensure_collection()
        
        qa_service = QAService(student_llm) 
        
        pipeline = RAGPipeline.build(
            store_manager=vector_store_manager,
            qa_service=qa_service,
            top_k=params.get("top_k", settings.TOP_K),
            strategy=params.get("strategy", "default")
        )
        
        # 将动态的 judge_llm 传入评估器
        evaluator = RAGEvaluator(
            rag_pipeline=pipeline,
            llm=judge_llm, 
            embed_model=embed_model
        )

        try:
            # 适配 Prompt 语言
            asyncio.run(evaluator.adapt_metrics(language="chinese"))
        except Exception as e:
            logger.error(f"指标适配流程异常: {e}，实验将使用默认 Prompt 继续运行")

        # 2. 从 Langfuse 加载数据集
        try:
            lf_dataset = langfuse.get_dataset(dataset_name)
        except Exception as e:
            raise ValueError(f"无法在 Langfuse 找到数据集: {dataset_name}")

        agg_scores = {"faithfulness": [], "answer_relevancy": [], "context_recall": [], "context_precision": []}

        # 3. 遍历并运行实验
        for item in lf_dataset.items:
            question = item.input
            ground_truth = item.expected_output
            
            with item.run(
                run_name=f"exp_{experiment_id}_{kb.name}",
                run_description=f"Strat: {params.get('strategy')} | Model: {student_model_name}",
                run_metadata={
                    "experiment_id": experiment_id,
                    "knowledge_id": kb.id,
                    "student_model": student_model_name,
                    "judge_model": judge_model_name,
                    **params
                }
            ) as trace:
                
                # A. 执行 RAG Pipeline (使用 Student LLM)
                answer_result, docs = asyncio.run(pipeline.async_query(question))
                retrieved_contexts = [d.page_content for d in docs]
                
                # B. 计算 Ragas 分数 (使用 Judge LLM)
                scores = asyncio.run(evaluator.score_single_item(
                    question=question,
                    answer=answer_result,
                    contexts=retrieved_contexts,
                    ground_truth=ground_truth
                ))
                
                safe_scores = {k: float(v) for k, v in scores.items()}
                
                # C. 上报分数
                for metric_name, val in safe_scores.items():
                    trace.score(name=metric_name, value=val)
                    if metric_name in agg_scores:
                        agg_scores[metric_name].append(val)

        # 4. 计算平均分
        def avg(lst):
            return float(sum(lst) / len(lst)) if lst else 0.0

        exp.faithfulness = avg(agg_scores["faithfulness"])
        exp.answer_relevancy = avg(agg_scores["answer_relevancy"])
        exp.context_recall = avg(agg_scores["context_recall"])
        exp.context_precision = avg(agg_scores["context_precision"])
        
        exp.status = "COMPLETED"
        db.add(exp)
        db.commit()
        logger.info(f"实验 {experiment_id} 完成。")

    except Exception as e:
        logger.error(f"实验 {experiment_id} 失败: {e}", exc_info=True)
        db.rollback()
        exp = db.get(Experiment, experiment_id)
        if exp:
            exp.status = "FAILED"
            exp.error_message = str(e)[:500]
            db.add(exp)
            db.commit()