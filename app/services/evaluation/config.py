from dataclasses import dataclass
from typing import Tuple

from app.core.config import settings


@dataclass(frozen=True)
class EvaluationConfig:
    """
    统一评估相关的默认参数。
    """

    testset_size: int = settings.TESTSET_SIZE
    batch_size: int = 16
    metrics: Tuple[str, ...] = (
        "faithfulness",
        # "answer_relevancy",
        "context_recall",
        # "context_precision",
    )


def get_default_config() -> EvaluationConfig:
    return EvaluationConfig()

