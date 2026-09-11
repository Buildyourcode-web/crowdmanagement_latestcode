# ==============================================================================
# GPU-Accelerated Backend Dockerfile for BYC Command & Control Platform
# Ubuntu 22.04 + NVIDIA CUDA 12.4 + cuDNN + Python 3.10 + ONNXRuntime-GPU + FFmpeg
# ==============================================================================

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# NVIDIA Runtime Capabilities
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

WORKDIR /app

# 1. Install system runtime dependencies (Python 3.10, FFmpeg for RTSP, OpenCV libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libpq-dev \
    curl \
    git \
    build-essential \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 3. Copy and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 4. Create persistent volume mount points for data, models, and InsightFace cache
RUN mkdir -p /app/media /app/models /app/data /root/.insightface/models

# 5. Copy backend application source code
# (Assumes docker build context is the repository root or backend directory)
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY scripts /app/scripts

# Copy YOLO model if present in local build context
COPY models /app/models

EXPOSE 8000

# Healthcheck to verify FastAPI is alive
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

# Start Uvicorn ASGI production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
