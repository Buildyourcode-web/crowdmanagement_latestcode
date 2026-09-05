# AI Orchestrator & Multi-Camera Pipeline Management System

## 1. System Overview
The **AI Orchestrator** is the centralized control-plane layer of the BYC AI Platform. It provides deterministic, production-grade management of multi-camera real-time inference pipelines (Crowd AI and Queue AI) without requiring operators to execute terminal commands, DeepStream binaries, or Python runner scripts.

The system decouples **desired state** (operator intent) from **actual runtime state** (engine reality), ensuring automatic recovery from RTSP dropouts, staggered recovery across host reboots, capacity-aware fleet launches, and audit trail generation.

---

## 2. Core Architecture

`
                  +--------------------------------------------------------+
                  |              Festival Control Operator                 |
                  |        (Web Console / AIDeployment Dashboard)          |
                  +--------------------------+-----------------------------+
                                             | REST API (Bearer JWT: ai:manage)
                                             v
                  +--------------------------------------------------------+
                  |                 AI Orchestrator Engine                 |
                  |          (app/ai/orchestrator/service.py)              |
                  +--------------------------+-----------------------------+
                  |  Desired vs Actual State | Pre-flight Verification     |
                  |  Capacity Protection     | Reconnection Exponential    |
                  |  Priority Scheduler      | Fault Recovery Circuit-Brk  |
                  +──────────+───────────────+───────────────+─────────────+
                             |                               |
            +----------------+--------------+ +--------------+-------------+
            v                               v v                            v
+------------------------+      +------------------------+      +------------------------+
| CrowdPipelineRegistry  |      | QueuePipelineRegistry  |      |  AIDeploymentRepository|
| (Crowd AI Pipelines)   |      |  (Queue AI Pipelines)  |      |   (Postgres Telemetry) |
+------------------------+      +------------------------+      +------------------------+
`

---

## 3. State Machine Specifications

### 3.1 States
| State | Type | Description |
|---|---|---|
| STOPPED | Desired / Actual | Pipeline is not executing; zero GPU/CPU allocation. |
| CREATED | Actual | Pipeline deployment record registered in database. |
| VALIDATING | Actual | Running 6-step pre-flight checklist. |
| STARTING | Actual | Initializing model engine, GStreamer/RTSP source, and tracking state. |
| RUNNING | Desired / Actual | Pipeline actively processing frames, tracking people, emitting telemetry. |
| DEGRADED | Actual | Temporary stream loss detected (>10s without frame). Auto-reconnecting. |
| STOPPING | Actual | Flushing buffers and releasing model memory. |
| FAILED | Actual | Terminal failure or recovery retry limits exhausted. |
| RESTARTING | Actual | In-flight restart transition. |

### 3.2 State Transition Matrix
`
[STOPPED]  --(start_pipeline)-->  [VALIDATING]  -->  [STARTING]  -->  [RUNNING]
    ^                                                                     |
    |                                                               (RTSP drop)
    |                                                                     v
    |  <--------------(stop_pipeline)--------------- [DEGRADED]
    |                                                     |   ^
    |                                             (retry) |   | (timeout)
    |                                                     v   |
    +--(reconnect maxed)--> [FAILED] <--------------------+
`

---

## 4. Pre-Flight Verification Checklist
Prior to launching any inference pipeline, the Orchestrator enforces 6 mandatory criteria:
1. **Camera Operational**: Must be enabled (enabled=True) and status online. Returns 400 CAMERA_OFFLINE otherwise.
2. **Stream Verified**: RTSP stream must have verified connectivity (stream_status != 'NOT_TESTED' and != 'OFFLINE'). Returns 400 CAMERA_STREAM_NOT_VERIFIED.
3. **AI Profile Assigned**: Camera must possess an active, enabled AI profile assignment (CROWD_STANDARD, CROWD_HIGH_DENSITY, QUEUE_STANDARD, etc.). Returns 400 NO_AI_PROFILE_ASSIGNED.
4. **Spatial Geometry Readiness**:
   - For **Crowd AI**: At least one enabled CROWD_ROI polygon (>= 3 vertices). Returns 400 ROI_NOT_CONFIGURED.
   - For **Queue AI**: Must possess all three required geometries: QUEUE_ROI (>= 3 vertices), ENTRY_LINE, and EXIT_LINE. Returns 400 QUEUE_CONFIGURATION_NOT_READY.
5. **Hardware Runtime Check**: Host system must possess an NVIDIA GPU with active DeepStream / CUDA runtimes. Unsupported hosts cleanly reject with 400 RUNTIME_UNAVAILABLE (zero fake or synthetic metrics).
6. **Capacity Protection**: Evaluates projected RAM, CPU, GPU, and VRAM utilization across all active workloads using CapacityCalculator. If projected load exceeds safety thresholds, startup is blocked with 409 AI_CAPACITY_EXCEEDED.

---

## 5. Automated Fault-Recovery & Resilience

### 5.1 Automatic RTSP Reconnection
- **Detection**: Background supervision loop inspects active pipelines every 5 seconds. If a pipeline reports no frames in >10s, actual state transitions RUNNING -> DEGRADED.
- **Exponential Backoff**: Reconnection attempts are scheduled with exponential backoff: 2s -> 4s -> 8s -> 16s -> 30s.
- **Limit**: Maximum 5 reconnection attempts. If stream does not recover, transitions to FAILED.

### 5.2 Fault Recovery Circuit Breaker
- Prevents infinite crash-restart loops on corrupt video feeds or fatal memory faults.
- **Limit**: Maximum 3 automatic restarts within a sliding 10-minute window.
- When exceeded, ctual_state transitions to FAILED, sets error to AI_PIPELINE_RECOVERY_EXHAUSTED, and requires manual operator intervention.

### 5.3 Server / Application Restart Recovery
- Upon FastAPI startup lifecycle (@asynccontextmanager in main.py):
  1. Queries all deployments where desired_state == RUNNING.
  2. Restores pipelines in **staggered batches of 2** with a 2-second inter-batch delay.
  3. Re-verifies all pre-flight checks (skipping offline cameras or disabled configurations).
  4. Prevents simultaneous startup GPU current inrush spikes.

---

## 6. Operator Control Operations

### 6.1 Individual Pipeline Control
- **Start**: POST /api/v1/ai/orchestrator/pipelines/{camera_id_or_code}/start
- **Stop**: POST /api/v1/ai/orchestrator/pipelines/{camera_id_or_code}/stop
- **Restart**: POST /api/v1/ai/orchestrator/pipelines/{camera_id_or_code}/restart

### 6.2 Fleet Fleet Operations
- **Start All**: POST /api/v1/ai/orchestrator/start-all
  - Sorts eligible cameras by deployment priority: CRITICAL -> HIGH -> NORMAL -> LOW, breaking ties by camera_code ascending.
  - Sequentially starts pipelines until server capacity is reached.
  - Excess pipelines are marked as BLOCKED with detailed resource bottleneck diagnostics.
- **Stop All**: POST /api/v1/ai/orchestrator/stop-all
  - Gracefully stops all active pipelines across both CrowdPipelineRegistry and QueuePipelineRegistry.
  - Sets all database desired and actual states to STOPPED.

---

## 7. Security & RBAC
- **Read Operations** (GET /status, GET /deployments, GET /health): Require i:read permission (ROLE_AI_VIEWER, ROLE_OPERATOR, ROLE_ADMIN, SUPER_ADMIN).
- **Control Operations** (POST /start, POST /stop, POST /restart, POST /start-all, POST /stop-all): Require i:manage permission. Viewers receive 403 Forbidden.
- **Audit Trails**: Every lifecycle operation creates an immutable AuditLog entry detailing user ID, username, action, IP address, and runtime instance ID.
