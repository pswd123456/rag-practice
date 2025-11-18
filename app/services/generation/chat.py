import app.services.factories.embedding_factory as util
import app.services.ingest.ingest as ingest
import app.services.factories.llm_factory as llm_factory
from app.core.config import settings
from app.services.pipelines.pipeline import RAGPipeline
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)
@lru_cache(maxsize=1)
def run_rag_chain():
    try:
        # (这部分逻辑和你 main.py 的 setup 部分完全一致)
        embed_model = util.setup_hf_embed_model("Qwen3-Embedding-0.6B")
        llm = llm_factory.setup_qwen_llm("qwen-flash")

        vector_store = ingest.build_or_get_vector_store(
            settings.CHROMADB_COLLECTION_NAME,
            embed_model=embed_model
        )

        retriever = vector_store.as_retriever(search_kwargs={"k": settings.TOP_K})

        pipeline = RAGPipeline(llm=llm, retriever=retriever)
        # rag_chain = pipeline.get_rag_chain()

        logger.info("模型和 RAG 管道加载成功，API 已就绪。")

    except Exception as e:
        logger.critical(f"API 启动失败，加载模型出错: {e}", exc_info=True)
        # 在实际生产中，你可能希望让应用在这里失败退出
        # rag_chain = None

    return pipeline