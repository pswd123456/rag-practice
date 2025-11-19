import logging
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader

from pathlib import Path
from typing import Iterable, List

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

def load_raw_docs() -> List[Document]:
    """
    从配置的目录或文件加载原始 Document。
    """
    loader = create_document_loader()
    docs = loader.load()
    logger.info("原始文档加载完成，共 %s 条。", len(docs))
    return docs


def normalize_metadata(docs: Iterable[Document]) -> List[Document]:
    """
    标准化 Document metadata，确保包含 `source` 字段。
    """
    normalized: List[Document] = []
    for doc in docs:
        metadata = dict(doc.metadata or {})
        metadata.setdefault("source", metadata.get("source", str(settings.SOURCH_FILE_DIR)))
        normalized.append(Document(page_content=doc.page_content, metadata=metadata))
    logger.debug("元数据标准化完成。")
    return normalized


def split_docs(docs: Iterable[Document]) -> List[Document]:
    """
    对 Document 进行分块。
    """
    splitter = get_text_splitter()
    splitted_docs = splitter.split_documents(list(docs))
    logger.info("文档分割完成，共 %s 个块。", len(splitted_docs))
    return splitted_docs


def get_prepared_docs() -> List[Document]:
    """
    加载、清洗并分割文档。
    """
    logger.info("开始加载和分割源文档...")
    raw_docs = load_raw_docs()
    normalized_docs = normalize_metadata(raw_docs)
    return split_docs(normalized_docs)

def load_single_document(file_path: str) -> List[Document]:
    """
    从单个文件加载 PDF或者文件
    暂时只支持 PDF
    """
    path_obj = Path(file_path)
    if not path_obj.exists():
        logger.error(f"文件不存在: {file_path}")
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    logger.debug(f"正在从 {file_path} 加载文件...")

    if path_obj.suffix == ".pdf":
        loader = PyPDFLoader(str(path_obj))
    else:
        raise ValueError(f"不支持的文件类型: {path_obj.suffix}")
    
    return loader.load()


