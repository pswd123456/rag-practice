import logging

import nest_asyncio
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.testset import TestsetGenerator

from app.core.config import settings
from app.services.factories import setup_embed_model, setup_qwen_llm
from app.services.loader import get_prepared_docs
from evaluation.config import get_default_config

def generate_testset():
    nest_asyncio.apply()
    logger = logging.getLogger(__name__)

    config = get_default_config()
    docs = get_prepared_docs()
    embed_model = LangchainEmbeddingsWrapper(setup_embed_model("text-embedding-v4"))
    llm = LangchainLLMWrapper(setup_qwen_llm("qwen-flash"))

    # 生成测试集
    logger.info("正在生成测试集...")
    generator = TestsetGenerator(llm=llm, embedding_model=embed_model)  
    dataset = generator.generate_with_langchain_docs(docs, testset_size=config.testset_size)
    logger.info("测试集生成成功。")

    logger.info("正在保存测试集...")
    df = dataset.to_pandas()#type: ignore
    df.to_csv(settings.TESTSET_OUTPUT_PATH, index=False)

if __name__ == "__main__":
    generate_testset()
    print("测试集生成完毕")
    print(f"测试集保存在 {settings.TESTSET_OUTPUT_PATH}")