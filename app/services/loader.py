import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)
def create_document_loader():

    logger.debug
    
    if not settings.SOURCH_FILE_DIR.exists():
        logger.error(f"数据文件未找到: {settings.SOURCH_FILE_DIR}")
        raise FileNotFoundError(f"数据文件 {settings.SOURCH_FILE_DIR} 不存在")

    if Path(settings.SOURCH_FILE_DIR).is_dir():
        loader = DirectoryLoader(str(settings.SOURCH_FILE_DIR))
        logger.debug(f"正在从 {settings.SOURCH_FILE_DIR} 加载目录...")
    
    elif settings.SOURCH_FILE_DIR.suffix == ".pdf":
        loader = PyPDFLoader(str(settings.SOURCH_FILE_DIR))
        logger.debug(f"正在从 {settings.SOURCH_FILE_DIR} 加载 PDF...")

    else:
        logger.error(f"不支持的文件类型: {settings.SOURCH_FILE_DIR.suffix}")
        raise ValueError(f"不支持的文件类型: {settings.SOURCH_FILE_DIR.suffix}")
    
    return loader


def get_text_splitter():
    """
    配置并返回文本分割器实例。

    :return: RecursiveCharacterTextSplitter 实例
    """
    logger.debug("正在设置文本分割器...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size = settings.CHUNK_SIZE,     # 每个块的最大长度
        chunk_overlap  = settings.CHUNK_OVERLAP,  # 块之间的重叠长度，有助于上下文连续性
        add_start_index = True # 在元数据中添加块的起始索引
    )
    logger.debug(f"文本分割器设置完成 (Chunk size: {settings.CHUNK_SIZE}, Overlap: {settings.CHUNK_OVERLAP})。")
    return text_splitter

def get_prepared_docs():
    """
    加载并分割 PDF 文档。

    :return: 分割后的文档列表 (List[Document])
    """
    logger.info("开始加载和分割源文档...")

    # 1. 加载 PDF
    loader = create_document_loader()

    logger.info(f"正在从 {settings.SOURCH_FILE_DIR} 加载文档...")
    docs = loader.load()
    logger.info(f"原始 PDF 加载了 {len(docs)} 页。")

    # 2. 分割文档
    splitter = get_text_splitter()
    splitted_docs = splitter.split_documents(docs)

    logger.info(f"文档分割完成。共 {len(splitted_docs)} 个文档块 (chunks)。")
    return splitted_docs