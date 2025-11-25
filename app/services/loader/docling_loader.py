import logging
import torch
from typing import List, Optional
from pathlib import Path

# LangChain Document
from langchain_core.documents import Document

# Docling
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
# [修改] 引入 TableStructureOptions
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, TesseractOcrOptions
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice 
from docling.datamodel.pipeline_options import TableFormerMode
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
        初始化 Converter，配置 GPU 加速与增强表格识别
        """
        # 配置 Pipeline 选项
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # 开启 OCR
        pipeline_options.do_table_structure = True # 开启表格结构提取
        
        pipeline_options.ocr_options = TesseractOcrOptions(
            lang=["chi_sim", "eng"]
        )
        
        # 增强表格配置
        # do_cell_matching: 强制进行单元格匹配，解决合并单元格错位问题
        pipeline_options.table_structure_options = TableStructureOptions(
            do_cell_matching=True,             # 强力匹配单元格
            mode=TableFormerMode.ACCURATE      # [关键] 使用高精度模式 (ACCURATE) 而不是 FAST
        )
        # 提高渲染分辨率 (默认约 72 DPI，提高到 2.0 倍约 144 DPI)
        # 这有助于识别密集的表格线，但会增加显存消耗
        pipeline_options.images_scale = 3.0

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

            # =============== 🐛 DEBUG START ===============
            # 既然是开发环境，直接把它写到根目录方便查看
            # 文件名带上时间戳或随机数防止覆盖，或者干脆固定名字方便反复刷
            debug_filename = f"debug_docling_output_{Path(self.file_path).name}.md"
            
            # 获取项目根目录 (假设容器内 workdir 是 /app)
            # 也可以直接写相对路径，因为 worker 启动时的 cwd 就是 /app
            with open(debug_filename, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            
            logger.info(f"🐛 [DEBUG] Markdown 已保存至根目录: {debug_filename}")
            # =============== 🐛 DEBUG END =================
            
            # [新增] 统计表格数量用于 Debug
            table_count = len([item for item in doc_content.tables])
            logger.info(f"📊 文档中检测到的表格数量: {table_count}")
            
            # 提取元数据
            metadata = {
                "source": str(self.file_path),
                "filename": Path(self.file_path).name,
                "page_count": len(doc_content.pages) if hasattr(doc_content, "pages") else 0,
                "table_count": table_count, # 记录表格数
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