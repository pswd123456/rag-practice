import logging
import torch
from typing import List, Optional
from pathlib import Path

# LangChain Document
from langchain_core.documents import Document

# Docling
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice

logger = logging.getLogger(__name__)

class DoclingLoader:
    """
    基于 Docling 的文档加载器，支持 PDF 和 Docx。
    输出格式为结构化的 Markdown。
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
            logger.info("🚀 Docling 检测到 CUDA 环境，正在启用 GPU 加速...")
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

    def load(self) -> List[Document]:
        """
        加载文档并转换为 LangChain Document 对象列表。
        目前 Docling 通常将整个文档转换为一个完整的 Markdown，
        这里我们将其封装为一个 Document，后续由 Splitter 进行切分。
        """
        if not Path(self.file_path).exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        logger.info(f"开始使用 Docling 解析文件: {self.file_path}")
        
        try:
            # 核心转换逻辑
            conversion_result = self._converter.convert(self.file_path)
            doc_content = conversion_result.document
            
            # 导出为 Markdown
            markdown_text = doc_content.export_to_markdown()
            
            # 提取元数据
            # Docling 的元数据可能比较分散，我们取一些基础的
            metadata = {
                "source": str(self.file_path),
                "filename": Path(self.file_path).name,
                "page_count": len(doc_content.pages) if hasattr(doc_content, "pages") else 0,
                # 可以在这里添加更多 Docling 特有的元数据，如表格数量等
            }

            logger.info(f"Docling 解析完成，生成 Markdown 长度: {len(markdown_text)}")
            
            return [Document(page_content=markdown_text, metadata=metadata)]

        except Exception as e:
            logger.error(f"Docling 解析失败: {e}", exc_info=True)
            raise e

# 适配旧有 loader.py 的接口风格
def load_docling_document(file_path: str) -> List[Document]:
    loader = DoclingLoader(file_path)
    return loader.load()