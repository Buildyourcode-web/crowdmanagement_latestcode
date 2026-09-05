# Crowd AI: Real-Time Detection, Tracking & Spatial Analytics

## 1. Overview & Scope
The **Crowd AI Pipeline** is the real-time computer vision subsystem of the BYC AI Platform responsible for monitoring crowd levels, spatial distribution, directional flow, and congestion risks at the Khairatabad Ganesh festival.

### Scope Boundaries
- **Strictly In Scope**: Person detection (Class 0), multi-object tracking, spatial Point-in-Polygon analytics, relative & calibrated density estimation, directional line crossing (inflow/outflow), deterministic crowd risk scoring, event cooldown suppression, and pipeline health telemetry.
- **Strictly Out of Scope**: Queue analytics (Step 7), Facial Recognition / Biometrics / FRS (Step 8), automatic law-enforcement actions, medical triage, or LLMs in real-time control loops.

---

## 2. Hardware & Runtime Requirements

| Component | Minimum Specification | Recommended Specification |
|---|---|---|
| **GPU** | NVIDIA Turing / Ampere (e.g. RTX 3050/3060, T4) | NVIDIA Ampere / Ada (e.g. RTX 4080/4090, A10, A30) |
| **VRAM** | 4 GB VRAM (for YOLOv8n) | 8 GB+ VRAM (for YOLOv8x) |
| **CUDA / Driver** | CUDA 12.x / 13.x, Driver >= 535 | CUDA 12.x / 13.x, Driver >= 550 |
| **DeepStream SDK** | NVIDIA DeepStream 6.3+ / 7.0+ | NVIDIA DeepStream 7.0+ Containerized |
| **CPU Fallback** | Not supported for production inference | Host without DeepStream explicitly reports RUNTIME_UNAVAILABLE |

### Profile Configurations
- **CROWD_STANDARD**:
  - Target: General pandal courtyards and open circulation zones.
  - Model: yolov8n-crowd (640x640 input resolution).
  - Target Frame Rate: 15 FPS (Process 1 in 2 frames from 30 FPS RTSP).
  - Confidence Threshold: 0.45.
  - Resource Budget: ~0.45 GB VRAM, ~3.5% GPU load.
- **CROWD_HIGH_DENSITY**:
  - Target: Core sanctum sanctorum and narrow barricaded corridors.
  - Model: yolov8x-crowd (1280x1280 input resolution).
  - Target Frame Rate: 20 FPS.
  - Confidence Threshold: 0.35.
  - Resource Budget: ~1.20 GB VRAM, ~8.0% GPU load.

---

## 3. Architecture & Data Flow

`
[IP Camera / RTSP H.264 Stream]
               │ (TCP transport, encrypted credentials)
               ▼
   [CrowdPipeline (Async Loop)]
               │
               ▼
   [PersonDetector (DeepStream / YOLO TensorRT)]
               │ Detections: Class 0 (person only), bbox: [x1, y1, x2, y2]
               ▼
   [PersonTracker (IoU + Centroid Association)]
               │ Transient IDs: TRK-0001, trajectory history (60 pts)
               ▼
   [CrowdSpatialAnalytics (Ray-Casting Algorithm)]
         ├── Point-in-Polygon (Bottom-Center Bounding Box Reference)
         ├── Exclusion Zone Subtraction
         ├── Density Estimation (Relative & Calibrated persons/m²)
         └── Directional Line Crossing (2D Vector Cross Product)
               │
               ▼
   [CrowdRiskEngine (Deterministic Multi-Factor Scoring)]
               │ Score: 0 - 100, Level: LOW / MODERATE / HIGH / CRITICAL
               ▼
   [CrowdEventEngine (Cooldown Alert Generation)]
               │ 60s suppression window per camera & event type
               ▼
   [Event Bus / WebSocket Telemetry & Snapshot Persistence]
`

---

## 4. Spatial Geometry & Coordinate Space

1. **Normalized Coordinate System**:
   - All spatial coordinates (points, start, end) are strictly normalized floats:
     0.0 <= x <= 1.0, 0.0 <= y <= 1.0
   - Resolution-independent: immune to RTSP stream resolution shifts (720p / 1080p / 4K).

2. **Reference Point Formulation**:
   - People in 2D perspective views are grounded at their feet.
   - Using the bounding box center or top creates perspective distortion near camera foreground.
   - The reference point (Px, Py) is strictly the **bottom-center** of the bounding box:
     Px = (xmin + xmax) / 2, Py = ymax

3. **Ray-Casting Polygon Containment**:
   - A ray is cast horizontally from (Px, Py) to positive infinity.
   - The number of intersecting polygon edges is counted. An odd number indicates the person is inside the ROI.
   - Persons whose reference point falls inside configured EXCLUSION_ZONE polygons are subtracted from the headcount.

---

## 5. Directional Line Crossing Math

Line crossings for Entry/Exit counting lines use 2D vector cross-product math between the person's consecutive trajectory points (A -> B) and the configured line segment (L1 -> L2):

1. **Segment Intersection**:
   Two segments intersect if and only if points A and B lie on opposite sides of line L1-L2, and points L1 and L2 lie on opposite sides of line AB.

2. **Direction Determination**:
   Vector v_line = L2 - L1 and vector v_mov = B - A.
   Cross_z = (v_line.x * v_mov.y) - (v_line.y * v_mov.x)
   - Cross_z > 0: Classified as IN.
   - Cross_z < 0: Classified as OUT.

3. **Duplicate Prevention**:
   - Once a track ID triggers a line crossing event on a given line, the crossing is logged with the track ID.
   - The track is inhibited from triggering the same line crossing again until it leaves the line boundary zone for at least 5 seconds.

---

## 6. Multi-Object Tracking & Transient Identifiers

- **Tracking Algorithm**: Intersection-over-Union (IoU) tracker with spatial Kalman filtering and trajectory history window (60 frames).
- **Identifier Policy**:
  - Tracking IDs are strictly **transient** integers formatted as TRK-xxxx (e.g. TRK-0501).
  - IDs are scoped strictly to the active pipeline session in-memory.
  - **Zero Biometric Linkage**: IDs are NEVER linked to face recognition embeddings, person re-identification databases, or citizen records.
  - Expired tracks (not matched for 30 consecutive frames) are permanently purged from memory.

---

## 7. Deterministic Crowd Risk Calculation

The crowd risk score (R in [0, 100]) is computed purely deterministically without non-deterministic LLM or probabilistic heuristics:

R = min(100.0, w_density * S_density + w_rate * S_rate + w_accel * S_accel)

### Default Weights
- w_density = 0.50 (50% weight on absolute/calibrated density).
- w_rate = 0.30 (30% weight on net inflow rate).
- w_accel = 0.20 (20% weight on sudden surge acceleration).

### Severity Classification
- **LOW**: 0 <= R < 40 (Normal flow)
- **MODERATE**: 40 <= R < 70 (Elevated presence, stable flow)
- **HIGH**: 70 <= R < 85 (Dense congestion, restricted movement)
- **CRITICAL**: 85 <= R <= 100 (Crush danger, queue stoppage, requires immediate marshal intervention)

---

## 8. Event Generation & Cooldown Suppression

When risk or density crosses threshold boundaries, the CrowdEventEngine emits structured events:
- CROWD_RISK_HIGH / CROWD_RISK_CRITICAL
- CROWD_THRESHOLD_EXCEEDED
- CROWD_SURGE_DETECTED

### Cooldown Policy
To prevent notification flooding during ongoing congestion, an event with the same (camera_code, event_type) is suppressed if emitted within the previous **60 seconds**. Once the 60-second window expires and conditions remain critical, a recurring notification is permitted.

---

## 9. Pipeline Health & Fault Tolerance

The PipelineHealthMonitor continuously inspects pipeline health metrics:
- **Input FPS vs Processed FPS**: Detects RTSP dropouts or inference backpressure.
- **Inference Latency**: Tracks YOLO inference time (target: < 25 ms).
- **No-Frame Timeout**: If no frame is received from the RTSP source for >= 10.0 seconds, the pipeline automatically transitions to FAILED health status with reason Stream timeout: no frames received in >10s.
- **Resource Deallocation**: When stopped via POST /api/v1/crowd/pipelines/{camera_id}/stop, the video capture thread is terminated, GPU memory buffers are flushed, and the camera status is restored to VERIFIED.

---

## 10. Security & Privacy Guarantees

1. **Credential Sanitization**:
   RTSP credentials (usernames, passwords) are encrypted in the database using Fernet symmetric encryption (tsp_url_encrypted). They are decrypted strictly inside internal pipeline memory and NEVER included in logs, metrics payloads, or health responses.
2. **Role-Based Access Control (RBAC)**:
   - Starting / stopping pipelines requires the i:manage permission (ADMIN or SUPERADMIN).
   - Viewing live metrics and health requires the crowd:read permission (OPERATOR, POLICE_LEAD, VIEWER).
3. **Audit Trail**:
   Every pipeline start, stop, or capacity rejection is immutably logged to the udit_logs table with user ID, client IP, camera code, and timestamp.
