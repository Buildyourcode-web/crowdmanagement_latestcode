#!/usr/bin/env bash
# ==============================================================================
# One-Click Automated Deployment Script for CPU Frontend Instance
# Usage: bash deploy.sh
# ==============================================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}   BYC AI Platform — CPU Frontend Deployment          ${NC}"
echo -e "${GREEN}======================================================${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${SCRIPT_DIR}"

# 1. Check Docker & Docker Compose
if ! command -v docker &> /dev/null; then
    echo -e "${RED}[ERROR] Docker is not installed!${NC}"
    echo "Install it with: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}[ERROR] Docker Compose plugin is not installed!${NC}"
    exit 1
fi

# 2. Check or create .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}[!] .env not found. Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Please enter the IP or DNS of your GPU Backend Instance (e.g. http://10.0.0.5:8000):${NC}"
    read -r user_backend_url
    if [ -n "$user_backend_url" ]; then
        # Ensure protocol is present
        if [[ ! "$user_backend_url" =~ ^https?:// ]]; then
            user_backend_url="http://${user_backend_url}"
        fi
        # Ensure port 8000 is present if no port specified
        if [[ ! "$user_backend_url" =~ :[0-9]+ ]]; then
            user_backend_url="${user_backend_url}:8000"
        fi
        sed -i "s|BACKEND_URL=.*|BACKEND_URL=${user_backend_url}|g" .env
        echo -e "${GREEN}[✓] Set BACKEND_URL=${user_backend_url} in .env${NC}"
    fi
fi

# 3. Pull / Build and launch containers
echo -e "${GREEN}==> Building and launching Nginx frontend container...${NC}"
docker compose -f docker-compose.yml up -d --build

# 4. Verification
echo -e "${GREEN}==> Checking frontend service health...${NC}"
sleep 3
if docker ps --format '{{.Names}}' | grep -q "byc_cpu_frontend"; then
    echo -e "${GREEN}======================================================${NC}"
    echo -e "${GREEN}   [✓] Frontend successfully deployed and running!    ${NC}"
    echo -e "${GREEN}======================================================${NC}"
    echo -e "Web Application URL: http://$(curl -s ifconfig.me || hostname -I | awk '{print $1}')"
    echo -e "Check logs anytime with: docker compose logs -f frontend"
else
    echo -e "${RED}[ERROR] Container failed to start. Logs:${NC}"
    docker compose logs frontend
    exit 1
fi
