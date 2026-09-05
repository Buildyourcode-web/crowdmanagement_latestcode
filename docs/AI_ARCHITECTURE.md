# BYC AI Platform — Technical Architecture & AI Orchestration Foundation

**Event:** Khairatabad Ganesh Festival 2026  
**Platform:** BYC AI Command & Control (C&C) Platform  
**Document Version:** 1.0.0 (Step 1 Baseline & Foundation)  
**Status:** Step 1 Foundation Established — Inference Pipelines [NOT IMPLEMENTED]

---

## 1. Executive Summary & Philosophy

The BYC AI Command & Control platform is an enterprise-grade crowd monitoring, facial recognition, and event management platform. This document establishes the foundational design for the **AI Deployment & Orchestration System**.

### Core Tenets
1. **Zero Fake Metrics:** The system will never return synthetic people counts, simulated crowd densities, fake FRS matches, or fictitious GPU capacities. If a service is offline, it reports `NOT_AVAILABLE` or `NOT_IMPLEMENTED`.
2. **Safe Multi-Environment Operation:** The platform runs reliably on CPU-only local development laptops, single-GPU edge boxes, and multi-GPU high-density production servers without code branching.
3. **Strict RBAC & Isolation:** All AI deployment, configuration, and capacity endpoints strictly adhere to existing JWT token authentication and role-based access control.

---

## 2. Existing Project Audit & Baseline

### 2.1 Frontend Architecture
- **Framework & Build:** React 19 / Vite 8 with ESM bundling.
- **Routing:** React Router DOM v7 (`src/router.jsx`) with protected route guards for authentication and roles.
- **State Management:** Zustand stores:
  - `useAppStore.js`: Theme, UI state, active navigation.
  - `useSettingsStore.js`: Centralized configuration (event, alert thresholds, AI, FRS, notifications).
  - `useAlertStore.js`, `useCrowdStore.js`, `useSystemStore.js`.
- **API Client:** Axios instance (`src/services/apiClient.js`) configured with base URL, request interceptors (attaching Bearer JWT), and response interceptors (handling transparent 401 token refresh).
- **Core Pages:**
  - `Cameras.jsx`: Working channels divided into FRS Biometric and Crowd Surveillance sections.
  - `FRS.jsx`: Facial recognition investigation console, candidate review queue, and watchlist gallery.
  - `Crowd.jsx`: Real-time sector density, inflow/outflow, and threshold alerts.
  - `Settings.jsx`: Comprehensive settings panel with dedicated `AIConfigPanel` and `FRSConfigPanel`.
  - `SystemHealth.jsx`: Infrastructure gauges (CPU, RAM, GPU, service status).

### 2.2 Backend Architecture
- **Framework:** FastAPI with asynchronous lifespan lifecycle.
- **Data Access:** SQLAlchemy 2.0 async engine (`asyncpg`) connecting to Supabase PostgreSQL, paired with Alembic migrations.
- **Event Bus & Caching:** Redis async client (`redis.asyncio`) with channel constants (`byc:crowd`, `byc:alerts`, `byc:frs`, etc.). Operates in standalone in-memory fallback when Redis is absent.
- **WebSocket Gateway:** In-memory `ConnectionManager` at `/ws/v1/events` broadcasting real-time crowd, alert, and FRS events.
- **Existing AI Ingest Endpoint:** `POST /internal/v1/ai/events` guarded by `X-AI-Service-Key` header, validating worker submissions and routing to Redis/WebSockets.

### 2.3 Baseline Verification Results
- **Backend Tests:** 31 / 31 existing tests PASSED.
- **Frontend Build:** `npm run build` SUCCESS (dist generated with zero errors).
- **Database:** Supabase PostgreSQL operational, schema models resolved.
- **Redis:** Fallback mode functional without degradation of core REST operations.
- **WebSocket:** Connection and broadcasting verified.

---

## 3. Future AI Architecture & Step 1 Foundation

```
+-----------------------------------------------------------------------------------+
|                           Camera Ingestion Layer                                  |
|         RTSP / HLS / USB Webcams / Pre-recorded CCTV Stream Feeds                 |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                        AI Orchestrator (backend/app/ai/)                          |
|  [Step 1: Established Interface / Lifecycle Machine]   [Inference: NOT IMPLEMENTED]|
|                                                                                   |
|  +-----------------------+ +-----------------------+ +-------------------------+  |
|  |   Runtime Detector    | |  Capacity Calculator  | |     Profile Registry    |  |
|  | - CPU, RAM, Disk      | | - Dynamic VRAM Budget | | - CROWD_STANDARD        |  |
|  | - NVIDIA GPU & CUDA   | | - Stream Concurrency  | | - CROWD_HIGH_DENSITY    |  |
|  | - TensorRT/DeepStream | | - Bottleneck Analysis | | - QUEUE_STANDARD        |  |
|  | - Docker & Toolkit    | | [NOT IMPLEMENTED]     | | - FRS_STANDARD          |  |
|  +-----------------------+ +-----------------------+ | - VIDEO_SAFETY          |  |
|                                                      +-------------------------+  |
|  +-----------------------------------------------------------------------------+  |
|  |                      Pipeline Manager & State Machine                       |  |
|  | CREATED -> VALIDATING -> STARTING -> RUNNING -> STOPPING -> STOPPED        |  |
|  |                      DEGRADED -> FAILED -> RESTARTING                       |  |
|  +-----------------------------------------------------------------------------+  |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                      Unified Event & Telemetry Bus (Redis / WS)                   |
|                   AIPipelineLogger -> /ws/v1/events -> Frontend                   |
+-----------------------------------------------------------------------------------+
```

---

## 4. Module Specifications

### 4.1 AI Orchestrator (`backend/app/ai/orchestrator/`)
- **Role:** Central coordinator for pipeline startup, shutdown, pause, restart, and health checking.
- **Lifecycle Methods:**
  - `start(pipeline_id, profile_id)` [NOT IMPLEMENTED IN STEP 1 - Returns `NOT_IMPLEMENTED`]
  - `stop(pipeline_id)` [NOT IMPLEMENTED IN STEP 1 - Returns `NOT_IMPLEMENTED`]
  - `restart(pipeline_id)` [NOT IMPLEMENTED IN STEP 1 - Returns `NOT_IMPLEMENTED`]
  - `pause(pipeline_id)` [NOT IMPLEMENTED IN STEP 1 - Returns `NOT_IMPLEMENTED`]
  - `status(pipeline_id)` [NOT IMPLEMENTED IN STEP 1 - Returns `NOT_IMPLEMENTED`]
  - `health_check()` [NOT IMPLEMENTED IN STEP 1 - Returns `NOT_IMPLEMENTED`]

### 4.2 Central Pipeline State Machine (`PipelineState`)
A single, unified state machine governs Crowd, Queue, and FRS pipelines:
- `CREATED`: Pipeline entity registered in memory/DB.
- `VALIDATING`: Validating RTSP source, model file integrity, and GPU budget.
- `STARTING`: Initializing decoder, loading TensorRT/ONNX engine into VRAM.
- `RUNNING`: Streaming and inferring frames within target latency.
- `STOPPING`: Flushed frames, releasing GPU allocations.
- `STOPPED`: Cleanly halted.
- `DEGRADED`: Frame drops detected or FPS below SLA threshold.
- `FAILED`: Unrecoverable decoding, worker crash, or OOM event.
- `RESTARTING`: Automatic retry loop with exponential backoff.
- `UNKNOWN`: Uninitialized state.

### 4.3 AI Profiles (`backend/app/ai/profiles/`)
Standardized workload templates defining model parameters, GPU requirements, and camera specifications:

| Profile ID | Model Backbone | Target FPS | Min VRAM | Primary Features | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `CROWD_STANDARD` | YOLOv8n | 15 FPS | 1.5 GB | Headcount, flow direction, density | [SPECIFICATION ONLY] |
| `CROWD_HIGH_DENSITY` | YOLOv8x | 20 FPS | 4.0 GB | Sanctum dense crowd, bottleneck, panic | [SPECIFICATION ONLY] |
| `QUEUE_STANDARD` | YOLOv8s | 10 FPS | 2.0 GB | Queue length (meters), headcount, wait-time | [SPECIFICATION ONLY] |
| `FRS_STANDARD` | buffalo_l (512-D) | 12 FPS | 3.0 GB | Face detection, Cosine match, quality filter | [SPECIFICATION ONLY] |
| `VIDEO_SAFETY` | YOLOv8s-pose | 15 FPS | 2.5 GB | Person down, fall, barrier crossing | [SPECIFICATION ONLY] |

### 4.4 Runtime Detection Service (`backend/app/ai/runtime/`)
Safely inventories node capabilities without vendor assumptions:
- **CPU:** Logical cores, physical cores, model architecture, frequency, utilization via `psutil`.
- **Memory (RAM):** Total, available, used, percentage.
- **Storage:** Disk capacity and headroom for logs and media.
- **NVIDIA Accelerators:** Queries `nvidia-smi` in CSV mode. If absent or failing, safely returns `gpu_available: False` without raising exceptions.
- **Software Stacks:** Verifies Docker CLI, NVIDIA Container Toolkit (`nvidia-ctk`), TensorRT python runtime, and DeepStream SDK installation.

### 4.5 Capacity Calculation Engine (`backend/app/ai/capacity/`)
- **Role:** Formulates the mathematical concurrency limits of camera streams per node.
- **Rule:** Never returns hardcoded approximations (e.g. "25 cameras per GPU").
- **State in Step 1:** Returns `CAPACITY_CALCULATION_NOT_READY`. Live profiling, TensorRT engine benchmarking, and decode hardware metrics will be activated in Step 2+.

---

## 5. Database Schema Roadmap (Future Tables)

The following tables will be introduced in subsequent steps. They are documented here to prevent schema fragmentation:

1. `ai_profiles`: Stores customizable workload profiles.
2. `ai_deployments`: Maps cameras to specific AI profiles and hardware nodes.
3. `ai_pipeline_instances`: Tracks active worker processes, assigned PIDs/containers, and stream URIs.
4. `camera_ai_configs`: Per-camera inference overrides (detection thresholds, frame skip).
5. `camera_rois`: Regions of interest polygons for counting or exclusion.
6. `camera_counting_lines`: Bidirectional directional tripwires for entrance/exit counting.
7. `ai_server_capabilities`: Historical hardware and accelerator inventory per server.
8. `ai_capacity_snapshots`: Time-series log of capacity calculations and bottlenecks.
9. `ai_pipeline_health`: Live telemetry samples (actual FPS, latency, GPU temperature).
10. `ai_pipeline_events`: Audit log of state transitions (STARTING, DEGRADED, FAILED).

---

## 6. End-to-End Camera -> AI -> Event Telemetry Flow

```
[ CCTV RTSP Stream ]
         │
         ▼
[ Hardware Video Decoder (NVDEC / CPU FFmpeg) ]
         │
         ▼
[ Preprocessing & Scaling (Letterbox / Normalization) ]
         │
         ▼
[ Inference Backbone (TensorRT / ONNX) ] ─── [ Profile: Confidence Threshold ]
         │
         ▼
[ Object Tracking (ByteTrack / SORT) ]
         │
         ▼
[ Business Logic & Analytics ] ─── (Headcount, Line Cross, Face Embedding)
         │
         ▼
[ AIPipelineLogger & Event Dispatcher ]
         │
         ├───> [ Internal Ingestion: POST /internal/v1/ai/events ]
         │           │
         │           ▼
         ├───> [ Redis Pub/Sub: byc:crowd / byc:frs / byc:alerts ]
         │           │
         │           ▼
         └───> [ WebSocket Gateway: /ws/v1/events ]
                     │
                     ▼
               [ React Web Portal UI: Live Dashboard & Alarms ]
```

---

## 7. API Design & Security

All AI foundation endpoints are located under `/api/v1/ai` and protected with JWT Bearer authentication and RBAC permissions:

- `GET /api/v1/ai/system/capabilities`: Returns hardware inventory, CPU, RAM, GPU, and stack readiness.
- `GET /api/v1/ai/system/capacity`: Returns capacity calculator readiness status.
- `GET /api/v1/ai/profiles`: Lists registered standard AI profiles.
- `GET /api/v1/ai/deployments`: Lists active camera AI deployments (empty in Step 1).
- `GET /api/v1/ai/pipelines`: Lists active pipeline instances (empty in Step 1).
- `GET /api/v1/ai/health`: Real-time health metrics across DB, Redis, and compute nodes.

---

## 8. Verification Matrix

| Verification Check | Target | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| Existing Tests | 31 / 31 | 31 / 31 Passed | PASS |
| Foundation Tests | 16 / 16 | 16 / 16 Passed | PASS |
| Total Pytest Suite | 47 / 47 | 47 / 47 Passed (100%) | PASS |
| Frontend Build | Vite 8.2 | Built in 889ms, 0 errors | PASS |
| Backend Core | FastAPI | Port 8000 operational | PASS |
| Database | PostgreSQL | Supabase pooler connected | PASS |
| Redis | Event Bus | Standalone fallback mode verified | PASS |
| WebSocket | /ws/v1/events | Connected & broadcasting verified | PASS |

---

## 9. Step 3: Camera Onboarding & RTSP Stream Management

Step 3 introduces the physical video ingestion foundation. It establishes the bridge between physical IP surveillance cameras and future AI orchestration pipelines without starting any inference prematurely.

### 9.1 Camera Data Architecture & Credential Security
Cameras are stored in the PostgreSQL `cameras` table and represented by the `Camera` model:
- **Sensitive Credentials**: RTSP passwords and authenticated URLs are encrypted at rest using `cryptography.fernet.Fernet` derived from `settings.JWT_SECRET_KEY` (or dedicated `CAMERA_ENCRYPTION_KEY`).
- **Zero Leakage**: Camera passwords are never returned in `CameraRead` responses, never printed in server logs, never emitted over WebSockets, and never stored in frontend localStorage.
- **RTSP URL Sanitization**: URLs are sanitized via `sanitize_rtsp_url()` (e.g. `rtsp://admin:***@192.168.0.102:554/...`) for display and logging.

### 9.2 RTSP Stream Probe Service (`RTSPTestService`)
- Uses host `ffprobe` (FFmpeg 8.1) with `-rtsp_transport tcp` and strict timeouts (default: 6.0 seconds).
- Probes resolution, FPS, video codec, and network latency.
- Guaranteed cleanup: Process trees are immediately terminated on timeout or connection failure, preventing zombie processes.
- Standardized error classification:
  - `CAMERA_NOT_FOUND`
  - `INVALID_RTSP_URL`
  - `NETWORK_UNREACHABLE`
  - `RTSP_CONNECTION_FAILED`
  - `RTSP_AUTH_FAILED`
  - `STREAM_NOT_FOUND`
  - `UNSUPPORTED_CODEC`
  - `NO_VIDEO_TRACK`
  - `STREAM_TIMEOUT`
  - `FFPROBE_UNAVAILABLE`
  - `UNKNOWN_STREAM_ERROR`

### 9.3 Stream Health States & Lifecycle
- `ONLINE`: Stream reachable, video decodable, FPS output active.
- `DEGRADED`: Stream reachable but low FPS, high latency, or intermittent probe failure.
- `OFFLINE`: Stream unavailable or host unreachable.
- `NOT_TESTED`: Newly registered camera before its first RTSP test.
- `UNKNOWN`: Uninitialized state.

### 9.4 Camera Purpose & Zone Association
- **Primary Operational Zone**: Every camera is linked via foreign key to a primary zone (`zones.id` / `zone_code`) for precinct tracking.
- **Intended Purpose**: Defines future AI workload suitability (`CROWD`, `QUEUE`, `FRS`, `GENERAL`, `MULTI_PURPOSE`). No AI inference is started during onboarding.

---

## 10. Step 4: AI Profile → Camera Assignment & Capacity Validation

Step 4 establishes the production configuration layer allowing authorized operators to assign AI workload profiles to onboarded cameras with real-time hardware capacity verification.

```
+-----------------------------------------------------------------------------------+
|                           CAMERA AI WORKLOAD CONFIGURATION                         |
|                                                                                   |
|  [Onboarded Camera] ---> [AI Profile Selection] ---> [Pre-Flight Validation Engine]|
|         |                        |                                |               |
|         |                        v                                v               |
|         |              +-------------------+             +--------------------+   |
|         |              | Purpose Match     |             | Dynamic Capacity   |   |
|         |              | FRS Authorization |             | Resource Headroom  |   |
|         |              +-------------------+             +--------------------+   |
|         |                                                         |               |
|         v                                                         v               |
|  +-----------------------------------------------------------------------------+  |
|  |           [Configuration Saved to camera_ai_profile_assignments]            |  |
|  |                  (State: ASSIGNED / ENABLED / HEALTHY)                      |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|                                         | (NO INFERENCE PROCESSES STARTED)        |
|                                         v                                         |
|               [Future Step: AI Orchestrator Pipeline Lifecycle]                   |
+-----------------------------------------------------------------------------------+
```

### 10.1 Persistent Database Model (`CameraAIProfileAssignment`)
Stored in the PostgreSQL `camera_ai_profile_assignments` table:
- `id` (UUID, Primary Key)
- `camera_id` (UUID, Foreign Key -> `cameras.id` with CASCADE delete)
- `camera_code` (String, Indexed)
- `profile_id` (String, Standard Profile Enum: `CROWD_STANDARD`, `CROWD_HIGH_DENSITY`, `QUEUE_STANDARD`, `FRS_STANDARD`, `VIDEO_SAFETY`)
- `enabled` (Boolean, Default: True)
- `metadata_json` (JSONB, custom thresholds like confidence, min_face_size)
- `assigned_at` (Timestamp UTC)
- `assigned_by` (String, Username)
- `validation_status` (String: `HEALTHY`, `WARNING`, `LIMIT_REACHED`, `OVER_CAPACITY`)
- `validation_message` (Text, Explaining capacity or status reason)
- **Unique Constraint**: `(camera_id, profile_id)` strictly prevents duplicate assignments of the same profile on any camera.

### 10.2 Server-Side Compatibility Rules
Assignments are strictly validated against the camera's operational purpose:
| Camera Purpose | Allowed Standard AI Profiles |
| :--- | :--- |
| `CROWD` | `CROWD_STANDARD`, `CROWD_HIGH_DENSITY` |
| `QUEUE` | `QUEUE_STANDARD` |
| `FRS` | `FRS_STANDARD` |
| `GENERAL` | `VIDEO_SAFETY` |
| `MULTI_PURPOSE` | `CROWD_STANDARD`, `CROWD_HIGH_DENSITY`, `QUEUE_STANDARD`, `FRS_STANDARD`, `VIDEO_SAFETY` |

Attempting to assign an incompatible profile (e.g. `FRS_STANDARD` on a `CROWD` camera) immediately returns HTTP 422 Unprocessable Content (`AI_PROFILE_NOT_COMPATIBLE`).

### 10.3 Strict FRS Biometric Isolation
Facial Recognition Technology (FRS) carries strict operational and regulatory isolation:
1. **Camera Purpose Restriction**: May ONLY be assigned to cameras designated as `FRS` or `MULTI_PURPOSE`.
2. **RBAC Permission Gate**: The configuring operator must possess FRS permissions (`Permissions.FRS_MANAGE`, `Permissions.FRS_REVIEW`, or `Permissions.FRS_READ`), or be `SUPER_ADMIN`.
3. Rejection with HTTP 403 Forbidden (`FRS_ASSIGNMENT_NOT_AUTHORIZED`) occurs if unauthorized personnel attempt FRS assignment.

### 10.4 Pre-Flight Dynamic Capacity Validation
Before any profile assignment is persisted:
1. Calculates active workload across all enabled camera assignments in the deployment.
2. Simulates adding the requested profile workload (`requested_addition`).
3. Invokes `CapacityCalculator.validate_capacity_for_deployment()`.
4. If projected usage exceeds the server's hard ceilings (`hard_max_gpu_percent`, `hard_max_vram_percent`, `hard_max_cpu_percent`, `hard_max_ram_percent`):
   - Assignment is strictly BLOCKED with HTTP 409 Conflict (`AI_CAPACITY_EXCEEDED`).
   - Rejection is recorded to `AuditLog` (`AI_PROFILE_ASSIGNMENT_REJECTED`).
   - Real-time notification emitted via WebSockets.

### 10.5 Audit Trail & WebSocket Telemetry
- **Audit Logging**: Successful assignments create `AuditLog` records with action `AI_PROFILE_ASSIGNED`; updates create `AI_PROFILE_UPDATED`; removals create `AI_PROFILE_REMOVED`.
- **WebSocket Broadcast**: Emits `AI_CONFIGURATION_CHANGED` event on the `ai` channel to notify connected frontend clients and future orchestrator instances in real time.

### 10.6 STRICT INVARIANT: Non-Inference Configuration
Saving an AI profile configuration configures intended deployment state only. It does **NOT** spawn DeepStream pipelines, load model weights, or start inference subprocesses. AI lifecycle execution remains exclusively decoupled to the Orchestrator stage.

---

## 11. Visual ROI & Counting-Line Configuration (Step 5)

The Visual ROI and Geometry Configuration subsystem provides a production-grade, human-operator-driven visual interface and REST backend for establishing spatial analytical boundaries on real camera streams.

### 11.1 Key Architecture & Data Model
Spatial geometries are persisted in the `camera_roi_configurations` table via the `CameraROIConfiguration` model:
- `id` (UUID Primary Key)
- `camera_id` (Foreign Key -> `cameras.id`)
- `camera_code` (Indexed lookup)
- `profile_id` (Associated AI workload profile, e.g. `CROWD_STANDARD`, `QUEUE_STANDARD`)
- `roi_type` (Enum: `CROWD_ROI`, `QUEUE_ROI`, `ENTRY_LINE`, `EXIT_LINE`, `DIRECTION_LINE`, `EXCLUSION_ZONE`, `SAFETY_BOUNDARY`)
- `name` (Operator label, e.g. "East Gate Courtyard Density Zone")
- `geometry_json` (Normalized coordinate dictionary):
  - Polygons: `{"points": [{"x": 0.12, "y": 0.20}, ...]}`
  - Lines: `{"start": {"x": 0.1, "y": 0.2}, "end": {"x": 0.8, "y": 0.2}, "direction": "IN"}`
- `normalized` (Boolean, strictly `True`)
- `enabled` (Boolean active flag)
- `version` (Integer configuration version, incremented on each geometry modification)
- `created_by` / `updated_by` (Username audit attribution)
- `created_at` / `updated_at` (UTC timestamps)

### 11.2 Coordinate System & Resolution Independence
All coordinates stored in the database are strictly normalized:
$$0.0 \le x \le 1.0, \quad 0.0 \le y \le 1.0$$
- This guarantees complete resolution independence: if a camera stream switches between 1080p, 720p, or 4K, all ROI boundaries scale with pixel accuracy.
- Coordinates outside $[0.0, 1.0]$ are immediately rejected with HTTP 422 (`ROI_COORDINATE_OUT_OF_RANGE`).
- Polygons require a minimum of 3 distinct non-collinear vertices (`ROI_TOO_FEW_POINTS`).
- Counting lines require distinct start and end endpoints (`COUNTING_LINE_INVALID`).

### 11.3 Profile Compatibility & Readiness Lifecycle Engine
Geometries are strictly validated against the target profile:
| Profile | Allowed ROI Types | Required for "READY" Status |
| :--- | :--- | :--- |
| `CROWD_STANDARD` / `CROWD_HIGH_DENSITY` | `CROWD_ROI`, `EXCLUSION_ZONE`, `COUNTING_LINE` | At least 1 `CROWD_ROI` polygon |
| `QUEUE_STANDARD` | `QUEUE_ROI`, `ENTRY_LINE`, `EXIT_LINE`, `DIRECTION_LINE`, `EXCLUSION_ZONE` | At least 1 `QUEUE_ROI` polygon, 1 `ENTRY_LINE`, and 1 `EXIT_LINE` |
| `VIDEO_SAFETY` | `SAFETY_BOUNDARY`, `EXCLUSION_ZONE`, `COUNTING_LINE` | At least 1 `SAFETY_BOUNDARY` |
| `FRS_STANDARD` | *None* | Biometric FRS profiles strictly reject crowd/queue geometry (`ROI_PROFILE_MISMATCH`) |

#### Readiness States
1. `NOT_CONFIGURED`: No geometry has been created for the profile.
2. `PARTIALLY_CONFIGURED`: Some geometry exists, but mandatory requirements are missing (e.g. Queue ROI defined but Entry/Exit lines missing).
3. `READY`: All mandatory spatial requirements are satisfied. The configuration is ready for future pipeline orchestrator execution.
4. `INVALID`: Invalid geometry structure or incompatible profile mapping.

### 11.4 Real Stream Snapshot Capture & Security
- Real JPEG frames are captured via `SnapshotService.capture_frame(camera)` using `ffmpeg -rtsp_transport tcp -stimeout 5000000 -frames:v 1 -f image2pipe -vcodec mjpeg -`.
- Frames are cached in-memory with a 5-second TTL to minimize RTSP transport overhead.
- Strictly rejects offline cameras (`CAMERA_OFFLINE`) and unverified streams (`CAMERA_STREAM_NOT_VERIFIED`).
- Passwords and RTSP connection tokens are never exposed in snapshot URLs, responses, or logs.

### 11.5 Operator Visual Editor
The frontend `ROIEditor.jsx` component provides:
- Live real-frame canvas with dynamic SVG geometry overlay.
- Polygon creation (click-to-add vertices, double-click to close).
- Vertex dragging with live normalized coordinate readout.
- Entry/Exit counting line drawing with customizable flow arrows.
- Undo, redo, vertex reset, and pre-flight dry-run validation (`POST /api/v1/cameras/{id}/roi-config/validate`).
- Prominent disclaimers reinforcing that saving ROI configurations does **NOT** start AI video inference.

---

## 12. Crowd AI Real-Time Detection, Tracking & Analytics Pipeline

### 12.1 Pipeline Lifecycle & Execution Boundaries
The Crowd AI Pipeline operates as an isolated asynchronous execution loop (`CrowdPipeline`) decoupling stream ingestion, tensor inference, and stateful tracking:
1. **Pre-flight Enforcement**: A pipeline can ONLY start if:
   - Camera is `VERIFIED` and `online`.
   - Camera has an active `CROWD_STANDARD` or `CROWD_HIGH_DENSITY` AI profile assignment.
   - Spatial boundaries (`CROWD_ROI`) are configured with $\ge 3$ vertices.
   - Host platform has NVIDIA GPU and DeepStream runtime (explicitly returning `400 RUNTIME_UNAVAILABLE` on unsupported hosts without fake inference).
   - Server capacity calculator verifies that GPU VRAM, GPU Load, and CPU headroom remain strictly within safe operating envelopes (returning `409 AI_CAPACITY_EXCEEDED` otherwise).
2. **Model Registry**:
   - `CROWD_STANDARD`: YOLOv8n-Crowd, 640x640 input, 15 FPS target.
   - `CROWD_HIGH_DENSITY`: YOLOv8x-Crowd, 1280x1280 input, 20 FPS target.
   - Detections are filtered strictly for Class 0 (`person`). Zero biometric, face, or queue inference is permitted in the crowd pipeline.
3. **Spatial Geometries & Tracking**:
   - Bottom-center bounding box anchoring: $(x_{\text{mid}}, y_{\text{max}})$.
   - Ray-casting Point-in-Polygon testing with exclusion zone subtraction.
   - Multi-object tracking with transient identifiers (`TRK-xxxx`) and trajectory histories (up to 60 points).
   - 2D vector cross-product line crossing detection (`IN` / `OUT`) with 5-second anti-repetition cooldowns.
4. **Deterministic Risk Scoring & Cooldown**:
   - Formula: $R = \min(100.0, \, 0.50 \cdot S_{\text{density}} + 0.30 \cdot S_{\text{rate}} + 0.20 \cdot S_{\text{accel}})$.
   - Event alerts emitted with 60-second duplicate suppression per camera and event type.
5. **Observability & Fault Tolerance**:
   - Ingestion and processed FPS tracking, dropped frame detection, and 10-second no-frame timeouts triggering `FAILED` pipeline state.
   - WebSocket broadcast (`ws/live` and event bus) for real-time operator situational awareness.
   - Secure RTSP credential isolation (passwords never exposed in APIs, metrics, or logs).

---

## 13. Queue AI Real-Time Detection, Tracking & Analytics Pipeline

### 13.1 Pipeline Lifecycle & Execution Boundaries
The Queue AI Pipeline operates as an isolated asynchronous execution loop (`QueuePipeline`) monitoring queue channels, barricaded lines, and pedestrian flow:
1. **Pre-flight Prerequisites**:
   - Camera must be `VERIFIED` and `online`.
   - Camera must have an active `QUEUE_STANDARD` AI profile assignment.
   - Spatial prerequisites require **all three mandatory geometries**: `QUEUE_ROI` ($\ge 3$ vertices), `ENTRY_LINE`, and `EXIT_LINE`. Missing geometries return `400 QUEUE_CONFIGURATION_NOT_READY`.
   - Hardware runtime check: host must possess NVIDIA GPU with DeepStream/CUDA runtime; unsupported development hosts cleanly return `400 RUNTIME_UNAVAILABLE` without emitting fictitious queue metrics.
   - Server capacity check: `CapacityCalculator` ensures mixed-workload safety margins across active Crowd and Queue pipelines, rejecting launches with `409 AI_CAPACITY_EXCEEDED` when GPU VRAM or compute limits are reached.

### 13.2 Model Registry & Class 0 Isolation
- Profile: `QUEUE_STANDARD` with `yolov8s-queue` (TensorRT optimized engine).
- Target Frame Rate: 10 FPS (optimal for walking speed and queuing dynamics).
- Confidence Threshold: 0.50.
- Class Isolation: Strictly COCO Class 0 (`person`). All non-person detections are discarded.
- **Zero Biometric / FRS Isolation**: No face detection, facial crops, face embeddings, or identity matching exist in the queue pipeline.

### 13.3 Spatial Analytics & Mathematical Formulations
- **Bottom-Center Anchoring**: Person reference points are strictly grounded at $(x_{\text{mid}}, y_{\text{max}})$ to eliminate perspective tilt errors.
- **Spatial Filtering**: Ray-casting Point-in-Polygon containment for `QUEUE_ROI` with automatic deduction of `EXCLUSION_ZONE` polygons.
- **Occupancy Percentage**: Headcount divided by configured `queue_capacity`. Returns `UNAVAILABLE` and `None` if unconfigured.
- **Calibrated & Relative Density**: Persons per square meter ($\text{persons/m}^2$) when `physical_area_m2` is provided, otherwise relative density.
- **Queue Length Extents**: Diagonal bounding span of queued individuals, scaled to meters when `physical_length_meters` calibration is set.
- **Inflow & Outflow Flow Rates**: 2D line segment crossing detection on Entry and Exit lines with 5-second duplicate suppression per track ID, normalized to persons per minute.
- **Queue Direction Vector**: Analyzes track movement vectors against entry-to-exit flow: `FORWARD`, `BACKWARD` (surges or panic), or `UNKNOWN`.
- **Transient Dwell / Waiting Time Engine**: In-memory tracking of queue dwell times; calculates average, median, and maximum dwell upon exit line crossing or departure. Returns `insufficient_data` when samples are below 1.

### 13.4 Deterministic Queue Risk Engine
Queue risk $R \in [0, 100]$ is computed deterministically:
$$R = \min\left(100.0, \, 0.35 \cdot S_{\text{occ}} + 0.30 \cdot S_{\text{wait}} + 0.20 \cdot S_{\text{inflow}} + 0.15 \cdot S_{\text{growth}} + P_{\text{backward}}\right)$$
- Categorical levels: `LOW` ($<40$), `MEDIUM` ($40-69$), `HIGH` ($70-84$), and `CRITICAL` ($\ge 85$).

### 13.5 Event Generation & Cooldown Suppression
Emits structured events (`QUEUE_THRESHOLD_EXCEEDED`, `QUEUE_RISK_HIGH`, `QUEUE_RISK_CRITICAL`, `QUEUE_INFLOW_SPIKE`, `QUEUE_WAIT_TIME_HIGH`, `QUEUE_GROWTH_SPIKE`) with a 60-second cooldown window per camera and event type.

### 13.6 Multi-Camera Zone Summaries & Security
- `QueuePipelineRegistry` aggregates queue counts, peak risk levels, and weighted wait times across all cameras in a zone.
- RTSP credentials decrypted for streaming are masked in string representations and never leaked via endpoints or logs.
- RBAC permissions `queue:read` and `queue:manage`/`ai:manage` protect telemetry and pipeline controls.

---

## 14. AI Orchestration & Multi-Camera Pipeline Management Control-Plane

### 14.1 Architecture & Control Decoupling
The AI Orchestrator (`app/ai/orchestrator/service.py`) coordinates multi-camera execution across both Crowd AI and Queue AI registries. It strictly separates:
- **Desired State (`desired_state`)**: Operator intent persisted in PostgreSQL (`AIPipelineDeployment`), defining whether the pipeline should be `RUNNING` or `STOPPED`.
- **Actual Runtime State (`actual_state`)**: Real engine reality (`CREATED`, `VALIDATING`, `STARTING`, `RUNNING`, `DEGRADED`, `STOPPING`, `STOPPED`, `FAILED`, `RESTARTING`).
- **Health Telemetry State (`health_state`)**: Operational health (`HEALTHY`, `DEGRADED`, `FAILED`, `UNKNOWN`, `STOPPED`).

### 14.2 Pre-Flight Validation Matrix
Prior to state transition to `STARTING`, every deployment must satisfy 6 rigorous pre-flight validations:
1. Camera status is `online` and `enabled`.
2. RTSP stream status is `VERIFIED`.
3. An active AI profile assignment is linked.
4. Required geometric boundaries are present (`CROWD_ROI` polygon for Crowd AI; `QUEUE_ROI`, `ENTRY_LINE`, `EXIT_LINE` for Queue AI).
5. Hardware runtime exists (clean rejection with `400 RUNTIME_UNAVAILABLE` on unsupported hosts without emitting synthetic metrics).
6. Dynamic mixed-workload capacity headroom is confirmed via `CapacityCalculator` (`409 AI_CAPACITY_EXCEEDED` on projected resource exhaustion).

### 14.3 Automated Fault Recovery & Self-Healing
- **RTSP Dropout Recovery**: Background supervision loop (5s interval) detects stalls (>10s without frame). Transitions `actual_state` to `DEGRADED` and initiates exponential backoff reconnects ($2\text{s} \to 4\text{s} \to 8\text{s} \to 16\text{s} \to 30\text{s}$, max 5 attempts) until restored to `RUNNING` or escalated to `FAILED`.
- **Circuit Breaker Retry Throttling**: Limits automatic restart attempts to a maximum of 3 restarts within a sliding 10-minute window. Prevents infinite crash loops, locking `actual_state` to `FAILED` with `AI_PIPELINE_RECOVERY_EXHAUSTED`.
- **Server Restart Staggered Recovery**: FastAPI lifespan automatically queries deployments where `desired_state == RUNNING` upon reboot and recovers pipelines in staggered batches of 2 with 2-second inter-batch pauses to eliminate hardware current inrush spikes.

### 14.4 Fleet Orchestration & Priority Scheduling
- **Start All Fleet Algorithm**: Sorts deployments by operator priority (`CRITICAL` $\to$ `HIGH` $\to$ `NORMAL` $\to$ `LOW`), breaking ties by `camera_code` ascending. Concurrently deploys pipelines until hardware capacity ceiling is reached, marking remaining pipelines as `BLOCKED` with explicit resource bottleneck diagnostics.
- **Graceful Stop All**: Concurrently flushes inference buffers and tears down active pipelines across both `CrowdPipelineRegistry` and `QueuePipelineRegistry`, updating all desired states to `STOPPED`.

### 14.5 Operator Console & Audit Logging
- **Frontend Dashboard (`AIDeployment.jsx`)**: Dual-tab interface providing fleet-wide status ribbons, mass Start/Stop controls, live state/health badges, runtime instance IDs, and dynamic capacity utilization meters.
- **Security & RBAC**: All write actions enforce `ai:manage` permission; viewer accounts receive `403 Forbidden`. Every lifecycle event generates an immutable `AuditLog` row with operator credentials and runtime tracking IDs.

---

## 15. FRS Face Detection, Candidate Matching & Human Review Pipeline

> [!IMPORTANT]
> **Safety & Operational Rule:**
> FRS produces candidate matches for authorized human review. It does NOT automatically confirm identity, declare suspects, or trigger police/enforcement action. Every match remains `CANDIDATE` / `REVIEW_REQUIRED` until an authorized reviewer explicitly decides.

### 15.1 Biometric Isolation & Camera Restrictions
- **Strict Isolation**: FRS operates independently from Crowd and Queue pipelines. Zero shared tracking IDs (`TRK-xxxx`), zero routing through Crowd/Queue risk engines, zero impact on Crowd/Queue headcounts.
- **Camera Purpose Gate**: FRS is restricted exclusively to cameras where `camera_type` is `FRS` or `MULTI_PURPOSE` and `profile_id == "FRS_STANDARD"` is assigned. Rejection on `CROWD`, `QUEUE`, or `GENERAL` cameras is enforced at the orchestrator API boundary.

### 15.2 Modular Pipeline Architecture (`app/ai/pipelines/frs/`)
1. **RTSP Stream Ingestion**: Clean decryption of camera credentials; URLs are masked in logs and telemetry (`rtsp://***:***@...`).
2. **Face Detection**: High-accuracy SCRFD 10G / InsightFace model extracting bounding box, confidence, and 5-point facial landmarks.
3. **Face Quality Gate (`quality.py`)**: Multi-factor validation checking resolution ($\ge 60\text{px}$), sharpness (Laplacian variance $\ge 50.0$), brightness ($40 \le \mu \le 220$), and pose ($|\text{yaw}| \le 45^\circ$, $|\text{pitch}| \le 30^\circ$). Faces failing quality standards are rejected as `FACE_QUALITY_INSUFFICIENT` without candidate generation.
4. **512-D Embedding Engine (`embedding.py`)**: ArcFace ResNet-50 deep feature extractor producing L2-normalized 512-dimensional vectors.
5. **Active Gallery Matcher (`matcher.py`)**: Cosine similarity search against active reference profiles in `FRSReferenceProfile`, ranking Top-K candidates (default Top 3) with margin analysis.
6. **Temporal Duplicate Suppression (`events.py`)**: Suppresses repetitive candidate alerts for the same camera and reference person within a sliding 60-second window.
7. **Human Review Governance**: Every match creates an `FRSCandidate` in `REVIEW_REQUIRED` status. Authorized officers (`frs:review`) make explicit decisions: `CONFIRMED_BY_REVIEWER`, `REJECTED_BY_REVIEWER`, or `UNRESOLVED`. Every review decision emits an immutable `FRSAuditLog` entry and sanitized event bus notification.
8. **Retention & Privacy Lifecycle**: Configurable retention (default 30 days) automatically purges candidate events and cropped face images while preserving all historical audit logs. Raw embeddings and credentials are never exposed via REST or WebSocket payloads.


