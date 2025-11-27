import logging
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader, TextLoader, Docx2txtLoader

from pathlib import Path
from typing import Iterable, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)
def get_text_splitter(chunk_size: int, chunk_overlap: int):
    """
    配置并返回文本分割器实例。

    :return: RecursiveCharacterTextSplitter 实例
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size = chunk_size,     # 每个块的最大长度
        chunk_overlap  = chunk_overlap,  # 块之间的重叠长度，有助于上下文连续性
        add_start_index = True # 在元数据中添加块的起始索引
    )
    
    return text_splitter

def split_docs(docs: Iterable[Document], chunk_size: int, chunk_overlap: int) -> List[Document]:
    """
    对 Document 进行分块。
    """
    splitter = get_text_splitter(chunk_size, chunk_overlap)
    splitted_docs = splitter.split_documents(list(docs))
    logger.info(f"文档分割完成 (Size={chunk_size}, Overlap={chunk_overlap})，共 {len(splitted_docs)} 个块。")
    return splitted_docs

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
    # md 将视为普通文本处理
    elif path_obj.suffix.lower() in [".txt", ".md"]:
        loader = TextLoader(str(path_obj), encoding="utf-8")

    elif path_obj.suffix == ".docx":
        loader = Docx2txtLoader(str(path_obj))
        
    else:
        raise ValueError(f"不支持的文件类型: {path_obj.suffix}")
    
    return loader.load()


