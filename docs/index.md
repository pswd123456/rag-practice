# rag practice

> 一个可部署、工程化、集成了全链路评估体系的垂直领域 RAG 服务。

## 📖 项目简介

本项目旨在构建一个生产级的 **Retrieval-Augmented Generation (RAG)** 后端服务。区别于简单的 Demo，本项目注重工程质量、数据一致性、异步处理能力以及持续的效果评估。

核心目标是解决垂直领域（如金融、法律、医疗）中的知识问答难题，并通过 **Ragas** 框架量化优化效果。

## ✨ 核心特性

- **📚 知识库全生命周期管理**
    
    - 支持多知识库隔离（ChromaDB Collection 级别）。
        
    - 支持 PDF/TXT/MD 文件上传、解析与切片。
        
    - **原子性删除**：保证 SQL 数据库、向量数据库与对象存储的数据强一致性。
        
- **🚀 高性能异步处理**
    
    - 基于 **Redis + Arq** 的任务队列，解耦 API 与耗时任务（如文档解析、Embedding、大批量评测）。
        
    - 支持任务重试与死信处理。
        
- **🔍 灵活的检索策略**
    
    - 模块化的 `RetrievalService`。
        
    - 支持多种检索策略切换（Default, Dense Only, Hybrid, Rerank）。
        
- **🧪 自动化评估体系**
    
    - 集成 **Ragas** 框架。
        
    - 支持一键生成测试集（Testset Generation）。
        
    - 支持基于测试集的批量实验（Experiment Runner），并持久化评估指标（Faithfulness, Answer Relevancy 等）。
        
- **🛠️ 现代化的技术栈**
    
    - 全异步 Python (FastAPI + Motor/SQLModel)。
        
    - 容器化部署 (Docker Compose)。
        

## 🏗️ 技术栈

|组件|技术选型|用途|
|---|---|---|
|**Web 框架**|FastAPI|高性能异步 REST API|
|**数据库**|PostgreSQL (SQLModel)|存储元数据（文档状态、实验记录等）|
|**向量数据库**|ChromaDB|存储文档 Embedding 向量|
|**对象存储**|MinIO|存储原始文件与测试集文件|
|**任务队列**|Redis + Arq|异步处理文档解析与评估任务|
|**LLM 框架**|LangChain|编排 RAG 流程|
|**评估框架**|Ragas|生成测试集与计算评估指标|
|**前端**|Streamlit|管理后台与调试界面|

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
    
- Python 3.10+ (用于本地开发)
    

### 启动服务

1. **克隆项目**
    
    ```
    git clone <your-repo-url>
    cd rag-practice
    ```
    
2. **配置环境变量**
    
    复制 `.env.example` 为 `.env` 并填入你的 API Key (DashScope/OpenAI)。
    
    ```
    cp .env.example .env
    ```
    
3. **Docker 一键启动**
    
    ```
    docker-compose up -d --build
    ```
    
4. **访问服务**
    
    - **Streamlit 管理台**: [http://localhost:8501](http://localhost:8501 "null")
        
    - **API 文档 (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs "null")
        
    - **MinIO 控制台**: [http://localhost:9001](http://localhost:9001 "null") (User/Pass: `minioadmin`)
        
    - **Mkdocs 文档**: [http://localhost:8002](http://localhost:8002 "null")

## 📂 项目结构

```
.
├── app
│   ├── api         # 路由层 (Routes)
│   ├── core        # 核心配置 (Config, Logging)
│   ├── db          # 数据库连接
│   ├── domain      # 领域模型 (SQLModel)
│   ├── services    # 业务逻辑层 (Ingest, Retrieval, Evaluation, Pipeline)
│   └── worker.py   # 异步任务入口
├── evaluation      # 评估脚本独立模块
├── frontend        # Streamlit 前端
└── docker-compose.yml
```