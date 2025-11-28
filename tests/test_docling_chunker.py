"""
tests/test_docling_chunker.py
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document as LCDocument
from app.services.loader.docling_loader import DoclingLoader

@pytest.fixture
def mock_docling_components():
    # 🟢 [Fix] Mock Path.exists 以避开文件存在性检查
    with patch("pathlib.Path.exists", return_value=True), \
         patch("app.services.loader.docling_loader.DocumentConverter") as MockConverter, \
         patch("app.services.loader.docling_loader.HybridChunker") as MockChunker, \
         patch("app.services.loader.docling_loader.HuggingFaceTokenizer") as MockTokenizer, \
         patch("app.services.loader.docling_loader.AutoTokenizer") as MockAutoTokenizer:
        
        # 1. Mock Converter Result
        mock_dl_doc = MagicMock()
        mock_result = MagicMock()
        mock_result.document = mock_dl_doc
        
        mock_converter_instance = MockConverter.return_value
        mock_converter_instance.convert.return_value = mock_result
        
        # 2. Mock Chunker Result
        mock_chunker_instance = MockChunker.return_value
        
        # 模拟 2 个 chunks
        chunk1 = MagicMock()
        # chunk.text 是原始文本
        chunk1.text = "Chunk 1 raw text" 
        chunk1.meta.headings = ["Header 1"]
        
        chunk2 = MagicMock()
        chunk2.text = "Chunk 2 raw text"
        chunk2.meta.headings = ["Header 1", "Subheader 2"]

        # chunk 方法返回迭代器或列表
        mock_chunker_instance.chunk.return_value = [chunk1, chunk2]
        
        # 模拟 contextualize (HybridChunker 的核心，返回增强后的文本)
        mock_chunker_instance.contextualize.side_effect = [
            "Header 1\nChunk 1 raw text", 
            "Header 1 > Subheader 2\nChunk 2 raw text"
        ]

        yield MockConverter, MockChunker, mock_dl_doc

def test_docling_load_and_chunk(mock_docling_components):
    """
    [Unit] 测试 DoclingLoader.load_and_chunk 方法
    """
    MockConverter, MockChunker, mock_dl_doc = mock_docling_components
    
    # 传入虚拟路径，因为 Path.exists 已经被 Mock 为 True，所以不会报错
    loader = DoclingLoader("test.pdf")
    
    # 调用新方法
    docs = loader.load_and_chunk(chunk_size=500, chunk_overlap=50)
    
    # === 验证 ===
    assert len(docs) == 2
    assert isinstance(docs[0], LCDocument)
    
    # 验证内容是否是 Contextualized 之后的文本
    assert "Header 1" in docs[0].page_content
    assert "Subheader 2" in docs[1].page_content
    
    # 验证 Metadata
    assert docs[0].metadata["source"] == "test.pdf"
    assert docs[0].metadata["filename"] == "test.pdf"
    assert docs[0].metadata["chunk_index"] == 0
    
    # 验证 HybridChunker 初始化逻辑
    MockChunker.assert_called_once()
    
    # 验证 Converter 调用
    MockConverter.return_value.convert.assert_called_with("test.pdf")