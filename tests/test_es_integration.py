# tests/test_es_integration.py
import pytest
from langchain_core.documents import Document
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.core.config import settings

# 本地定义的 FakeEmbeddings
class LocalFakeEmbeddings:
    def embed_documents(self, texts):
        return [[0.1] * settings.EMBEDDING_DIM for _ in texts]
    def embed_query(self, text):
        return [0.1] * settings.EMBEDDING_DIM

@pytest.mark.asyncio
class TestESIntegration:
    
    def test_analyzer_ik(self, es_client):
        """验证 IK 分词器"""
        text = "数据库配置管理"
        try:
            response = es_client.indices.analyze(
                body={"analyzer": "ik_max_word", "text": text}
            )
        except Exception as e:
            pytest.fail(f"分词测试失败，请检查 analysis-ik 插件是否安装: {e}")

        tokens = [t["token"] for t in response["tokens"]]
        print(f"\n[分词结果] '{text}' -> {tokens}")
        assert "数据库" in tokens
        assert "配置" in tokens

    def test_hybrid_search_effectiveness(self, es_client, clean_es_index):
        """验证混合检索"""
        collection_name = "kb_test_hybrid"
        embed_model = LocalFakeEmbeddings()
        
        manager = VectorStoreManager(collection_name, embed_model)
        manager.ensure_index()
        store = manager.get_vector_store()
        
        docs = [
            Document(page_content="MySQL port is 3306", metadata={"knowledge_id": 999, "id": 1}),
            Document(page_content="Redis is a KV store", metadata={"knowledge_id": 999, "id": 2}),
            Document(page_content="生产环境禁止root登录", metadata={"knowledge_id": 999, "id": 3})
        ]
        
        store.add_documents(docs)
        es_client.indices.refresh(index=manager.index_name)

        from app.services.factories.retrieval_factory import RetrievalFactory
        
        # [Fix] 将 top_k 设为 3，确保 RRF 有足够的候选进行加权排序
        # 因为向量全是相同的，我们需要让目标文档出现在向量召回列表中(即使排名靠后)，
        # 这样它的 Keyword 分数 + Vector 分数 才能超过其他噪音文档。
        retriever = RetrievalFactory.create_retriever(
            manager, strategy="hybrid", top_k=3, knowledge_id=999
        )
        
        # Case 1: 关键词 "3306"
        results_1 = retriever.invoke("3306")
        assert len(results_1) > 0
        assert "3306" in results_1[0].page_content

        # Case 2: 中文关键词 "root"
        results_2 = retriever.invoke("root")
        assert len(results_2) > 0
        
        # [Fix] 此时 Root 应该稳居第一
        assert "root" in results_2[0].page_content

    @pytest.mark.asyncio
    async def test_es_retriever_filter_structure(self, es_client, clean_es_index):
        """
        [验证修复] 测试 dense 和 hybrid 检索在带 filter 时是否报错
        """
        # 1. 初始化 Manager 和数据
        from app.services.retrieval.vector_store_manager import VectorStoreManager
        from app.services.factories.retrieval_factory import RetrievalFactory
        from tests.conftest import FakeEmbeddings
        
        manager = VectorStoreManager("filter_test", FakeEmbeddings())
        
        # 🟢 [关键修复] 显式强制删除索引，防止上次测试残留的 Dirty Data
        # 即使 clean_es_index fixture 失效，这里也能保证环境纯净
        manager.delete_index()
        
        manager.ensure_index()
        store = manager.get_vector_store()
        
        # 写入带有不同 knowledge_id 的文档
        docs = [
            Document(page_content="Target Doc", metadata={"knowledge_id": 100}),
            Document(page_content="Noise Doc", metadata={"knowledge_id": 200})
        ]
        store.add_documents(docs)
        # 强制刷新，确保数据立即可查
        es_client.indices.refresh(index=manager.index_name)

        # 2. 测试 Hybrid Retriever
        hybrid_retriever = RetrievalFactory.create_retriever(
            manager, strategy="hybrid", knowledge_id=100
        )
        results = hybrid_retriever.invoke("Doc")
        
        # 断言：应该只找到 ID=100 的文档，且只有一份
        assert len(results) == 1
        assert results[0].metadata["knowledge_id"] == 100