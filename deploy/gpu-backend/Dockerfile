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
COPY deploy/gpu-backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 4. Create persistent volume mount points for data, models, and InsightFace cache
RUN mkdir -p /app/media /app/models /app/data /root/.insightface/models

# 5. Copy backend application source code from backend directory
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini
COPY backend/scripts /app/scripts

# Copy YOLO model if present in local build context
COPY models /app/models

EXPOSE 8000

# Healthcheck — 120s start_period because ONNX + InsightFace buffalo_l
# loading on first boot can take 60-90s on a cold Docker start.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

# ==============================================================================
# Production ASGI Server: Uvicorn (single worker, uvloop event loop)
#
# WHY SINGLE WORKER:
# This application has in-process state that CANNOT be shared across OS processes:
#   1. ws_manager (WebSocket connections) — process-local set, cannot broadcast
#      across Gunicorn workers.
#   2. Camera threads (auto_start_main_camera) — lifespan starts them in EVERY
#      Gunicorn worker, producing N copies of the same RTSP stream reader.
#   3. gpu_pool (ONNX sessions) — loaded once per process; N workers = N × VRAM.
#
# To scale HTTP concurrency, tune uvicorn async throughput (uvloop + httptools)
# and tune the asyncpg pool size.  Horizontal scaling = add more EC2 instances
# each with its own set of cameras, NOT multiple workers on one instance.
#
# GPU_WORKER_COUNT env controls how many GPU ONNX sessions the pool creates
# (0 = auto-detect from nvidia-smi).
# ==============================================================================
ENV GPU_WORKER_COUNT=0
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--timeout-keep-alive", "30"]
