# Dockerfile

FROM python:3.10-slim

WORKDIR /app

# [新增] 1. 换源：将默认的 deb.debian.org 替换为 mirrors.aliyun.com
# 注意：python:3.10-slim 基于 Debian Bookworm/Trixie，源配置文件通常在 /etc/apt/sources.list.d/debian.sources
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# [原有] 2. 安装系统依赖 (现在应该飞快了)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# [原有] Python 依赖安装 (这一步你已经配置了国内源，保持不动)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]