# tests/test_evaluation_adaptation.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.evaluation.runner import RAGEvaluator

@pytest.mark.asyncio
async def test_adapt_metrics_flow():
    """
    测试 RAGEvaluator.adapt_metrics 方法是否正确调用了底层 Ragas 指标的适配逻辑
    """
    # 1. 准备 Mock 对象
    mock_pipeline = MagicMock()
    mock_llm = MagicMock()
    mock_embed = MagicMock()

    # 2. Patch 评估器中用到的 Ragas 指标类
    # 我们拦截 evaluation.runner 模块中导入的 Faithfulness 类
    with patch("app.services.evaluation.runner.Faithfulness") as MockFaithfulness, \
         patch("app.services.evaluation.runner.AnswerRelevancy") as MockAnswerRelevancy, \
         patch("app.services.evaluation.runner.ContextRecall") as MockContextRecall, \
         patch("app.services.evaluation.runner.ContextPrecision") as MockContextPrecision:

        fake_adapted_prompts = {"long_form_answer_prompt": "这是适配后的中文提示词"}
        
        for MockClass in [MockFaithfulness, MockAnswerRelevancy, MockContextRecall, MockContextPrecision]:
            # 获取该类实例化后的对象 (metric instance)
            mock_instance = MockClass.return_value
            
            # 关键：显式将其 adapt_prompts 方法设为异步 Mock
            mock_instance.adapt_prompts = AsyncMock(return_value=fake_adapted_prompts)
            
            # 模拟 set_prompts 和 llm
            mock_instance.set_prompts = MagicMock()
            mock_instance.llm = MagicMock()

        # 3. 初始化评估器 (这会触发 _build_metrics)
        evaluator = RAGEvaluator(
            rag_pipeline=mock_pipeline,
            llm=mock_llm, 
            embed_model=mock_embed
        )

        # 4. 执行被测方法
        target_language = "chinese"
        await evaluator.adapt_metrics(language=target_language)

        # 5. 验证逻辑
        # 验证是否所有指标都被调用了适配
        # evaluator.metrics 里应该有 4 个 mock 对象
        assert len(evaluator.metrics) == 4
        
        for metric in evaluator.metrics:
            # 验证每个指标的 adapt_prompts 是否被正确调用
            metric.adapt_prompts.assert_called_once()
            call_kwargs = metric.adapt_prompts.call_args.kwargs
            assert call_kwargs['language'] == target_language
            
            # 验证 set_prompts 是否被调用
            metric.set_prompts.assert_called_once_with(**fake_adapted_prompts)

@pytest.mark.asyncio
async def test_adapt_metrics_partial_failure():
    """
    测试当某个指标适配失败时，是否能优雅降级（不影响其他指标）
    """
    mock_pipeline = MagicMock()
    
    # 模拟两个指标：MetricA 成功，MetricB 失败
    mock_metric_a = MagicMock()
    mock_metric_a.name = "MetricA"
    mock_metric_a.adapt_prompts = AsyncMock(return_value={})
    
    mock_metric_b = MagicMock()
    mock_metric_b.name = "MetricB"
    # 模拟抛出异常
    mock_metric_b.adapt_prompts = AsyncMock(side_effect=Exception("API Error"))

    # 手动构造 Evaluator，绕过 _build_metrics，直接注入我们控制的 metrics
    evaluator = RAGEvaluator(mock_pipeline, MagicMock(), MagicMock())
    evaluator.metrics = [mock_metric_a, mock_metric_b]

    # 执行
    await evaluator.adapt_metrics("chinese")

    # 验证
    # A 应该成功设置
    mock_metric_a.set_prompts.assert_called_once()
    # B 抛异常后，set_prompts 不应被调用，但程序不应崩溃
    mock_metric_b.set_prompts.assert_not_called()