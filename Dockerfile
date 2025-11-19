# 使用 Python 3.10 轻量版镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 1. 安装系统依赖
# build-essential: 编译某些 python 包需要
# libpq-dev: psycopg2 (Postgres驱动) 需要
# curl: 用于健康检查
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. 复制并安装依赖
# 这样做利用了 Docker 缓存层，只有 requirements.txt 变了才重装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. 复制项目代码
COPY . .

# 设置 PYTHONPATH，确保 app 模块能被找到
ENV PYTHONPATH=/app

# 默认启动命令 (会被 docker-compose 覆盖)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]