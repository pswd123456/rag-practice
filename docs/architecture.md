# 系统架构设计

本文档详细描述了 RAG Service V4 的数据流向与核心组件交互。

## 📐 系统架构图

```
graph TD
    User[用户 / 前端] -->|HTTP Request| API[FastAPI Server]
    
    subgraph "数据存储层 (Persistence)"
        PG[(PostgreSQL)]
        Redis[(Redis Cache/Queue)]
        MinIO[(MinIO Object Storage)]
        Chroma[(ChromaDB Vector Store)]
    end

    subgraph "异步处理层 (Async Worker)"
        Worker[Arq Worker Process]
    end

    %% 1. 上传流程
    User -->|1. 上传文件| API
    API -->|1.1 保存原始文件| MinIO
    API -->|1.2 创建记录 (PENDING)| PG
    API -->|1.3 推送任务| Redis
    
    Redis -->|1.4 消费任务| Worker
    Worker -->|1.5 读取文件| MinIO
    Worker -->|1.6 解析 & Embedding| LLM_API[外部 LLM API]
    Worker -->|1.7 存入向量| Chroma
    Worker -->|1.8 存入 Chunk 映射| PG
    Worker -->|1.9 更新状态 (COMPLETED)| PG

    %% 2. 检索流程
    User -->|2. 提问 (Query)| API
    API -->|2.1 获取 Pipeline| RAG_Factory
    RAG_Factory -->|2.2 检索 (Retrieve)| Chroma
    RAG_Factory -->|2.3 生成 (Generate)| LLM_API
    API -->|2.4 返回答案 + 来源| User

    %% 3. 评估流程
    User -->|3. 发起评估| API
    API -->|3.1 创建实验记录| PG
    API -->|3.2 推送评估任务| Redis
    Redis -->|3.3 消费任务| Worker
    Worker -->|3.4 加载测试集| MinIO
    Worker -->|3.5 批量运行 Pipeline| API
    Worker -->|3.6 Ragas 评分 (Judge)| LLM_API
    Worker -->|3.7 保存分数| PG

    style API fill:#f9f,stroke:#333,stroke-width:2px
    style Worker fill:#bbf,stroke:#333,stroke-width:2px
```

## 🔄 核心数据流

### 1. 数据摄取 (Ingestion)

数据摄取过程设计为**异步非阻塞**模式，以支持大文件处理。

1. **API 层**: 接收文件 `UploadFile`，立即将其流式写入 **MinIO**。
    
2. **DB 层**: 在 Postgres `Document` 表中创建一条记录，状态标记为 `PENDING`。
    
3. **Queue 层**: 将 `doc_id` 推送至 **Redis** 任务队列。
    
4. **Worker 层**:
    
    - 从 Redis 获取任务。
        
    - 从 MinIO 下载文件到临时目录。
        
    - 调用 `LangChain` 加载器解析文本。
        
    - 执行文本切分 (Splitting) 和 向量化 (Embedding)。
        
    - 将向量写入 **ChromaDB**，将 Chunk 的元数据（`chroma_id`, `page_content`）写入 **Postgres**。
        
    - 最后更新 `Document` 状态为 `COMPLETED` 或 `FAILED`。
        

### 2. 检索与问答 (RAG Flow)

检索过程采用动态 Pipeline 构建模式。

1. **Pipeline Factory**: 根据请求中的 `knowledge_id` 和 `strategy` 参数，动态实例化 `VectorStoreManager` 和 `RAGPipeline`。
    
2. **Retrieval**:
    
    - 如果策略是 `dense_only`，直接调用 ChromaDB 的 `similarity_search`。
        
    - 如果策略是 `hybrid` (计划中)，结合关键词搜索结果。
        
3. **Generation**:
    
    - 将检索到的 Context 填充进 Prompt。
        
    - 调用 LLM 生成答案。
        
    - 支持流式输出 (`/chat/stream`)。
        

### 3. 评估体系 (Evaluation Flow)

评估是本项目的核心亮点，实现了闭环优化。

1. **Testset Generation**: 利用 LLM 根据现有文档自动生成 QA 对（问题-答案-Ground Truth），保存为 JSONL 存入 MinIO。
    
2. **Running Experiments**:
    
    - 读取 MinIO 中的测试集。
        
    - 使用当前的 RAG 配置（如 `top_k=5`, `strategy=hybrid`）批量回答问题。
        
    - 使用 **Ragas** 指标（Faithfulness, Answer Relevancy 等）对生成结果进行打分。
        
    - 分数持久化到 Postgres `Experiment` 表，便于前端绘制雷达图对比。
        

## 🛡️ 数据一致性设计

在执行删除操作（删除文档或删除知识库）时，系统遵循以下原则以保证一致性：

- **级联删除**: 删除 `Knowledge` -> 触发删除其下所有 `Document`。
    
- **原子清理**: 删除 `Document` 时：
    
    1. 删除 MinIO 原始文件。
        
    2. 利用 `chunks` 表中记录的 `chroma_id`，精准删除 ChromaDB 中的向量。
        
    3. 删除 Postgres 中的 `Chunk` 记录。
        
    4. 删除 Postgres 中的 `Document` 记录。