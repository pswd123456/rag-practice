import logging
import torch
import json
import os
from typing import List
from pathlib import Path

# LangChain Document
from langchain_core.documents import Document

# Docling
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice

# Config
from app.core.config import settings, PROJECT_ROOT  # 确保引用了 PROJECT_ROOT

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

            # 2. 保存层级结构 JSON (Hierarchical Structure)
            # DoclingDocument 对象通常提供 export_to_dict() 方法
            if hasattr(doc_content, "export_to_dict"):
                doc_dict = doc_content.export_to_dict()
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(doc_dict, f, ensure_ascii=False, indent=2)
                logger.info(f"   -> JSON Structure: {json_path}")
            else:
                logger.warning("   -> 该 Docling 版本不支持 export_to_dict，跳过 JSON 保存。")

            # 3. 保存 Markdown 内容
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            logger.info(f"   -> Markdown Content: {md_path}")

        except Exception as e:
            logger.error(f"🐛 [Debug] 保存调试文件失败: {e}", exc_info=True)

    def load(self) -> List[Document]:
        """
        加载文档并转换为 LangChain Document 对象列表。
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

            # ==========================================
            # 🛠️ 插入 Debug 逻辑
            # ==========================================
            self._save_debug_files(doc_content, markdown_text)
            # ==========================================
            
            # 提取元数据
            metadata = {
                "source": str(self.file_path),
                "filename": Path(self.file_path).name,
                "page_count": len(doc_content.pages) if hasattr(doc_content, "pages") else 0,
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