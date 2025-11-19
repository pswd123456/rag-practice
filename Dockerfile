FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖 (这一步也换成国内 debian 源会更快，但先不改以免复杂)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# ✅ 优化点：挂载缓存 + 国内源
# 第一次构建可能还是慢(要下载填满缓存)，但第二次改依赖时，已有的包就是秒装！
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]