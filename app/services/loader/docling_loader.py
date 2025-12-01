"""
app/services/loader/docling_loader.py
"""
import logging
import torch
import json
import os
from typing import List, Optional
from pathlib import Path

# LangChain Document
from langchain_core.documents import Document

# Docling
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice

# Docling Chunking
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer

# Config
from app.core.config import settings, PROJECT_ROOT

logger = logging.getLogger(__name__)

class DoclingLoader:
    """
    基于 Docling 的文档加载器，支持 PDF 和 Docx。
    支持直接导出 Markdown 或使用 HybridChunker 进行语义切片。
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._converter = self._init_converter()

    def _init_converter(self) -> DocumentConverter:
        """
        初始化 Converter，配置 GPU 加速（如果可用）
        """
        # 配置 Pipeline 选项
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # 开启 OCR 以处理扫描件
        pipeline_options.do_table_structure = True # 开启表格结构提取

        # GPU 加速配置
        if torch.cuda.is_available():
            # logger.info("🚀 Docling 检测到 CUDA 环境，正在启用 GPU 加速...")
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=4, 
                device=AcceleratorDevice.CUDA
            )
        else:
            logger.warning("⚠️ 未检测到 CUDA，Docling 将使用 CPU 运行 (速度较慢)")
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=8, 
                device=AcceleratorDevice.CPU
            )

        # 绑定格式配置
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def _save_debug_files(self, doc_content, markdown_text: str):
        """
        [Debug Logic] 保存中间解析结果到项目根目录
        """
        try:
            # 1. 构造文件名
            original_stem = Path(self.file_path).stem
            # 清理文件名中的特殊字符以免路径报错
            safe_stem = "".join([c for c in original_stem if c.isalnum() or c in (' ', '-', '_')]).strip()
            
            json_filename = f"debug_docling_{safe_stem}.json"
            md_filename = f"debug_docling_{safe_stem}.md"
            
            json_path = PROJECT_ROOT / json_filename
            md_path = PROJECT_ROOT / md_filename

            logger.info(f"🐛 [Debug] 正在保存 Docling 中间文件到根目录...")

            # 2. 保存 Markdown 内容
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            
            # 3. 尝试保存 JSON
            if hasattr(doc_content, "export_to_dict"):
                doc_dict = doc_content.export_to_dict()
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(doc_dict, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"🐛 [Debug] 保存调试文件失败: {e}")

    def load(self) -> List[Document]:
        """
        (Legacy) 加载文档并转换为单一的 Markdown LangChain Document。
        适用于后续使用 RecursiveSplitter 的场景。
        """
        return self._process_doc(chunking=False)

    def load_and_chunk(self, chunk_size: int = 512, chunk_overlap: int = 50) -> List[Document]:
        """
        [New] 加载并使用 HybridChunker 进行切片。
        
        :param chunk_size: Token 限制 (HybridChunker 使用 Tokenizer 计数)
        :param chunk_overlap: 这里的 overlap HybridChunker 不一定完全遵循，它有自己的逻辑
        """
        return self._process_doc(chunking=True, max_tokens=chunk_size)

    def _process_doc(self, chunking: bool, max_tokens: int = 512) -> List[Document]:
        if not Path(self.file_path).exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        logger.info(f"开始使用 Docling 解析文件: {self.file_path} (Chunking={chunking})")
        
        try:
            # 1. 核心转换
            conversion_result = self._converter.convert(self.file_path)
            doc_content = conversion_result.document
            
            # Debug: 始终保存 Markdown 以便人工检查
            # try:
            #     markdown_text = doc_content.export_to_markdown()
            #     self._save_debug_files(doc_content, markdown_text)
            # except Exception:
            #     pass

            final_docs = []

            # 2. 分支处理
            if chunking:
                # === Hybrid Chunking 逻辑 ===
                logger.info(f"初始化 HybridChunker (Tokenizer: {settings.CHUNK_TOKENIZER_ID}, MaxTokens: {max_tokens})")
                
                # 初始化 Tokenizer (Lazily loaded usually, but here we init explicitly)
                # 注意：AutoTokenizer 需要联网下载模型配置，Worker 环境需确保网络或已缓存
                hf_tokenizer = AutoTokenizer.from_pretrained(settings.CHUNK_TOKENIZER_ID)
                tokenizer = HuggingFaceTokenizer(
                    tokenizer=hf_tokenizer, 
                    max_tokens=max_tokens # <--- 这里必须传，通常是 512
                )
                
                chunker = HybridChunker(
                    tokenizer=tokenizer,
                    max_tokens=max_tokens,
                    merge_peers=True
                )
                
                chunk_iter = chunker.chunk(dl_doc=doc_content)
                
                for i, chunk in enumerate(chunk_iter):
                    # 获取增强后的上下文文本 (包含标题层级等)
                    enriched_text = chunker.contextualize(chunk=chunk)
                    
                    metadata = {
                        "source": str(self.file_path),
                        "filename": Path(self.file_path).name,
                        "chunk_index": i,
                        # 尝试从 Docling 元数据中提取页码等信息 (可能分布在 prov items 中)
                        "doc_items": [str(item) for item in chunk.meta.doc_items] if hasattr(chunk.meta, "doc_items") else [],
                        "headings": chunk.meta.headings if hasattr(chunk.meta, "headings") else []
                    }
                    
                    final_docs.append(Document(page_content=enriched_text, metadata=metadata))
                
                logger.info(f"HybridChunker 生成了 {len(final_docs)} 个切片。")
                
            else:
                # === Legacy Logic: 全文 Markdown ===
                metadata = {
                    "source": str(self.file_path),
                    "filename": Path(self.file_path).name,
                    "page_count": len(doc_content.pages) if hasattr(doc_content, "pages") else 0,
                }
                final_docs = [Document(page_content=markdown_text, metadata=metadata)]

            return final_docs

        except Exception as e:
            logger.error(f"Docling 解析/切片失败: {e}", exc_info=True)
            raise e

# 适配函数 (Updated)
def load_and_chunk_docling_document(file_path: str, chunk_size: int = 512) -> List[Document]:
    loader = DoclingLoader(file_path)
    return loader.load_and_chunk(chunk_size=chunk_size)

def load_docling_document(file_path: str) -> List[Document]:
    loader = DoclingLoader(file_path)
    return loader.load()