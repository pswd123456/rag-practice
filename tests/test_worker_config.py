import pytest
from app.worker import (
    process_document_task,
    delete_knowledge_task,
    generate_testset_task,
    run_experiment_task
)

def test_worker_retry_configuration():
    """
    验证 Arq Worker 的任务是否配置了合理的重试机制。
    这是 Infrastructure 稳定性的重要保障。
    """
    # 1. 文档处理任务 (涉及 MinIO下载 + Embedding API)
    # 应该有重试，但不需要太长的 backoff
    assert getattr(process_document_task, "max_tries", 0) >= 3, "文档处理任务应至少重试 3 次"
    assert getattr(process_document_task, "retry_delay", 0) >= 5, "文档处理重试间隔应至少 5 秒"

    # 2. 知识库删除任务 (涉及 MinIO 删除 + Chroma 删除)
    # 相对较快，重试次数可以少一点
    assert getattr(delete_knowledge_task, "max_tries", 0) >= 3

    # 3. 测试集生成 (涉及 LLM Generation)
    # 容易触发 Rate Limit，建议间隔长一点
    assert getattr(generate_testset_task, "max_tries", 0) >= 3
    assert getattr(generate_testset_task, "retry_delay", 0) >= 10, "LLM 相关任务重试间隔应较长以避开 Rate Limit"

    # 4. 实验运行 (涉及大量 LLM 评测)
    assert getattr(run_experiment_task, "max_tries", 0) >= 3
    assert getattr(run_experiment_task, "retry_delay", 0) >= 10