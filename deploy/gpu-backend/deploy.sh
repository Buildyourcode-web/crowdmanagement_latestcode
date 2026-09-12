#!/usr/bin/env bash
# ==============================================================================
# One-Click Automated Deployment Script for GPU Backend Instance
# Usage: bash deploy.sh
# ==============================================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}   BYC AI Platform — GPU Backend Deployment          ${NC}"
echo -e "${GREEN}======================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${SCRIPT_DIR}"

# 1. Check NVIDIA GPU & Drivers
echo -e "${GREEN}==> Verifying NVIDIA GPU driver...${NC}"
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}[ERROR] nvidia-smi not found! Please install NVIDIA GPU drivers first.${NC}"
    exit 1
fi
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

# 2. Check Docker & NVIDIA Container Toolkit
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR] Docker is not installed!${NC}"
    echo "Install with: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

echo -e "${GREEN}==> Verifying NVIDIA Container Toolkit...${NC}"
if ! docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo -e "${YELLOW}[!] NVIDIA Container Toolkit test failed. Attempting setup...${NC}"
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
      sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
fi

# 3. Check YOLO Model
echo -e "${GREEN}==> Checking YOLO ONNX model...${NC}"
if [ ! -f "${ROOT_DIR}/models/yolo11x.onnx" ]; then
    echo -e "${YELLOW}[!] Warning: ${ROOT_DIR}/models/yolo11x.onnx not found!${NC}"
    echo -e "${YELLOW}Please ensure yolo11x.onnx is placed in the models/ directory.${NC}"
fi

# 4. Check or create .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}[!] .env not found. Creating from .env.example...${NC}"
    # Auto-generate unique cryptographically secure secrets
    RAND_JWT=$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || date +%s | sha256sum | head -c 64)
    RAND_AI=$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || date +%s | sha256sum | head -c 64)
    sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${RAND_JWT}|g" .env
    sed -i "s|AI_SERVICE_API_KEY=.*|AI_SERVICE_API_KEY=${RAND_AI}|g" .env
    echo -e "${GREEN}[✓] Generated unique cryptographically secure JWT and API secrets${NC}"
fi

# 5. Build and launch Backend + DB + Redis
echo -e "${GREEN}==> Launching Backend, PostgreSQL (PostGIS), and Redis...${NC}"
export COMPOSE_BAKE=false
export DOCKER_BUILDKIT=1
docker compose -f docker-compose.yml up -d --build

# 6. Wait for DB to be healthy and initialize schema
echo -e "${GREEN}==> Waiting for PostgreSQL to be ready...${NC}"
for i in {1..30}; do
    if docker exec byc_gpu_postgres pg_isready -U postgres -d main_crowd_ai &> /dev/null; then
        echo -e "${GREEN}[✓] PostgreSQL is ready.${NC}"
        break
    fi
    sleep 2
done

echo -e "${GREEN}==> Waiting for Backend container to be running...${NC}"
for i in {1..30}; do
    if [ "$(docker inspect -f '{{.State.Running}}' byc_gpu_backend 2>/dev/null)" = "true" ]; then
        echo -e "${GREEN}[✓] Backend container is running.${NC}"
        break
    fi
    sleep 2
done

echo -e "${GREEN}==> Initializing Database Tables...${NC}"
docker exec byc_gpu_backend python scripts/init_db.py


echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}   [✓] GPU Backend stack successfully running!        ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "API Endpoint: http://$(curl -s ifconfig.me || hostname -I | awk '{print $1}'):8000"
echo -e "Swagger Docs: http://$(curl -s ifconfig.me || hostname -I | awk '{print $1}'):8000/docs"
echo -e "Health Check: http://$(curl -s ifconfig.me || hostname -I | awk '{print $1}'):8000/api/v1/health/live"
echo -e "Check logs anytime with: docker compose logs -f backend"
