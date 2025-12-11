<div align="center">

<h1>📚 RAG Practice: Full-Stack RAG Knowledge Base & Evaluation System</h1>

<p style="margin-top: 10px;"> <img src="https://img.shields.io/badge/License-Apache--2.0-green" alt="license"> <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="python"> <img src="https://img.shields.io/badge/Next.js-14-black" alt="nextjs"> <img src="https://img.shields.io/badge/Docker-Enabled-2496ED" alt="docker"> </p>

<p> <a href="#-introduction">Introduction</a> • <a href="#-features">Features</a> • <a href="#-architecture">Architecture</a> • <a href="#-tech-stack">Tech Stack</a> • <a href="#-quick-start">Quick Start</a> • <a href="#-limitations">Limitations</a> • <a href="#-contributing">Contributing</a> </p>

</div>

## 📖 Introduction

**RAG Practice** is an engineering implementation that attempts to translate RAG (Retrieval-Augmented Generation) theory into code. Unlike simple demos, this project focuses on the practical challenges encountered when moving a RAG system from a prototype to a production-grade system.

Key focuses of the project:

1. **Data Processing Granularity**: Using Docling to explore parsing and semantic slicing of complex documents (PDFs).
    
2. **Retrieval Strategy Optimization**: Moving beyond single vector retrieval to implement **Hybrid Search (Vector + Keyword)** based on Elasticsearch and **RRF (Reciprocal Rank Fusion)**.
    
3. **Closed-Loop Evaluation**: Integrating Ragas and Langfuse to build an automated evaluation loop: "Generate Test Set -> Run Experiment -> Quantify Metrics".
    
4. **Engineering Practices**: Implementing asynchronous task queues, rate limiting, permission management, and containerized deployment.
    

## ✨ Features

### 🧠 Advanced Retrieval & Generation

- **Hybrid Search**: Combines Dense Vector (Semantic) and Sparse BM25 (Keyword) retrieval to solve the issue of inaccurate matching for specific terms.
    
- **Rerank**: Integrates TEI (Text Embeddings Inference) to re-rank recalled results.
    
- **Query Rewrite**: Rewrites multi-turn conversation context into standalone queries to improve retrieval accuracy.
    

### 📄 Data Ingestion

- **Document Parsing**: Uses [Docling](https://github.com/DS4SD/docling "null") to process PDF documents, attempting to preserve the document hierarchy.
    
- **Asynchronous Processing**: Non-blocking document parsing and vectorization pipeline based on Redis + Arq.
    
- **Parent-Child Indexing**: Implements the Small-to-Big strategy, using small slices for retrieval and large windows for generation.
    

### 📊 Evaluation & Observability (Ops)

- **Automated Evaluation**: Integrates **Ragas** to support automated calculation of metrics like Faithfulness and Answer Relevancy.
    
- **Full-Link Tracing**: Connects to **Langfuse** to monitor the full trace from retrieval to generation and token consumption.
    

## 🖼️ Screenshots

<center> Main Dashboard </center>

<center>Permission Management / File Upload</center>

<center>Source & Page Number View / Reranker Confidence Score</center>

<center>Visual Test Set Management & Experiment Running</center>

## 🛠️ Tech Stack

|**Module**|**Technology**|**Description**|
|---|---|---|
|**Backend Framework**|FastAPI|High-performance Python Web Framework|
|**ORM**|SQLModel (PostgreSQL)|Modern Database Interaction|
|**LLM Orchestration**|LangChain|Core Logic Orchestration|
|**Document Processing**|Docling|Deep PDF Parsing & OCR Support|
|**Vector Database**|Elasticsearch (8.17.0)|Hybrid Query Support (Vector + Full Text)|
|**Rerank**|HuggingFace TEI|Local Deployment of BGE-Reranker Model|
|**Task Queue**|Arq + Redis|Handling Long-running Tasks (Parsing, Eval)|
|**Object Storage**|MinIO|Storing Original Document Files|
|**Observability**|Langfuse|LLM Ops Monitoring & Tracing|
|**Evaluation**|Ragas|RAG Performance Quantification|

## 🏗️ System Architecture

_(Please refer to the diagrams in the main README or view the source code for Mermaid definitions)_

The system consists of a Next.js frontend, a FastAPI backend, and several worker services for asynchronous processing. Data flows through MinIO for storage, Elasticsearch for retrieval, and Redis for caching and queuing.

## 🚀 Quick Start

This project is built with Docker for one-click startup.

### Prerequisites

- Docker Desktop / Docker Engine
    
- Git
    

#### Recommended Configuration (Production/Smooth Dev)

- **CPU**: 8 Cores
    
- **RAM**: 32 GB
    
- **GPU**: NVIDIA GPU with 8GB VRAM
    
- **Storage**: 50 GB+
    

> Minimum Config: 16GB RAM. You may need to manually lower the resource limits for `docling-worker` and `rerank-service` in `docker-compose.yml` to avoid OOM.

### Deployment Steps

#### **Clone Repository**

```
git clone git@github.com:pswd123456/rag-practice.git
cd rag-practice
```

#### Configure Environment Variables

#### 🧪 Key Environment Variables

|Variable Name|Required|Example|Description|
|---|---|---|---|
|`DASHSCOPE_API_KEY`|✅|`sk-...`|Qwen API Key (Default for Gen & Embed)|
|`DEEPSEEK_API_KEY`||`sk-...`|DeepSeek Model Support|
|`ZENMUX_API_KEY`|||If using Gemini models|
|`MODEL_SOURCE`||`online`|Model loading: `online` (Auto Download) or `local`|
|`LANGFUSE_PUBLIC_KEY`|✅|`pk-lf-...`|Langfuse Project Public Key|
|`LANGFUSE_SECRET_KEY`|✅|`sk-lf-...`|Langfuse Project Secret Key|
|`LANGFUSE_NEXTAUTH_SECRET`|✅|Generated via openssl|Langfuse Auth|
|`LANGFUSE_SALT`|✅|Generated via openssl|Langfuse Auth|
|`LANGFUSE_ENCRYPTION_KEY`|✅|Generated via openssl|Langfuse Auth|
|`SECRET_KEY`|✅|Generated via openssl|JWT Secret|

Copy and configure the env file:

```
cp .env.example .env
```

#### Start Services

**Start with Docker Compose:**

```
docker-compose up -d --build
```

#### Model Loading Configuration

This project supports two ways to load models.

##### **Option A: Auto Download (Recommended)**

No extra configuration is needed.

- **Docling Models**: Will be automatically downloaded to the cache directory inside the Docker container.
    
- **Rerank Models**: The TEI service will automatically pull the model from HuggingFace upon startup.
    

##### **Option B: Local Mode**

If you prefer to manage models manually or have them already downloaded:

1. Download the required models (e.g., `BAAI/bge-reranker-v2-m3`) to the `language_models` directory in the project root.
    
2. Set `MODEL_SOURCE=local` in your `.env` file.
    
3. Update the `rerank-service` volume mapping in `docker-compose.yml` to mount your local model directory to `/data`.
    

### **Access Services**

Frontend Access: [http://localhost:3000](https://www.google.com/search?q=http://localhost:3000/login "null")

**Initial Admin Account** (Required to view the Evaluation Dashboard):

- Account: `admin@example.com`
    
- Password: `admin123`
    

#### Post-Login Configuration

1. Register and log in to the [Langfuse Dashboard](https://www.google.com/search?q=http://localhost:3001 "null").
    
2. Generate API Keys and update your `.env` file.
    
3. Restart containers (`docker-compose up -d --force-recreate`).
    
4. Create two prompts in Langfuse:
    
    - `rag-default`: Standard chat prompt.
        
    - `rag-query-rewrite`: Query rewrite prompt (must include `chat_history` placeholder and `{{question}}` variable). _Note: Without these prompts, Langfuse tracing and Ragas evaluation will not function correctly._
        

#### 🔌 Service Ports

|Service|Port|Description|
|---|---|---|
|**Backend API**|8000|FastAPI Backend & Swagger Docs|
|**Frontend**|3000|Next.js UI|
|**MinIO Console**|9001|Object Storage Admin (`minioadmin`)|
|**Elasticsearch**|9200|Vector Database HTTP Interface|
|**Kibana**|5601|ES Visualization|
|**Langfuse**|3001|LLM Ops Dashboard|
|**Rerank Service**|8003|TEI Inference Interface|

## ⚠️ Limitations

As an exploratory learning project, there is room for improvement:

1. **Document Adaptability**: Deep parsing currently focuses on PDF formats using Docling.
    
2. **Performance**: While asynchronous queues are used, local model inference (TEI/Docling) can be a bottleneck under high concurrency.
    
3. **Domain Specificity**: Currently focuses on a general RAG pipeline without domain-specific fine-tuning (e.g., Legal or Medical).
    

> **⚠️ Note:** This project is currently in `v0.1.0` (Work in Progress). It is a **learning and practice project** built to deeply understand RAG architecture and engineering.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

## 📄 License

Apache License 2.0