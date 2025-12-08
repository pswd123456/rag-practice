import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import uuid

# ==========================================
# Unit Tests for Parent-Child Logic
# ==========================================

def test_ingestion_parent_child_splitting():
    """
    [Unit] 测试 Ingestion 阶段的父子切分逻辑
    验证:
    1. 父文档被切分为多个子文档
    2. 子文档 Metadata 包含 parent_id, parent_content, doc_id
    """
    # 1. 模拟一个较长的父文档 (Docling Output)
    parent_text = "Section 1: Introduction. " * 20 + "\n\n" + "Section 2: Details. " * 20
    parent_doc = Document(
        page_content=parent_text,
        metadata={"source": "test.pdf", "page": 1}
    )
    
    # 2. 模拟切分逻辑 (Replica of ingest.py logic)
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=100,
        chunk_overlap=0,
        separators=["\n\n", " "]
    )
    
    final_docs = []
    
    # Logic to be implemented in ingest.py
    parent_id = str(uuid.uuid4())
    parent_content = parent_doc.page_content
    
    child_chunks = child_splitter.split_documents([parent_doc])
    
    for c_doc in child_chunks:
        c_doc.metadata.update(parent_doc.metadata)
        c_doc.metadata["doc_id"] = str(uuid.uuid4())
        c_doc.metadata["parent_id"] = parent_id
        c_doc.metadata["parent_content"] = parent_content
        final_docs.append(c_doc)
        
    # 3. Assertions
    assert len(final_docs) > 1, "Should generate multiple children"
    
    first_child = final_docs[0]
    assert "parent_id" in first_child.metadata
    assert first_child.metadata["parent_id"] == parent_id
    assert first_child.metadata["parent_content"] == parent_text
    assert first_child.page_content != parent_text # Child content should be smaller
    assert len(first_child.page_content) <= 100

def test_retrieval_collapse_logic():
    """
    [Unit] 测试 Retrieval 阶段的 'Collapse' (折叠) 逻辑
    验证:
    1. 多个属于同一 Parent 的 Child 文档被去重
    2. 返回的文档内容被替换为 Parent Content
    3. 顺序保留 (基于最高分 Child)
    """
    # 1. Prepare Mock Data (SearchResults)
    # Parent A has 2 children in results
    parent_a_id = "parent_a"
    parent_a_content = "Full Content A"
    
    # Parent B has 1 child in results
    parent_b_id = "parent_b"
    parent_b_content = "Full Content B"
    
    # Order: Child A1 (0.9), Child B1 (0.8), Child A2 (0.7)
    # Expected Result: Parent A (0.9), Parent B (0.8) -> A2 is collapsed into A
    
    docs = [
        Document(
            page_content="Child A1", 
            metadata={"parent_id": parent_a_id, "parent_content": parent_a_content, "score": 0.9}
        ),
        Document(
            page_content="Child B1", 
            metadata={"parent_id": parent_b_id, "parent_content": parent_b_content, "score": 0.8}
        ),
        Document(
            page_content="Child A2", 
            metadata={"parent_id": parent_a_id, "parent_content": parent_a_content, "score": 0.7}
        )
    ]
    
    # 2. Execute Logic (Replica of hybrid_retriever.py logic)
    seen_parent_ids = set()
    unique_parent_docs = []
    
    for doc in docs:
        p_id = doc.metadata.get("parent_id")
        p_content = doc.metadata.get("parent_content")
        
        if not p_id:
            unique_parent_docs.append(doc)
            continue
            
        if p_id in seen_parent_ids:
            continue
            
        seen_parent_ids.add(p_id)
        
        new_doc = Document(
            page_content=p_content,
            metadata=doc.metadata
        )
        # Cleanup to save memory
        new_doc.metadata.pop("parent_content", None)
        unique_parent_docs.append(new_doc)
        
    # 3. Assertions
    assert len(unique_parent_docs) == 2
    assert unique_parent_docs[0].page_content == parent_a_content
    assert unique_parent_docs[0].metadata["parent_id"] == parent_a_id
    assert unique_parent_docs[1].page_content == parent_b_content