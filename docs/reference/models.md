领域模型 (Domain Models)

本项目使用 SQLModel (基于 SQLAlchemy + Pydantic) 定义数据库 Schema。

::: app.domain.models.knowledge
options:
members:
- Knowledge
- KnowledgeStatus

::: app.domain.models.document
options:
members:
- Document
- DocStatus

::: app.domain.models.chunk
options:
members:
- Chunk

::: app.domain.models.experiment
options:
members:
- Experiment

::: app.domain.models.testset
options:
members:
- Testset