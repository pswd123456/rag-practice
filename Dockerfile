# 使用 Python 3.10 Slim 版本作为基础镜像
FROM python:3.10-slim

WORKDIR /app

# -----------------------------------------------------------------
# 1. 系统层优化
# -----------------------------------------------------------------
# 替换 Debian 系统源为阿里源 (加速 apt install)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装必要的系统依赖 (保留了你之前的列表)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    libgl1 \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------
# 2. 依赖层优化 (引入 uv)
# -----------------------------------------------------------------
# [关键] 从官方镜像中直接复制 uv 二进制文件 (这是最安全、最新的安装方式)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

# [关键] 使用 uv 替代 pip 安装依赖
# --system    : 直接安装到系统 Python 环境中 (Docker 容器内不需要再创建 venv)
# --index-url : 强制指定阿里源
# --mount     : 挂载缓存目录，确保下一次构建更快
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt
# -----------------------------------------------------------------
# 3. 源码层
# -----------------------------------------------------------------
COPY . .

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]