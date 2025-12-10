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
from docling.datamodel.pipeline_options import PdfPipelineOptions, PictureDescriptionVlmOptions
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

        local_models_path = settings.DOCLING_MODELS_PATH

        # 配置 Pipeline 选项
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # 开启 OCR 以处理扫描件
        pipeline_options.do_table_structure = True # 开启表格结构提取
        pipeline_options.do_formula_enrichment = True
        pipeline_options.do_picture_description = True 
        # 图片描述用的默认的256M的SmolVLM, 一言难尽, 由于机器性能限制只能用这个, 后续可以自己换一下
        pipeline_options.picture_description_options = PictureDescriptionVlmOptions(
            repo_id="HuggingFaceTB/SmolVLM-256M-Instruct",
            
            #"Describe this image in a few sentences."
            prompt="Briefly describe the main subject of this image. If it is a chart, explain what it shows."
        )

        pipeline_options.images_scale = 2.0
        pipeline_options.artifacts_path = local_models_path

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
                num_threads=4, 
                device=AcceleratorDevice.CPU
            )

        # 绑定格式配置
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def load(self) -> List[Document]:
        """
        加载文档并转换为单一的 Markdown LangChain Document。
        """
        return self._process_doc(chunking=False)

    def load_and_chunk(self, chunk_size: int = 512, chunk_overlap: int = 50) -> List[Document]:
        """
        加载并使用 HybridChunker 进行切片。
        
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
            
            final_docs = []

            # 2. 分支处理
            if chunking:
                # === Hybrid Chunking 逻辑 ===
                logger.info(f"初始化 HybridChunker (Tokenizer: {settings.CHUNK_TOKENIZER_ID}, MaxTokens: {max_tokens})")
                
                # 初始化 Tokenizer
                hf_tokenizer = AutoTokenizer.from_pretrained(settings.CHUNK_TOKENIZER_ID)
                tokenizer = HuggingFaceTokenizer(
                    tokenizer=hf_tokenizer, 
                    max_tokens=max_tokens
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
                
                    page_numbers = set()
                    
                    # 获取 doc_items
                    doc_items = getattr(chunk.meta, "doc_items", []) or []

                    for item in doc_items:
                        provs = []
                        if hasattr(item, "prov"):
                            provs = item.prov
                        elif isinstance(item, dict) and "prov" in item:
                            provs = item["prov"]
                        
                        if not provs:
                            continue
                        
                        for prov in provs:
                            p_no = None
                            if hasattr(prov, "page_no"):
                                p_no = prov.page_no
                            elif isinstance(prov, dict) and "page_no" in prov:
                                p_no = prov["page_no"]

                            if p_no is not None:
                                page_numbers.add(p_no)
                    # ---------------------------------

                    # 排序并生成最终列表
                    sorted_pages = sorted(list(page_numbers))
                    
                    metadata = {
                        "source": str(self.file_path),
                        "filename": Path(self.file_path).name,
                        "chunk_index": i,
                        "headings": chunk.meta.headings if hasattr(chunk.meta, "headings") else [],
                        "page_numbers": sorted_pages, # ✅ 页码依然保留
                        "page_number": sorted_pages[0] if sorted_pages else None 
                    }
                    
                    final_docs.append(Document(page_content=enriched_text, metadata=metadata))
                
                logger.info(f"HybridChunker 生成了 {len(final_docs)} 个切片。")
                
            else:
                # === 全文 Markdown ===
                # 这段目前应该是不工作的状态
                markdown_text = doc_content.export_to_markdown()
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

# 适配函数
def load_and_chunk_docling_document(file_path: str, chunk_size: int = 512) -> List[Document]:
    loader = DoclingLoader(file_path)
    return loader.load_and_chunk(chunk_size=chunk_size)

def load_docling_document(file_path: str) -> List[Document]:
    loader = DoclingLoader(file_path)
    return loader.load()