import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.evaluation.evaluation_runner import RAGEvaluator
from app.services.evaluation.evaluation_config import EvaluationConfig
from app.services.pipelines.rag_pipeline import RAGPipeline

# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def mock_pipeline():
    """Mock RAG Pipeline"""
    return MagicMock(spec=RAGPipeline)

@pytest.fixture
def mock_llm_and_embed():
    """Mock LLM and Embedding models"""
    llm = MagicMock()
    embed = MagicMock()
    return llm, embed

# ==========================================
# Tests
# ==========================================

def test_ragas_metrics_loading(mock_pipeline, mock_llm_and_embed):
    """
    [Unit] 验证是否根据 Config 加载了指定的 Ragas 指标
    """
    llm, embed = mock_llm_and_embed
    
    # 1. 自定义配置：只加载 Faithfulness 和 ContextRecall
    config = EvaluationConfig(metrics=("faithfulness", "context_recall"))
    
    # 2. 初始化评估器 (Mock Ragas 类以避免真实初始化)
    with patch("app.services.evaluation.evaluation_runner.Faithfulness") as MockFaith, \
         patch("app.services.evaluation.evaluation_runner.ContextRecall") as MockRecall, \
         patch("app.services.evaluation.evaluation_runner.LangchainLLMWrapper"), \
         patch("app.services.evaluation.evaluation_runner.LangchainEmbeddingsWrapper"):
        
        evaluator = RAGEvaluator(mock_pipeline, llm, embed, config)
        
        # 3. 验证指标列表长度和内容
        assert len(evaluator.metrics) == 2
        assert MockFaith.called
        assert MockRecall.called
        
        # 确保 metrics 列表中包含的是我们 Mock 的实例
        assert evaluator.metrics[0] == MockFaith.return_value
        assert evaluator.metrics[1] == MockRecall.return_value

@pytest.mark.asyncio
async def test_score_single_item_flow(mock_pipeline, mock_llm_and_embed):
    """
    [Unit] 测试 score_single_item 流程：
    模拟 Ragas 指标计算返回分数，验证最终结果字典结构。
    """
    llm, embed = mock_llm_and_embed
    
    # 1. 准备 Mock Metrics
    # 模拟 Faithfulness 指标
    mock_metric_1 = MagicMock()
    mock_metric_1.name = "faithfulness"
    # 模拟异步评分方法 single_turn_ascore
    mock_metric_1.single_turn_ascore = AsyncMock(return_value=0.95)
    
    # 模拟 Context Precision 指标
    mock_metric_2 = MagicMock()
    mock_metric_2.name = "context_precision"
    mock_metric_2.single_turn_ascore = AsyncMock(return_value=0.88)

    # 2. 初始化 Evaluator 并注入 Mock Metrics
    # 这里我们绕过 __init__ 中的 _build_metrics 逻辑，直接手动注入
    with patch("app.services.evaluation.evaluation_runner.LangchainLLMWrapper"), \
         patch("app.services.evaluation.evaluation_runner.LangchainEmbeddingsWrapper"):
         
        evaluator = RAGEvaluator(mock_pipeline, llm, embed)
        evaluator.metrics = [mock_metric_1, mock_metric_2]

    # 3. 执行评分
    question = "什么是 RAG?"
    answer = "RAG 是检索增强生成。"
    contexts = ["RAG 结合了检索和生成..."]
    ground_truth = "检索增强生成技术。"

    scores = await evaluator.score_single_item(
        question=question,
        answer=answer,
        contexts=contexts,
        ground_truth=ground_truth
    )

    # 4. 验证结果
    assert scores["faithfulness"] == 0.95
    assert scores["context_precision"] == 0.88
    
    # 验证 mock 方法被正确调用
    mock_metric_1.single_turn_ascore.assert_called_once()
    mock_metric_2.single_turn_ascore.assert_called_once()

@pytest.mark.asyncio
async def test_score_single_item_exception_handling(mock_pipeline, mock_llm_and_embed):
    """
    [Unit] 测试异常处理：如果某个指标计算失败，不应导致整个评测崩溃，应返回 0.0
    """
    llm, embed = mock_llm_and_embed
    
    # 模拟一个会抛出异常的指标
    bad_metric = MagicMock()
    bad_metric.name = "broken_metric"
    bad_metric.single_turn_ascore = AsyncMock(side_effect=ValueError("Calculation Error"))
    
    with patch("app.services.evaluation.evaluation_runner.LangchainLLMWrapper"), \
         patch("app.services.evaluation.evaluation_runner.LangchainEmbeddingsWrapper"):
         
        evaluator = RAGEvaluator(mock_pipeline, llm, embed)
        evaluator.metrics = [bad_metric]
        
    scores = await evaluator.score_single_item("Q", "A", ["C"], "GT")
    
    # 验证是否降级为 0.0
    assert scores["broken_metric"] == 0.0