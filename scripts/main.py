# -*- coding: utf-8 -*-
"""
RAG 应用主入口 (main.py)

负责：
1. 配置全局日志 (通过 logging_config.py 加载)
2. 初始化向量数据库 (执行数据摄取)
3. 创建 RAG 链
4. 运行用户交互式查询循环
"""
from app.core.config import settings
import app.services.llm.llm_factory
from app.services.pipeline import RAGPipeline   
import app.services.embedding.embedding_factory as util
import app.services.ingest as ingest
import logging
import logging.config # 1. 导入 logging.config
import sys
import os
from app.core.logging_setup import get_logging_config
import warnings

warnings.filterwarnings(
    "ignore", 
    message=".*Torch was not compiled with flash attention.*"
)
# --- 2. 配置全局日志 (从配置加载) ---

# 确保 'logs' 文件夹存在 (这行代码来自原文件)
os.makedirs(settings.LOG_DIR, exist_ok=True) 

# 3. 获取配置字典
# 我们将 Path 对象转换为字符串，因为配置需要它
logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))

# 4. 应用日志配置
logging.config.dictConfig(logging_config_dict)

# --- (原始 main.py 的所有手动配置代码已删除) ---

# --- 配置完成 ---

# 获取 'main' 模块的 logger (它会正确继承 root 配置)
logger = logging.getLogger(__name__)

def main():
    """
    主执行函数
    """
    logger.info("===================")
    logger.info(f"应用启动... 日志将保存到: {settings.LOG_FILE_PATH}")
    logger.info("===================")
    
    collection_name = settings.CHROMADB_COLLECTION_NAME

    try:

        logger.info("开始初始化 LLM 和向量模型...")
        embed_model = util.setup_hf_embed_model("Qwen3-Embedding-0.6B")
        llm = app.services.llm.llm_factory.setup_qwen_llm("qwen-flash")
        
        logger.info("开始构建/加载向量数据库...")
        vector_store = ingest.build_or_get_vector_store(collection_name, embed_model)
        logger.info("向量数据库构建/加载完成。")
        
        retriever = vector_store.as_retriever(search_kwargs={"k": settings.TOP_K})

        logger.info("开始创建 RAG 链...")
        pipeline = RAGPipeline(llm=llm, retriever=retriever)
        rag_chain = pipeline.get_rag_chain()
        logger.info("RAG 链已就绪。")

        print("\n" + "="*30)
        print("🤖 链已就绪，请输入问题 (输入 'exit' 或 'quit' 退出):")
        print("="*30 + "\n")
        
        while True:
            try:
                query = input("👤 > ")
                if query.lower() in ["exit", "quit"]:
                    logger.info("收到退出命令，程序即将关闭。")
                    break
                    
                logger.info(f"收到用户查询: {query}")
                logger.debug("正在调用 RAG 链 (invoke)...")
                response = rag_chain.invoke(query)
                logger.debug("RAG 链调用完成。")
                
                print(f"\n🤖 助手:\n{response}\n")
                
            except KeyboardInterrupt:
                logger.info("检测到 KeyboardInterrupt (Ctrl+C)，正在退出...")
                break
            except Exception as e:
                logger.error(f"查询处理时发生未知错误: {e}", exc_info=True)

    except Exception as e:
        logger.critical(f"应用启动失败: {e}", exc_info=True)
        print(f"应用启动失败，请检查日志获取详细信息。错误: {e}")
        sys.exit(1)

    logger.info("===================")
    logger.info("应用已关闭。")
    logger.info("===================")

if __name__ == "__main__":
    main()