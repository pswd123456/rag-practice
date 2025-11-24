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
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.file_storage import save_bytes_to_minio, get_minio_client
from app.services.loader import load_single_document
from app.services.retrieval import VectorStoreManager
from app.services.pipelines import RAGPipeline
from app.services.generation import QAService
from app.services.evaluation.runner import RAGEvaluator

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
                langchain_docs.extend(loaded)
        
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
        
        # 🟢 5. 同步上传到 Langfuse Datasets
        lf_dataset_name = f"testset_{testset.id}_{testset.name}"
        logger.info(f"正在同步测试集到 Langfuse: {lf_dataset_name}")
        
        langfuse.create_dataset(
            name=lf_dataset_name,
            description=f"Auto-generated from docs: {source_doc_ids}",
            metadata={"testset_id": testset_id, "source": "rag-practice"}
        )
        
        # 遍历 DataFrame 上传 Item
        for _, row in df.iterrows():
            langfuse.create_dataset_item(
                dataset_name=lf_dataset_name,
                input=row["user_input"],          # Question
                expected_output=row["reference"], # Ground Truth
                metadata={
                    "source_context": row.get("reference_contexts")
                }
            )

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
    执行 RAG 评测实验：Langfuse Experiment Runner 模式
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
        
        embed_model = setup_embed_model(kb.embed_model)
        vector_store_manager = VectorStoreManager(f"kb_{kb.id}", embed_model)
        vector_store_manager.ensure_collection()
        
        params = exp.runtime_params or {}
        student_llm = setup_qwen_llm(params.get("llm", "qwen-flash"))
        qa_service = QAService(student_llm) 
        
        pipeline = RAGPipeline.build(
            store_manager=vector_store_manager,
            qa_service=qa_service,
            top_k=params.get("top_k", settings.TOP_K),
            strategy=params.get("strategy", "default")
        )
        
        judge_llm = setup_qwen_llm("qwen-max", max_tokens=2048) 
        evaluator = RAGEvaluator(
            rag_pipeline=pipeline,
            llm=judge_llm,
            embed_model=embed_model
        )

        try:
            # 确保在 worker 线程中调用，不会阻塞主事件循环
            asyncio.run(evaluator.adapt_metrics(language="chinese"))
        except Exception as e:
            logger.error(f"指标适配流程异常: {e}，实验将使用默认 Prompt 继续运行")

        # 2. 从 Langfuse 加载数据集
        logger.info(f"从 Langfuse 加载数据集: {dataset_name}")
        try:
            lf_dataset = langfuse.get_dataset(dataset_name)
        except Exception as e:
            raise ValueError(f"无法在 Langfuse 找到数据集: {dataset_name}。请确认该测试集是否已成功生成并同步。")

        agg_scores = {"faithfulness": [], "answer_relevancy": [], "context_recall": [], "context_precision": []}

        # 3. 遍历并运行实验
        for item in lf_dataset.items:
            question = item.input
            ground_truth = item.expected_output
            
            with item.run(
                run_name=f"exp_{experiment_id}_{kb.name}",
                run_description=f"Strategy: {params.get('strategy')}",
                run_metadata={
                    "experiment_id": experiment_id,
                    "knowledge_id": kb.id,
                    **params
                }
            ) as trace:
                
                # A. 执行 RAG Pipeline
                answer_result, docs = asyncio.run(pipeline.async_query(question))
                retrieved_contexts = [d.page_content for d in docs]
                
                # B. 计算 Ragas 分数
                scores = asyncio.run(evaluator.score_single_item(
                    question=question,
                    answer=answer_result,
                    contexts=retrieved_contexts,
                    ground_truth=ground_truth
                ))
                
                # 🟢 [关键修复] 强制转换为原生 float，防止 numpy 类型污染
                safe_scores = {k: float(v) for k, v in scores.items()}
                
                # C. 上报分数到 Langfuse
                for metric_name, val in safe_scores.items():
                    trace.score(name=metric_name, value=val)
                    if metric_name in agg_scores:
                        agg_scores[metric_name].append(val)

        # 4. 计算平均分并更新 DB
        def avg(lst):
            # 再次确保结果是原生 float
            return float(sum(lst) / len(lst)) if lst else 0.0

        exp.faithfulness = avg(agg_scores["faithfulness"])
        exp.answer_relevancy = avg(agg_scores["answer_relevancy"])
        exp.context_recall = avg(agg_scores["context_recall"])
        exp.context_precision = avg(agg_scores["context_precision"])
        
        exp.status = "COMPLETED"
        db.add(exp)
        db.commit()
        logger.info(f"实验 {experiment_id} 完成。Avg Scores: Faith={exp.faithfulness:.2f}")

    except Exception as e:
        logger.error(f"实验 {experiment_id} 失败: {e}", exc_info=True)
        # 事务回滚防止污染
        db.rollback()
        # 重新获取 exp 对象以记录错误
        exp = db.get(Experiment, experiment_id)
        if exp:
            exp.status = "FAILED"
            exp.error_message = str(e)[:500]
            db.add(exp)
            db.commit()