from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship, Column, JSON

if TYPE_CHECKING:
    from .knowledge import Knowledge
    from .testset import Testset

class Experiment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    knowledge_id: int = Field(foreign_key="knowledge.id")
    testset_id: int = Field(foreign_key="testset.id")

    runtime_params: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Ragas scores
    faithulness: float = Field(default=0.0)
    answer_relevancy: float = Field(default=0.0)
    context_recall: float = Field(default=0.0)
    context_precision: float = Field(default=0.0)

    # 任务状态
    status: str = Field(default="PENDING")
    error_message: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)

    knowledge: "Knowledge" = Relationship(back_populates="experiments")
    testset: "Testset" = Relationship(back_populates="experiments")
