# Release Notes - v0.1.0 (MVP)

## 📅 发布日期
2025-11-30

## 🌟 核心里程碑
完成了 RAG 服务的基础工程化建设，实现了从文档上传、异步处理到 Ragas 评估的全链路闭环。

## 🚀 功能特性 (Features)

### 1. 知识库管理
- [x] 多知识库隔离 (Chroma Collection 级别)。
- [x] 支持 PDF/DOCX/TXT/MD 文件上传。
- [x] **异步数据摄取**: 使用 Redis + Arq 实现非阻塞的文件解析与 Embedding。
- [x] **数据强一致性**: 实现了 Postgres、MinIO、Elasticsearch 的原子性级联删除。

### 2. RAG 对话系统
- [x] 基础检索策略 (Dense Retrieval)。
- [x] 支持流式输出 (SSE)。
- [x] **引用溯源**: 对话回复中包含文档来源。

### 3. 评估体系 (Evaluation)
- [x] **测试集生成**: 基于上传文档自动生成 QA 对。
- [x] **自动化评测**: 集成 Ragas 框架，计算 Faithfulness, Answer Relevancy 等指标。
- [x] 评测历史记录与可视化 (Streamlit)。

### 4. 基础设施
- [x] 完整的 Docker Compose 编排 (API + Worker + DBs)。
- [x] 集成 MinIO 对象存储。

### 11-30 Update:
- 添加了文档处理工具 docling输出markdown文件, 使用hybridchunker输出contexturelized chunks
- 替换了chromadb为es, 实现了RRF hybrid search
- 集成了langfuse引入observality

## ⚠️ 已知限制 (Known Limitations)
- 暂未实现重排序 (Rerank)
- 引入docling处理表格, 针对复杂和跨页表格处理能力较弱。
- 暂无用户权限管理系统。

## 📦 部署指南
```bash
docker-compose up -d --build