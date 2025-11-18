from app.core.config import settings
from app.services.factories.llm_factory import setup_qwen_llm
from app.services.ingest.loader import get_prepared_docs
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from app.services.factories.embedding_factory import setup_hf_embed_model
from ragas.testset import TestsetGenerator
import nest_asyncio
import logging

def generate_testset():
    nest_asyncio.apply()
    logger = logging.getLogger(__name__)

    docs = get_prepared_docs()
    embed_model = LangchainEmbeddingsWrapper(setup_hf_embed_model("Qwen3-Embedding-0.6B"))
    llm = LangchainLLMWrapper(setup_qwen_llm("qwen-flash"))

    # 生成测试集
    logger.info("正在生成测试集...")
    generator = TestsetGenerator(llm=llm, embedding_model=embed_model)  
    dataset = generator.generate_with_langchain_docs(docs, testset_size=settings.TESTSET_SIZE)
    logger.info("测试集生成成功。")

    logger.info("正在保存测试集...")
    df = dataset.to_pandas()#type: ignore
    df.to_csv(settings.TESTSET_OUTPUT_PATH, index=False)

if __name__ == "__main__":
    generate_testset()
    print("测试集生成完毕")
    print(f"测试集保存在 {settings.TESTSET_OUTPUT_PATH}")