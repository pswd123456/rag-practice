import asyncio
import logging
import nest_asyncio
import tempfile
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload
from langfuse import Langfuse

# 复用已有的 Ragas 逻辑
from ragas.testset import TestsetGenerator
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

from app.core.config import settings
from app.domain.models import Testset, Experiment, Document, Knowledge
from app.services.factories import setup_embed_model, setup_llm
from app.services.minio.file_storage import save_bytes_to_minio, get_minio_client

# [Modified] 引入与 Ingest 管道一致的加载器
from app.services.loader.docling_loader import load_and_chunk_docling_document
from app.services.loader import load_single_document, split_docs

from app.services.retrieval import VectorStoreManager
from app.services.pipelines import RAGPipeline
from app.services.generation import QAService
from app.services.evaluation.evaluation_runner import RAGEvaluator

logger = logging.getLogger(__name__)

nest_asyncio.apply()

# ==========================================
# 1. 测试集生成 (Generate Testset)
# ==========================================

async def generate_testset_pipeline(db: AsyncSession, testset_id: int, source_doc_ids: List[int], generator_model: str = "qwen-max"):
    """
    根据指定的源文档生成测试集 (异步版)
    [Consistency Fix]: 确保使用与 Ingestion 阶段完全一致的加载与切片策略 (Docling + HybridChunker)
    """
    testset = await db.get(Testset, testset_id)
    if not testset:
        logger.error(f"Testset {testset_id} not found")
        return

    try:
        logger.info(f"开始为 Testset {testset_id} 生成数据，源文档ID: {source_doc_ids}")
        testset.status = "GENERATING"
        db.add(testset)
        await db.commit()
        
        # 2. 预加载文档信息 (含 Knowledge 配置)
        # [Fix] 我们需要获取 chunk_size，以便 Docling 切片与入库时一致
        doc_infos = []
        for doc_id in source_doc_ids:
            # 显式加载 knowledge_base 关系
            stmt = select(Document).where(Document.id == doc_id).options(selectinload(Document.knowledge_base))
            result = await db.exec(stmt)
            db_doc = result.first()
            
            if db_doc:
                kb = db_doc.knowledge_base
                # 默认值防守
                c_size = kb.chunk_size if kb else settings.CHUNK_SIZE
                c_overlap = kb.chunk_overlap if kb else settings.CHUNK_OVERLAP
                
                doc_infos.append({
                    "filename": db_doc.filename,
                    "file_path": db_doc.file_path,
                    "chunk_size": c_size,
                    "chunk_overlap": c_overlap
                })
        
        if not doc_infos:
            raise ValueError("未找到有效文档记录")

        # 定义阻塞的加载函数 (Update)
        def _blocking_load(infos: List[Dict[str, Any]]):
            loaded_docs = []
            minio_client = get_minio_client()
            
            for info in infos:
                filename = info["filename"]
                file_path = info["file_path"]
                chunk_size = info["chunk_size"]
                chunk_overlap = info["chunk_overlap"]
                
                suffix = Path(filename).suffix.lower()
                
                # 创建临时文件
                with tempfile.NamedTemporaryFile(delete=True, suffix=suffix) as tmp:
                    # 下载
                    minio_client.fget_object(
                        bucket_name=settings.MINIO_BUCKET_NAME, 
                        object_name=file_path, 
                        file_path=tmp.name
                    )
                    
                    # [Critical Fix] 分支处理：保持与 Ingest Pipeline 一致
                    if suffix in [".pdf", ".docx", ".doc"]:
                        logger.info(f"Testset Generation: 使用 Docling 处理 {filename} (Size={chunk_size})")
                        # 使用 Docling HybridChunker
                        docs = load_and_chunk_docling_document(tmp.name, chunk_size=chunk_size)
                        loaded_docs.extend(docs)
                    else:
                        logger.info(f"Testset Generation: 使用 BasicLoader 处理 {filename}")
                        # 使用标准加载 + RecursiveSplitter
                        raw_docs = load_single_document(tmp.name)
                        splitted = split_docs(raw_docs, chunk_size, chunk_overlap)
                        loaded_docs.extend(splitted)
                        
            return loaded_docs

        # 在线程中执行加载
        langchain_docs = await asyncio.to_thread(_blocking_load, doc_infos)
        
        if not langchain_docs:
            raise ValueError("没有加载到任何有效文档内容")
        
        logger.info(f"文档加载完成，共 {len(langchain_docs)} 个切片。开始生成 QA 对...")

        # 3. 执行生成 (Ragas Generator)
        def _generation_task():
            generator_llm = setup_llm(generator_model) 
            # 使用更强的 Embedding 模型以提高 Testset 质量 (Evaluation 通常不惜成本)
            generator_embed = setup_embed_model("text-embedding-v4")
            
            generator = TestsetGenerator(
                llm=LangchainLLMWrapper(generator_llm), 
                embedding_model=LangchainEmbeddingsWrapper(generator_embed)
            )
            
            # generate_with_langchain_docs 会使用传入的 chunks (Nodes) 生成问题
            # 因为我们传入的是 Docling 切好的 chunks，所以生成的 Context 也是基于 Docling 的
            return generator.generate_with_langchain_docs(
                langchain_docs, 
                testset_size=settings.TESTSET_SIZE
            )

        dataset = await asyncio.to_thread(_generation_task)
        
        # 4. 转 CSV 并保存到 MinIO (Thread)
        def _save_task():
            df = dataset.to_pandas() # type: ignore
            json_str = df.to_json(orient="records", lines=True, force_ascii=False)
            json_bytes = json_str.encode('utf-8')
            
            file_path = f"testsets/{testset_id}_{testset.name}.jsonl"
            save_bytes_to_minio(json_bytes, file_path, "application/json")
            
            # 同步到 Langfuse
            try:
                langfuse = Langfuse()
                lf_dataset_name = f"testset_{testset_id}_{testset.name}"
                langfuse.create_dataset(
                    name=lf_dataset_name,
                    description=f"Docs: {source_doc_ids}. Model: {generator_model}. (Docling/Aligned)",
                    metadata={"testset_id": testset_id, "source": "rag-practice"}
                )
                for _, row in df.iterrows():
                    langfuse.create_dataset_item(
                        dataset_name=lf_dataset_name,
                        input=row["user_input"],
                        expected_output=row["reference"],
                        metadata={"source_context": row.get("reference_contexts")}
                    )
            except Exception as e:
                logger.warning(f"Langfuse dataset upload failed: {e}")

            return file_path, len(df)

        saved_path, count = await asyncio.to_thread(_save_task)

        # 5. 更新 DB
        testset = await db.get(Testset, testset_id)
        if testset:
            testset.file_path = saved_path
            testset.description = f"Generated by {generator_model} (Docling Enabled). Size: {count}"
            testset.status = "COMPLETED"
            testset.error_message = None
            db.add(testset)
            await db.commit()
        
        logger.info(f"Testset {testset_id} 生成完成")

    except Exception as e:
        logger.error(f"Testset 生成失败: {e}", exc_info=True)
        await db.rollback()
        testset = await db.get(Testset, testset_id) 
        if testset:
            testset.status = "FAILED"
            testset.error_message = str(e)
            db.add(testset)
            await db.commit()
        raise e

# ... (Run Experiment 部分保持不变) ...
async def run_experiment_pipeline(db: AsyncSession, experiment_id: int):
    # 复用之前的逻辑，未修改部分省略以节省篇幅，但请保留原文件中的完整代码
    stmt = select(Experiment).where(Experiment.id == experiment_id).options(
        selectinload(Experiment.knowledge),
        selectinload(Experiment.testset)
    )
    result = await db.exec(stmt)
    exp = result.first()
    
    if not exp:
        return

    try:
        logger.info(f"开始执行实验 {experiment_id}...")
        exp.status = "RUNNING"
        db.add(exp)
        await db.commit()

        # 2. 准备组件
        kb = exp.knowledge
        ts = exp.testset
        dataset_name = f"testset_{ts.id}_{ts.name}"
        params = exp.runtime_params or {}
        
        # 动态加载模型
        student_model_name = params.get("student_model") or params.get("llm") or "qwen-flash"
        student_llm = setup_llm(student_model_name)
        
        judge_model_name = params.get("judge_model", "qwen-max")
        judge_llm = setup_llm(judge_model_name)
        
        embed_model = setup_embed_model(kb.embed_model)
        
        # VectorStore 初始化 (部分涉及网络，可考虑 to_thread，但 ensure_collection 主要是检查)
        vector_store_manager = VectorStoreManager(f"kb_{kb.id}", embed_model)
        await asyncio.to_thread(vector_store_manager.ensure_collection)
        
        qa_service = QAService(student_llm) 
        
        pipeline = RAGPipeline.build(
            store_manager=vector_store_manager,
            qa_service=qa_service,
            top_k=params.get("top_k", settings.TOP_K),
            strategy=params.get("strategy", "default")
        )
        
        evaluator = RAGEvaluator(
            rag_pipeline=pipeline,
            llm=judge_llm, 
            embed_model=embed_model
        )

        try:
            await evaluator.adapt_metrics(language="chinese")
        except Exception as e:
            logger.error(f"指标适配流程异常: {e}")

        # 3. 加载数据集 (Langfuse API -> Thread)
        def _get_dataset():
            langfuse = Langfuse()
            return langfuse.get_dataset(dataset_name)
        
        lf_dataset = await asyncio.to_thread(_get_dataset)

        agg_scores = {"faithfulness": [], 
                      "answer_relevancy": [], 
                      "context_recall": [], 
                      "context_precision": [], 
                      "answer_accuracy": [], 
                      "context_entities_recall": []
                      }

        # 4. 遍历并运行实验
        # 注意：这里我们已经是 async 函数了，可以直接 await pipeline.async_query
        for item in lf_dataset.items:
            question = item.input
            ground_truth = item.expected_output
            
            # Langfuse 的 trace 上下文管理
            with item.run(
                run_name=f"exp_{experiment_id}_{kb.name}",
                run_description=f"Strat: {params.get('strategy')} | Model: {student_model_name}",
                run_metadata={
                    "experiment_id": experiment_id,
                    "knowledge_id": kb.id,
                    **params
                }
            ) as trace:
                
                # A. 执行 RAG Pipeline (异步)
                # pipeline.async_query 已经是原生异步的
                answer_result, docs = await pipeline.async_query(question)
                retrieved_contexts = [d.page_content for d in docs]
                
                # B. 计算 Ragas 分数 (异步)
                # evaluator.score_single_item 已经是原生异步的
                scores = await evaluator.score_single_item(
                    question=question,
                    answer=answer_result,
                    contexts=retrieved_contexts,
                    ground_truth=ground_truth
                )
                
                safe_scores = {k: float(v) for k, v in scores.items()}
                
                # C. 上报分数
                for metric_name, val in safe_scores.items():
                    trace.score(name=metric_name, value=val)
                    
                    # 🟢 [关键修复] 名称映射：将 Ragas 的名称映射到 DB/agg_scores 的名称
                    target_key = metric_name
                    
                    if metric_name == "context_entity_recall":
                        target_key = "context_entities_recall"
                
                    if metric_name == "nv_accuracy": 
                        target_key = "answer_accuracy"

                    # 3. 只有在 agg_scores 定义了的指标才统计
                    if target_key in agg_scores:
                        agg_scores[target_key].append(val)
                    else:
                        # 方便调试，打印一下不在列表里的指标名
                        logger.debug(f"Metric {metric_name} (mapped to {target_key}) not in agg_scores, skipping.")

        # 5. 计算平均分
        def avg(lst):
            return float(sum(lst) / len(lst)) if lst else 0.0

        # 更新 DB
        # 重新获取对象
        exp = await db.get(Experiment, experiment_id)
        if exp:
            exp.faithfulness = avg(agg_scores["faithfulness"])
            exp.answer_relevancy = avg(agg_scores["answer_relevancy"])
            exp.context_recall = avg(agg_scores["context_recall"])
            exp.context_precision = avg(agg_scores["context_precision"])
            exp.answer_accuracy = avg(agg_scores["answer_accuracy"])
            exp.context_entities_recall = avg(agg_scores["context_entities_recall"])
            
            exp.status = "COMPLETED"
            db.add(exp)
            await db.commit()
            
        logger.info(f"实验 {experiment_id} 完成。")

    except Exception as e:
        logger.error(f"实验 {experiment_id} 失败: {e}", exc_info=True)
        await db.rollback()
        exp = await db.get(Experiment, experiment_id)
        if exp:
            exp.status = "FAILED"
            exp.error_message = str(e)[:500]
            db.add(exp)
            await db.commit()