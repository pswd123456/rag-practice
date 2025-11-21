# 快速开始

## 环境要求

* Docker & Docker Compose (推荐)
* Python 3.10+ (如果本地开发)

## 🐳 Docker 一键启动

这是最推荐的运行方式，能够一键拉起 PostgreSQL, Redis, MinIO, ChromaDB 以及 API 服务。

1.  **配置环境变量**
    复制 `.env.example` (如果有) 或新建 `.env` 文件：
    ```bash
    DASHSCOPE_API_KEY=sk-xxxxxx  # 你的阿里千问 Key
    DATABASE_URL=postgresql+psycopg2://myuser:mypassword@db:5432/rag_db
    # ... 其他配置参考 config.py
    ```

2.  **启动服务**
    ```bash
    docker-compose up -d --build
    ```

3.  **访问服务**
    * **API 文档 (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
    * **管理后台 (Streamlit)**: [http://localhost:8501](http://localhost:8501) (需确认 docker-compose 端口映射)
    * **MinIO 控制台**: [http://localhost:9001](http://localhost:9001)

## 💻 本地开发模式

如果你需要调试代码：

1.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

2.  **启动基础设施 (DB/Redis/MinIO)**
    建议仅使用 Docker 启动基础设施：
    ```bash
    docker-compose up -d db redis minio chroma
    ```

3.  **运行 Worker (处理异步任务)**
    ```bash
    arq app.worker.WorkerSettings
    ```

4.  **运行 API**
    ```bash
    python app/main.py
    ```