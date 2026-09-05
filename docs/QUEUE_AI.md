# Queue AI: Real-Time Detection, Tracking & Queue Analytics

## 1. Overview & Scope
The **Queue AI Pipeline** is the dedicated computer vision subsystem of the BYC AI Platform responsible for real-time monitoring of queue lines, barricaded pilgrim channels, waiting times, and pedestrian congestion at the Khairatabad Ganesh festival.

### Scope Boundaries
- **Strictly In Scope**: Person detection (COCO Class 0 only), multi-object tracking (`TRK-xxxx`), spatial Point-in-Polygon queue channel analytics, occupancy percentage, relative & calibrated density estimation, queue length estimation, directional entry/exit counting (inflow/outflow), queue movement direction (`FORWARD`, `BACKWARD`, `UNKNOWN`), transient dwell time estimation (average, median, max dwell), rolling growth rate, deterministic queue risk scoring (0–100), AI event generation with 60-second cooldown suppression, and pipeline health telemetry.
- **Strictly Out of Scope**: Facial Recognition / Biometrics / FRS (Step 8), automatic AI restart loops / final orchestrator (Step 9), Android mobile app updates, automated enforcement actions, or non-deterministic heuristics.

---

## 2. Hardware & Runtime Requirements

| Component | Minimum Specification | Recommended Specification |
|---|---|---|
| **GPU** | NVIDIA Turing / Ampere (e.g. RTX 3050/3060, T4) | NVIDIA Ampere / Ada (e.g. RTX 4080/4090, A10, A30) |
| **VRAM** | 4 GB VRAM (for YOLOv8s-queue) | 8 GB+ VRAM |
| **CUDA / Driver** | CUDA 12.x / 13.x, Driver >= 535 | CUDA 12.x / 13.x, Driver >= 550 |
| **DeepStream SDK** | NVIDIA DeepStream 6.3+ / 7.0+ | NVIDIA DeepStream 7.0+ Containerized |
| **CPU Fallback** | Not supported for production inference | Host without DeepStream explicitly reports `RUNTIME_UNAVAILABLE` (no fake data) |

### Profile Configurations
- **QUEUE_STANDARD**:
  - **Target**: Barricaded pilgrim lines, VIP entry corridors, laddu distribution channels, and darshan approach pathways.
  - **Model**: `yolov8s-queue` (TensorRT optimized engine).
  - **Input Resolution**: 1080p (downscaled to 640×640 for inference).
  - **Processing Target**: 10 FPS (sufficient for walking queues).
  - **Tracker**: ByteTrack / Kalman-IoU association enabled.
  - **Confidence Threshold**: 0.50.
  - **Target Classes**: Person (Class 0 strictly isolated).
  - **Resource Budget**: ~0.60 GB VRAM, ~5.0% GPU load.

---

## 3. Architecture & Data Flow

```
[IP Camera / RTSP H.264 Stream]
               │ (TCP transport, encrypted credentials in DB)
               ▼
   [QueuePipeline (Async Event Loop)]
               │
               ▼
   [PersonDetector (DeepStream / YOLO TensorRT)]
               │ Detections: Class 0 (person only), bbox: [x1, y1, x2, y2]
               ▼
   [PersonTracker (IoU + Centroid Association)]
               │ Transient IDs: TRK-0001, trajectory history (60 pts)
               ▼
   [QueueSpatialAnalytics (Ray-Casting & Vector Math)]
         ├── Geometry Check: QUEUE_ROI, ENTRY_LINE, EXIT_LINE
         ├── Point-in-Polygon (Bottom-Center Grounding: x_mid, y_max)
         ├── Exclusion Zone Subtraction
         ├── Queue Occupancy % (relative to configured queue_capacity)
         ├── Density Estimation (Relative & Calibrated persons/m²)
         ├── Queue Length Estimation (Extents & Calibrated meters)
         ├── Entry & Exit Line Crossings (Inflow / Outflow per minute)
         ├── Movement Direction Vector (FORWARD / BACKWARD / UNKNOWN)
         ├── Transient Dwell Time Engine (Average, Median, Max Dwell)
         └── Rolling Growth Rate (Headcount delta over 60s)
               │
               ▼
   [QueueRiskEngine (Deterministic Multi-Factor Scoring)]
               │ Score: 0 - 100, Level: LOW / MEDIUM / HIGH / CRITICAL
               ▼
   [QueueEventEngine (Cooldown Alert Generation)]
               │ 60s suppression window per camera & event type
               ▼
   [Event Bus / WebSocket Telemetry & Snapshot Persistence]
```

---

## 4. Geometric Prerequisites & Grounding

### Prerequisite Geometries
A Queue AI pipeline **cannot start** without three mandatory visual configurations:
1. `QUEUE_ROI`: Polygon outlining the barricaded queue area (>= 3 points).
2. `ENTRY_LINE`: Line segment defining where people enter the queue.
3. `EXIT_LINE`: Line segment defining where people leave the queue or reach the darshan point.

Optional geometries:
- `DIRECTION_LINE`: Direction vector defining expected queue forward flow.
- `EXCLUSION_ZONE`: Obstacles, pillars, or generator booths to subtract from headcount.

If any mandatory geometry is missing, pre-flight verification rejects pipeline initialization with HTTP 400 `QUEUE_CONFIGURATION_NOT_READY`.

### Bottom-Center Spatial Grounding
To prevent perspective distortion when camera view is tilted:
$$\text{Point} = \left( \frac{x_{\min} + x_{\max}}{2},\ y_{\max} \right)$$
Only the feet of the person determine whether they are inside the `QUEUE_ROI` or crossing counting lines.

---

## 5. Analytics Mathematical Formulations

### 1. Queue Headcount & Occupancy
- **Headcount**: Sum of active persons whose bottom-center reference point is inside `QUEUE_ROI` and not inside any `EXCLUSION_ZONE`.
- **Occupancy Percentage**:
  $$\text{Occupancy \%} = \min\left(100.0, \frac{\text{Queue Headcount}}{\text{Queue Capacity}} \times 100\right)$$
  If `queue_capacity` is unconfigured, occupancy reports `UNAVAILABLE` and `None` rather than inventing synthetic numbers.

### 2. Queue Density
- **Calibrated Density**: $\frac{\text{Queue Headcount}}{\text{Physical Area } (\text{m}^2)}$ in $\text{persons/m}^2$.
- **Relative Density**: $\frac{\text{Queue Headcount}}{\text{Normalized ROI Area}}$.

### 3. Queue Length
- **Extent Calculation**: Diagonal span of people waiting inside the queue:
  $$\Delta x = \max(x) - \min(x),\quad \Delta y = \max(y) - \min(y),\quad \text{Extent} = \sqrt{\Delta x^2 + \Delta y^2}$$
- If calibrated with `physical_length_meters`:
  $$\text{Queue Length (m)} = \text{Extent} \times \text{physical\_length\_meters}$$

### 4. Directional Line Crossings (Inflow & Outflow)
- Evaluates line segment intersection between person's trajectory $(A \to B)$ and counting line $(L_1 \to L_2)$ using 2D cross products.
- **5-Second Duplicate Suppression**: A track ID cannot trigger another line-crossing event on the same line within 5 seconds.
- Inflow and outflow rates are normalized to **persons per minute** across the rolling counting window.

### 5. Queue Movement Direction
Movement vectors $\vec{v}_{\text{trk}}$ of active tracks are compared against the expected queue flow vector $\vec{v}_{\text{queue}}$ (from entry line centroid to exit line centroid):
- $\cos \theta > 0.3 \implies \text{FORWARD}$
- $\cos \theta < -0.3 \implies \text{BACKWARD}$ (pilgrims pushing back or queue breakdown)
- $|\cos \theta| \le 0.3 \implies \text{UNKNOWN / STATIONARY}$

### 6. Dwell & Waiting Time Engine
- Tracks entering `QUEUE_ROI` receive an in-memory timestamp `entered_at`.
- Upon crossing the `EXIT_LINE` (or departing the queue for >3s), the completed wait duration is recorded.
- Telemetry reports **Average Wait Time**, **Median Wait Time**, and **Max Current Dwell** in seconds.
- If fewer than 1 wait sample exists, status reports `insufficient_data` and values remain `None`.

---

## 7. Deterministic Queue Risk Engine

Queue risk $R \in [0, 100]$ is computed deterministically:

$$R = \min\left(100.0,\ w_{\text{occ}} S_{\text{occ}} + w_{\text{wait}} S_{\text{wait}} + w_{\text{inflow}} S_{\text{inflow}} + w_{\text{growth}} S_{\text{growth}} + P_{\text{backward}}\right)$$

### Default Factor Weights
- $w_{\text{occ}} = 0.35$ (Occupancy percentage severity)
- $w_{\text{wait}} = 0.30$ (Excessive wait time severity)
- $w_{\text{inflow}} = 0.20$ (Inflow surge relative to outflow)
- $w_{\text{growth}} = 0.15$ (Rapid queue expansion rate)
- $P_{\text{backward}} = +15.0$ (Penalty if queue direction is `BACKWARD`)

### Severity Levels
- **LOW**: $0 \le R < 40$ (Smooth movement, wait time normal)
- **MEDIUM**: $40 \le R < 70$ (Moderate waiting, steady inflow)
- **HIGH**: $70 \le R < 85$ (High occupancy, bottleneck forming)
- **CRITICAL**: $85 \le R \le 100$ (Queue stalled, overcrowding, urgent marshal intervention required)

---

## 8. Event Generation & Cooldown Suppression

The `QueueEventEngine` evaluates metrics each frame and triggers structured events:
- `QUEUE_THRESHOLD_EXCEEDED`: Headcount exceeds configured safety threshold.
- `QUEUE_RISK_HIGH` / `QUEUE_RISK_CRITICAL`: Risk score enters elevated tiers.
- `QUEUE_INFLOW_SPIKE`: Sudden influx of pilgrims entering channel.
- `QUEUE_WAIT_TIME_HIGH`: Average or median wait exceeds warning threshold (e.g. 10 min).
- `QUEUE_GROWTH_SPIKE`: Rapid surge in queue depth within 60 seconds.

**Cooldown Rule**: Once emitted, an event for a specific `(camera_code, event_type)` is suppressed for **60 seconds** to avoid notification fatigue.

---

## 9. Multi-Camera Zone Aggregation

The `QueuePipelineRegistry` provides aggregated zone metrics across all cameras monitoring queues in a common zone (e.g. `ZONE-NORTH-GATE`):
- `active_queues_count`: Total active queue pipelines in the zone.
- `total_people_in_queues`: Sum of all queue headcounts in the zone.
- `max_risk_level`: Peak risk level across all monitored queues.
- `average_wait_seconds`: Weighted average wait time across all queues in the zone.

---

## 10. Security & Privacy Compliance

1. **Credential Decryption & Non-Leakage**:
   RTSP credentials decrypted for GStreamer/ffmpeg ingestion are masked in `QueuePipelineConfig.__repr__` and `__str__` and never returned in API payloads or telemetry.
2. **Zero FRS / Face Biometrics**:
   The queue pipeline interacts strictly with generic person bounding boxes (Class 0). No face crops, facial embeddings, identity databases, or biometrics exist in this subsystem.
3. **RBAC Control**:
   - Starting / stopping queue pipelines requires `queue:manage` or `ai:manage` permission.
   - Viewing queue dashboards and metrics requires `queue:read` permission.
4. **Immutable Audit Logging**:
   Every lifecycle action (start, stop, capacity check failure) is recorded in `audit_logs` with operator identity and IP address.
