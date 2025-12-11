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
# 2. 依赖层
# -----------------------------------------------------------------

RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/

RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
# COPY torch-2.5.1+cu121-cp311-cp311-linux_x86_64.whl /tmp/
# RUN --mount=type=cache,target=/root/.cache/uv \
#     uv pip install --system /tmp/torch-*.whl
# 如果下torch一直失败可以手动下载到项目根目录用上面这两个安装

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