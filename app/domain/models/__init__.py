# 按照依赖顺序导入：Knowledge -> Document -> Chunk
from .knowledge import Knowledge, KnowledgeCreate, KnowledgeRead, KnowledgeUpdate, KnowledgeStatus
from .document import Document, DocStatus
from .chunk import Chunk

# 导出给外部使用
__all__ = [
    "Knowledge", "KnowledgeCreate", "KnowledgeRead", "KnowledgeUpdate" , "KnowledgeStatus",
    "Document", "DocStatus",
    "Chunk"
]