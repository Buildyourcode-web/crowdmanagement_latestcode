# FRS Face Detection, Candidate Matching & Human Review Pipeline Manual

## 1. Overview & Golden Rules

The **Face Recognition System (FRS)** in the BYC AI Platform is a permission-controlled, privacy-compliant biometric workflow designed for security and investigation operations during the Khairatabad Ganesh festival.

> [!IMPORTANT]
> ### Safety & Operational Golden Rules
> 1. **Candidate Matches Only**: FRS generates **candidate matches for authorized human review**.
> 2. **NO Automatic Confirmation**: FRS **MUST NEVER**:
>    - Automatically confirm a person's identity.
>    - Automatically declare someone a suspect or criminal.
>    - Automatically trigger arrest or police dispatch.
>    - Automatically deny gate access or take enforcement actions.
> 3. **Human Review Requirement**: Every candidate match enters `REVIEW_REQUIRED` state and requires an authorized officer holding `frs:review` permission to verify it.
> 4. **Strict Isolation**: FRS is completely decoupled from Crowd AI and Queue AI. It never shares tracking IDs (`TRK-xxxx`), routes through crowd/queue risk engines, creates crowd/queue alerts, or modifies crowd/queue counts.

---

## 2. Camera Restrictions & Purpose Gating

FRS workloads can **ONLY** be deployed on cameras that satisfy:
* `camera.camera_type` $\in$ `["FRS", "MULTI_PURPOSE"]`
* AND assigned the `FRS_STANDARD` AI profile.

Any attempt to run FRS on `GENERAL`, `CROWD`, or `QUEUE` cameras is strictly rejected by the backend pre-flight gate with `400 FRS_CAMERA_NOT_ALLOWED`.

---

## 3. RBAC Permissions Matrix

| Permission | Description | Authorized Roles |
|---|---|---|
| `frs:read` | View candidate events, candidate details, reference persons list, fleet status, and pipeline health. | `SUPER_ADMIN`, `COMMANDER`, `FRS_OPERATOR` |
| `frs:review` | Perform human review on candidate matches (`CONFIRMED_BY_REVIEWER`, `REJECTED_BY_REVIEWER`, `UNRESOLVED`). | `SUPER_ADMIN`, `COMMANDER`, `FRS_OPERATOR` |
| `frs:manage` | Configure FRS pipelines, start/stop via Orchestrator, enroll/update reference persons, configure thresholds, trigger retention cleanup. | `SUPER_ADMIN` |

---

## 4. Pipeline Execution Flow

```
RTSP Stream
   │ (Decrypted URL; credentials masked in telemetry)
   ▼
[Face Detector] ── (SCRFD 10G / InsightFace buffalo_l)
   │ Bounding box, confidence >= 0.60, 5-point landmarks
   ▼
[Face Quality Gate] ── (Laplacian sharpness >= 50, size >= 60px, exposure, pose)
   │ Reject if insufficient -> FACE_QUALITY_INSUFFICIENT
   ▼
[Embedding Model] ── (ArcFace ResNet-50: 512-D L2-normalized vector)
   │
   ▼
[Active Gallery Search] ── (Cosine similarity search against active FRSReferenceProfile)
   │ Top-K ranking, similarity >= 75%
   ▼
[Duplicate Suppression] ── (Same camera + reference within 60s suppressed)
   │
   ▼
[Candidate Event] ── (Status: REVIEW_REQUIRED)
   │ Persisted in DB + WebSocket broadcast (sanitized payload)
   ▼
[Human Review Console]
   │ Side-by-side detected face vs reference photo
   ▼
[Officer Decision] ── (CONFIRMED_BY_REVIEWER / REJECTED_BY_REVIEWER / UNRESOLVED)
   │
   ▼
[Immutable Audit Log] ── (FRSAuditLog with officer identity, timestamp, decision notes)
```

---

## 5. Technical Modules Reference

### 5.1 Face Detector (`detector.py`)
- **Model**: InsightFace SCRFD 10G (`buffalo_l_det`, version `1.0.0`).
- **Input Dimensions**: $640 \times 640$.
- **Detection Output**:
  - Bounding box $(x_1, y_1, x_2, y_2)$.
  - Confidence score (threshold $\ge 0.60$).
  - 5-point facial landmarks: left eye, right eye, nose tip, left mouth corner, right mouth corner.
  - 3D head pose: yaw, pitch, roll in degrees.

### 5.2 Face Quality Gate (`quality.py`)
Before passing a detected face to the embedding model, it must pass 4 quality gates:
1. **Dimensions**: Minimum width and height $\ge 60\text{px}$.
2. **Sharpness**: Laplacian variance $\ge 50.0$ (filters motion blur and out-of-focus crops).
3. **Exposure**: Mean grayscale intensity $40 \le \mu \le 220$ (filters extreme underexposure or lens glare).
4. **Pose**: Absolute yaw $|\text{yaw}| \le 45^\circ$ and pitch $|\text{pitch}| \le 30^\circ$ (filters profile/angled faces).
*Faces failing any check are rejected with `FACE_QUALITY_INSUFFICIENT` without candidate generation.*

### 5.3 Face Embedding Engine (`embedding.py`)
- **Model**: ArcFace ResNet-50 (`buffalo_l_emb`, version `insightface-r50-v1`).
- **Input Dimensions**: $112 \times 112$ aligned crop.
- **Output**: 512-dimensional float32 vector with $L_2$ unit normalization ($\|v\|_2 = 1.0$).
- **Similarity Metric**: Cosine distance:
  $$\text{sim}(u, v) = \frac{u \cdot v}{\|u\|_2 \|v\|_2} = u \cdot v \quad (\text{since } \|u\|_2 = \|v\|_2 = 1.0)$$

### 5.4 Candidate Matcher (`matcher.py`)
- Searches active enrolled profiles in `FRSReferenceProfile` (`active == True` and `status == 'ACTIVE'`).
- Ranks candidates descending by cosine similarity.
- Enforces configurable match threshold (default $0.75$ / $75\%$).
- Generates Top-K candidates (default Top 3) and computes margin between Top-1 and Top-2.

### 5.5 Duplicate Suppression (`events.py`)
- Key: `f"{camera_code}:{reference_id}"`.
- Suppression Window: 60 seconds.
- Prevents flood of repeated alerts for the same person standing in front of a camera.

---

## 6. Human Review Workflow & Decisions

Every candidate match generates an `FRSCandidate` row with `status = "REVIEW_REQUIRED"` and `review_required = True`.

Authorized officers review candidates in `src/pages/FRS.jsx` side-by-side with reference images:
* **`CONFIRMED_BY_REVIEWER`**: Authorized human confirmed visual correlation.
* **`REJECTED_BY_REVIEWER`**: Authorized human confirmed no match / false positive.
* **`UNRESOLVED`**: Image quality or angle requires further investigation or secondary camera review.

Every review decision creates an immutable `FRSAuditLog` entry and updates the candidate audit timeline.

---

## 7. Data Retention & Privacy Protection

1. **Embedding Isolation**: Raw embeddings are stored as internal JSON vectors in PostgreSQL and are **NEVER** exposed via REST APIs, WebSocket events, or application logs.
2. **Credential Masking**: RTSP credentials are masked in all string representations (`rtsp://***:***@...`).
3. **Retention Policy**:
   - Candidate records and detected face crops expire after configurable retention (default 30 days).
   - Automated retention cleanup service purges expired records and removes image files from disk.
   - `FRSAuditLog` records are retained indefinitely for compliance and accountability.

---

## 8. AI Orchestrator Integration

FRS pipelines are controlled through the central `AIOrchestrator`:
- Lifecycle methods: `start_pipeline`, `stop_pipeline`, `restart_pipeline`, `start_all`, `stop_all`.
- **Dynamic Capacity Protection**: Evaluates CPU, RAM, and GPU workloads via `CapacityCalculator` before launch (`409 AI_CAPACITY_EXCEEDED` on projected host overload).
- **Startup Recovery**: Recovers pipelines where `desired_state == RUNNING` in staggered batches of 2 with 2-second intervals upon server boot.
- **Supervision Loop**: Monitors frame rates, latency, and heartbeat timeouts every 5 seconds.
