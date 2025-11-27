import pytest
from langchain_core.documents import Document
from app.services.retrieval.vector_store_manager import VectorStoreManager
from app.core.config import settings

# [Fix] 手动定义 FakeEmbeddings，不依赖 conftest 的 patch，确保测试独立性
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
        # 1. 准备
        collection_name = "kb_test_hybrid"
        
        # [Fix] 使用本地定义的 FakeEmbeddings，确保绝对不会是 MagicMock
        embed_model = LocalFakeEmbeddings()
        
        manager = VectorStoreManager(collection_name, embed_model)
        manager.ensure_index()
        store = manager.get_vector_store()
        
        docs = [
            Document(page_content="MySQL port is 3306", metadata={"knowledge_id": 999, "id": 1}),
            Document(page_content="Redis is a KV store", metadata={"knowledge_id": 999, "id": 2}),
            Document(page_content="生产环境禁止root登录", metadata={"knowledge_id": 999, "id": 3})
        ]
        
        # 2. 写入
        store.add_documents(docs)
        es_client.indices.refresh(index=manager.index_name)

        # 3. 检索
        from app.services.factories.retrieval_factory import RetrievalFactory
        retriever = RetrievalFactory.create_retriever(
            manager, strategy="hybrid", top_k=1, knowledge_id=999
        )
        
        # Case 1: 关键词 "3306"
        results_1 = retriever.invoke("3306")
        assert len(results_1) > 0
        assert "3306" in results_1[0].page_content

        # Case 2: 中文关键词 "root"
        results_2 = retriever.invoke("root")
        assert len(results_2) > 0
        assert "root" in results_2[0].page_content