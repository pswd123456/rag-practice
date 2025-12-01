# 使用 Python 3.11 Slim 版本作为基础镜像
FROM python:3.11-slim

WORKDIR /app

# -----------------------------------------------------------------
# 1. 系统层优化
# -----------------------------------------------------------------
# 替换 Debian 系统源为阿里源 (加速 apt install)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装必要的系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    libgl1 \
    libglib2.0-0 \
    git \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------
# 2. 依赖层优化 (引入 uv)
# -----------------------------------------------------------------
# [修改点]：不再从 ghcr.io 拉取镜像，而是直接用 pip 安装 uv
# 使用 -i 指定阿里源，确保 100% 下载成功
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/

# [修改] 切换为 CUDA 12.1 的 Index URL (适配 RTX 2060)
# 注意：uv pip install 的语法略有不同，需要确保 uv 在 PATH 中 (pip安装后默认在 /usr/local/bin，已在 PATH 中)
# 这一步下载 pytorch 很大，建议保留原来的逻辑，或者让 uv 接管
# 注意：uv 的 --index-url 只能在 uv pip install 时指定，或者通过环境变量
# 这里我们用 uv 接管 pytorch 安装
RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

COPY requirements.txt .

# 设置 uv 的默认镜像源环境变量
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 使用 uv 安装剩余依赖
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

# COPY models /app/models
# -----------------------------------------------------------------
# 3. 源码层
# -----------------------------------------------------------------
COPY . .
ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]