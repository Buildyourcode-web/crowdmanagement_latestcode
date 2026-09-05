# BYC AI Command & Control Platform — Backend & API Layer

Production-grade, asynchronous backend API foundation for the **BYC AI Command & Control Platform**, built for mega-event crowd monitoring, AI video analytics, FRS operations, and multi-agency emergency response at the **Khairatabad Ganesh Festival 2026**.

---

## 🏛️ Architecture & Tech Stack

```
                    React Frontend (Vite)
                             │
                    REST + WebSocket
                             │
                             ▼
                    FastAPI (Python 3.12+)
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
    PostgreSQL 16          Redis          Background Jobs
    PostGIS                Pub/Sub
    `main_crowd_ai`          │
          │                  ▼
          └──────────── Event Bus / WebSocket
```

- **Framework**: FastAPI (Asynchronous Python 3.10+)
- **Validation**: Pydantic v2 & Pydantic-Settings
- **ORM & DB**: SQLAlchemy 2.0 (Asyncpg) + PostgreSQL 16 + PostGIS
- **Migrations**: Alembic
- **Real-Time Pub/Sub**: Redis 7 & WebSockets
- **Authentication**: JWT (HS256) with Bcrypt Password Hashing & RBAC
- **Testing**: Pytest & Pytest-Asyncio (100% pass rate)

---

## 🚀 Getting Started

### 1. Local Environment Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and verify database settings:

```ini
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/main_crowd_ai
DATABASE_SYNC_URL=postgresql://postgres:postgres@localhost:5432/main_crowd_ai
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=byc_super_secret_jwt_key_khairatabad_2026_production_change_me
```

### 3. Initialize Database & Seed Demo Data

```bash
# Create all tables in main_crowd_ai database
python scripts/init_db.py

# Seed full operational dataset (1 Event, 12 Zones, 8 Gates, 100 Cameras, 16 FRS channels, Alerts, Incidents, Users)
python scripts/seed.py
```

### 4. Start the FastAPI Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🐳 Docker Deployment

To launch the complete container stack (FastAPI + PostgreSQL PostGIS + Redis):

```bash
cd backend
docker compose up -d
```

---

## 🔑 Default Seed Credentials

| Role | Username | Password | Purpose |
|---|---|---|---|
| `SUPER_ADMIN` | `admin` | `admin123` | Full access, system administration |
| `COMMANDER` | `commander` | `commander123` | Incident assignment, operations dispatch |
| `CONTROL_ROOM` | `operator` | `operator123` | Crowd flow, cameras, alerts triaging |
| `FRS_OPERATOR` | `frs_reviewer` | `frs123` | Authorized FRS candidate human review |

---

## 📡 API Endpoints Overview (`/api/v1`)

- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Core Routers:
1. **Authentication**: `/api/v1/auth/login`, `/api/v1/auth/refresh`, `/api/v1/auth/logout`, `/api/v1/auth/me`
2. **Cameras**: `GET /api/v1/cameras` (with zone, type, status, and FRS filters), `GET /api/v1/cameras/{id}/health`
3. **Zones**: `GET /api/v1/zones`, `GET /api/v1/zones/{id}`, `GET /api/v1/zones/{id}/gates`, `GET /api/v1/zones/{id}/crowd`
4. **Crowd Intelligence**: `GET /api/v1/crowd/summary`, `GET /api/v1/crowd/zones`, `GET /api/v1/crowd/timeseries`, `GET /api/v1/crowd/queues`
5. **FRS (Facial Recognition)**: `GET /api/v1/frs/dashboard`, `GET /api/v1/frs/cameras`, `GET /api/v1/frs/candidates`, `POST /api/v1/frs/candidates/{id}/review` (Audit logged), `GET /api/v1/frs/history`
6. **Missing Persons**: `GET /api/v1/missing-persons`, `GET /api/v1/missing-persons/{id}/timeline`
7. **Alerts**: `GET /api/v1/alerts`, `POST /api/v1/alerts/{id}/acknowledge`, `POST /api/v1/alerts/{id}/resolve`
8. **Incidents**: `GET /api/v1/incidents`, `POST /api/v1/incidents/{id}/acknowledge`, `POST /api/v1/incidents/{id}/assign`, `POST /api/v1/incidents/{id}/resolve`, `POST /api/v1/incidents/{id}/notes`
9. **Operations**: `GET /api/v1/operations/police-units`, `GET /api/v1/operations/medical-units`, `GET /api/v1/operations/emergency-routes`
10. **Analytics**: `GET /api/v1/analytics/attendance`, `GET /api/v1/analytics/incidents`, `GET /api/v1/analytics/cameras`
11. **Predictions**: `GET /api/v1/predictions/crowd`, `GET /api/v1/predictions/queues`, `GET /api/v1/predictions/zones`
12. **System Health**: `GET /api/v1/system/health`, `GET /api/v1/system/gpus`, `GET /api/v1/system/services`
13. **Internal AI Ingestion**: `POST /internal/v1/ai/events` (Service key authenticated)
14. **WebSocket Live Events**: `ws://localhost:8000/ws/v1/events`

---

## 🧪 Running Automated Tests

```bash
pytest tests/ -v
```
