# Production Multi-Instance Deployment Guide
## BYC AI Command & Control Platform (Khairatabad Ganesh 2026)

This deployment architecture is tailored for running the system across two separate environments:
1. **CPU Instance**: Serves the React frontend using a high-performance, multi-stage Nginx container with built-in reverse proxy.
2. **GPU Instance**: Runs the FastAPI backend, YOLO11x Crowd AI, InsightFace FRS, PostgreSQL 16 (with PostGIS), and Redis 7 with full NVIDIA GPU acceleration.

---

## 1. Architectural Overview & Rationale

```
+-----------------------------------------------------------------------------------+
|                                 USER BROWSER                                      |
+----------------------------------------+------------------------------------------+
                                         |
                       (HTTP / WebSocket on Port 80)
                                         v
+-----------------------------------------------------------------------------------+
|  INSTANCE 1: CPU INSTANCE (e.g. AWS EC2 t3.small / 2 vCPU, 2GB RAM)               |
|                                                                                   |
|  [ Docker: byc_cpu_frontend (Nginx 1.27 Alpine) ]                                |
|  - Serves static compiled Vite React SPA                                          |
|  - Reverse Proxies:                                                               |
|      /api/*   ----->  http://<GPU_INSTANCE_IP>:8000/api/*                         |
|      /ws/*    ----->  ws://<GPU_INSTANCE_IP>:8000/ws/*                            |
|      /media/* ----->  http://<GPU_INSTANCE_IP>:8000/media/*                       |
+----------------------------------------+------------------------------------------+
                                         |
                    (Intra-VPC or Public Port 8000)
                                         v
+-----------------------------------------------------------------------------------+
|  INSTANCE 2: GPU INSTANCE (e.g. AWS EC2 g4dn.xlarge / NVIDIA T4 or RTX 4090)     |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | [ Docker: byc_gpu_backend (FastAPI + YOLO11x + InsightFace + CUDA 12) ]    |  |
|  | - Port 8000 exposed                                                         |  |
|  | - Processes RTSP camera feeds @ 25-30 FPS                                   |  |
|  +-----------------------+-----------------------------+-----------------------+  |
|                          | (0.1ms intra-docker link)   |                          |
|                          v                             v                          |
|  +--------------------------------+   +-------------------------------------+     |
|  | [ Docker: byc_gpu_postgres ]   |   | [ Docker: byc_gpu_redis ]           |     |
|  | - PostGIS 16 (Port 5432)       |   | - Redis 7 (Port 6379)               |     |
|  | - Bound to 127.0.0.1 ONLY      |   | - Bound to 127.0.0.1 ONLY           |     |
|  +--------------------------------+   +-------------------------------------+     |
+-----------------------------------------------------------------------------------+
```

### Why Database & Redis Run on the GPU Instance (Recommendation)

> **Important Rationale:**
> 1. **Zero Latency (< 0.5 ms):** The Crowd AI and Face Recognition workers process 25–30 frames per second. For every frame, bounding boxes, spatial deduplication checks, and snapshot telemetry query Redis and PostgreSQL. Running DB and Redis in the same Docker network on the GPU instance eliminates cross-machine network latency.
> 2. **Security by Default:** PostgreSQL (5432) and Redis (6379) are bound to `127.0.0.1` and the internal Docker bridge network. They are **never exposed to the public internet**. Only port 8000 of the backend needs network access.
> 3. **Zero Cloud Database Cost:** You do **not** need expensive managed cloud services like AWS RDS or AWS ElastiCache. Both PostgreSQL and Redis run self-hosted with persistent Docker volumes (`postgres_data`, `redis_data`).
> 4. **Clean CPU Instance:** The CPU instance only runs a lightweight Nginx container (< 30 MB RAM, < 1% CPU), keeping its cost minimal (e.g. $5–$15/month).

---

## 2. Firewall / Security Group Configuration

### On the CPU Instance
| Protocol | Port | Source | Description |
| :--- | :--- | :--- | :--- |
| **TCP** | `80` | `0.0.0.0/0` (Anywhere) | Public Web Access (HTTP) |
| **TCP** | `443` | `0.0.0.0/0` (Anywhere) | Public Web Access (HTTPS, if SSL configured) |
| **TCP** | `22` | Your IP / Bastion | SSH management |

### On the GPU Instance
| Protocol | Port | Source | Description |
| :--- | :--- | :--- | :--- |
| **TCP** | `8000` | CPU Instance IP / VPC Subnet | Backend API & WebSocket communication |
| **TCP** | `22` | Your IP / Bastion | SSH management |
| **TCP** | `5432` | `None` (Keep closed) | DB is internal only |
| **TCP** | `6379` | `None` (Keep closed) | Redis is internal only |

> **Tip:** If both instances are in the same AWS VPC or cloud provider network, set the source for port 8000 on the GPU instance to the **Private IP** of the CPU instance for maximum security.

---

## 3. Step-by-Step Deployment: GPU Instance (Backend + DB + Redis)

### Prerequisites on GPU Instance (Ubuntu 22.04 / Debian)
Install Docker, Docker Compose, and the **NVIDIA Container Toolkit**:

```bash
# 1. Install NVIDIA drivers (if not already installed)
sudo apt update && sudo apt install -y ubuntu-drivers-common
sudo ubuntu-drivers install
# Verify GPU is detected:
nvidia-smi

# 2. Install Docker & Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 3. Install NVIDIA Container Toolkit (allows Docker to access GPU)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Test GPU in docker:
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

### Deploying the Backend Services
1. Clone or copy the repository to the GPU instance:
   ```bash
   git clone <YOUR_REPO_URL> /opt/khairatabad_ganesh
   cd /opt/khairatabad_ganesh
   ```

2. Configure environment variables:
   ```bash
   cp deploy/gpu-backend/.env.example deploy/gpu-backend/.env
   nano deploy/gpu-backend/.env
   ```
   *Make sure `CORS_ORIGINS` includes your CPU instance IP/domain, e.g.:*
   `CORS_ORIGINS=http://<CPU_INSTANCE_IP>,http://localhost,http://localhost:5173`

3. Verify YOLO model is in `models/`:
   ```bash
   ls -lh models/yolo11x.onnx
   ```

4. Launch backend, database, and cache:
   ```bash
   docker compose -f deploy/gpu-backend/docker-compose.yml up -d --build
   ```

5. Initialize Database tables:
   ```bash
   # Execute schema creation script inside container
   docker exec -it byc_gpu_backend python scripts/init_db.py
   ```

6. Verify logs and status:
   ```bash
   docker compose -f deploy/gpu-backend/docker-compose.yml ps
   docker compose -f deploy/gpu-backend/docker-compose.yml logs -f backend
   ```

---

## 4. Step-by-Step Deployment: CPU Instance (Frontend)

### Prerequisites on CPU Instance
Install Docker and Docker Compose:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

### Deploying the Frontend Service
1. Clone or copy the repository to the CPU instance:
   ```bash
   git clone <YOUR_REPO_URL> /opt/khairatabad_ganesh
   cd /opt/khairatabad_ganesh
   ```

2. Configure environment variables:
   ```bash
   cp deploy/cpu-frontend/.env.example deploy/cpu-frontend/.env
   nano deploy/cpu-frontend/.env
   ```
   *Set `BACKEND_URL` to your GPU instance address:*
   ```env
   FRONTEND_PORT=80
   BACKEND_URL=http://<GPU_INSTANCE_IP>:8000
   VITE_API_BASE_URL=
   VITE_WS_URL=
   ```
   *(Leaving `VITE_API_BASE_URL` empty instructs the app to use Nginx's built-in reverse proxy, preventing CORS issues).*

3. Build and run the frontend:
   ```bash
   docker compose -f deploy/cpu-frontend/docker-compose.yml up -d --build
   ```

4. Verify status:
   ```bash
   docker compose -f deploy/cpu-frontend/docker-compose.yml ps
   docker compose -f deploy/cpu-frontend/docker-compose.yml logs -f frontend
   ```

5. Open your web browser and navigate to `http://<CPU_INSTANCE_IP>`. The application will load and seamlessly communicate with the GPU backend!

---

## 5. Useful Management Commands

### Check Health & Status
```bash
# GPU Instance:
docker compose -f deploy/gpu-backend/docker-compose.yml ps

# CPU Instance:
docker compose -f deploy/cpu-frontend/docker-compose.yml ps
```

### Restarting Services
```bash
# GPU Backend Restart:
docker compose -f deploy/gpu-backend/docker-compose.yml restart backend

# Frontend Restart:
docker compose -f deploy/cpu-frontend/docker-compose.yml restart frontend
```

### Database Backup & Restore (on GPU Instance)
```bash
# Take a live database backup
docker exec -t byc_gpu_postgres pg_dump -U postgres main_crowd_ai > backup_$(date +%Y%m%d).sql

# Restore a database backup
cat backup_file.sql | docker exec -i byc_gpu_postgres psql -U postgres -d main_crowd_ai
```
