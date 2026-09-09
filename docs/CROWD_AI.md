# Crowd AI: Real-Time Detection, Tracking & Spatial Analytics

## 1. Overview & Scope
The **Crowd AI Pipeline** is the core computer vision subsystem of the BYC AI Command & Control Platform. It delivers real-time crowd headcount, density estimation, directional flow rate, entry/exit line crossing, and deterministic crowd risk metrics for public safety operations at Khairatabad Ganesh.

### Scope Boundaries
- **Strictly In Scope**:
  - Person detection (Class 0: person only) using production **YOLO11x**.
  - Multi-object tracking with transient track IDs (`TRK-xxxx`).
  - Spatial Point-in-Polygon analytics with bottom-center grounding `((x1+x2)/2, y2)`.
  - Directional line crossing (`ENTRY_LINE`, `EXIT_LINE`) with anti-duplicate cooldown suppression.
  - Non-overlapping multi-camera occupancy aggregation.
  - Relative & calibrated density estimation.
  - Deterministic multi-factor risk engine and telemetry bus integration.
- **Strictly Out of Scope**:
  - Facial recognition / biometrics (FRS is 100% isolated).
  - Cross-camera person re-identification.
  - Automatic law-enforcement or arrest actions.
  - Video processing in frontend/browser.

---

## 2. Model Profiles & Hardware Requirements

| Parameter | CROWD_STANDARD | CROWD_HIGH_DENSITY | CROWD_YOLO11X (Production) |
|---|---|---|---|
| **Model** | YOLOv8n | YOLOv8x | **YOLO11x** |
| **Input Resolution** | 640x640 | 1280x1280 | **1280x1280** (configurable) |
| **Target FPS** | 15 FPS | 20 FPS | **15 FPS** (configurable) |
| **Confidence Threshold** | 0.45 | 0.35 | **0.35** (configurable: `YOLO_CONFIDENCE_THRESHOLD`) |
| **IoU Threshold** | 0.45 | 0.50 | **0.50** (configurable: `YOLO_IOU_THRESHOLD`) |
| **Allowed Classes** | `[0]` (Person only) | `[0]` (Person only) | `[0]` (Person only) |
| **Estimated VRAM** | 0.45 GB | 1.20 GB | **1.80 GB** per stream |
| **Estimated GPU Load** | 3.5% | 8.0% | **12.0%** per stream |
| **Estimated System RAM** | 350 MB | 750 MB | **800 MB** per stream |
| **Backends Supported** | TensorRT / DeepStream | TensorRT / DeepStream | **TensorRT / ONNX DirectML / PyTorch / CPU fallback** |

---

## 3. Inference Architecture

```
                 IP Camera (RTSP H.264/H.265)
                              │
                              ▼
                Hardware Decode (NVDEC / DirectML)
                              │
                              ▼
                YOLO11x Person Detector
                 - Strict Class 0 filter
                 - Normalized bbox [0.0, 1.0]
                              │
                              ▼
                Person Tracker (Transient IDs: TRK-xxxx)
                              │
                              ▼
                     Bottom-Center Grounding
                     x = (x1 + x2) / 2.0, y = y2
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ENTRY_LINE             CROWD_ROI             EXIT_LINE
   Direction == IN        Point-in-Polygon      Direction == OUT
   Anti-duplicate CD      Exclusion Zone check  Anti-duplicate CD
        │                     │                     │
        ▼                     ▼                     ▼
   PERSON_ENTRY           Zone Headcount        PERSON_EXIT
   Events & Count         & Density Level       Events & Count
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
                     Crowd Risk Engine
                              │
                              ▼
                    Redis / WebSocket Bus
                              │
                              ▼
                Crowd Management Dashboard (/crowd-management)
```

---

## 4. Ground-Plane Spatial Grounding (Bottom-Center Point)
For overhead and angled CCTV cameras, using the bounding box center or face center leads to perspective distortion when determining whether a person is standing inside a zone or has crossed a line on the floor.
The pipeline strictly uses the **bottom-center point**:
$$\text{point} = \left(\frac{x_1 + x_2}{2.0},\; y_2\right)$$
where $y_2$ is the bottom edge of the normalized bounding box.

---

## 5. Entry & Exit Line Crossing
1. Every tracked person stores a trajectory of recent bottom-center coordinates.
2. When the line segment between the previous coordinate and current coordinate intersects the configured line:
   - Line direction is verified via vector cross-product against `DIRECTION_LINE`.
   - If the crossing is forward across `ENTRY_LINE`, a `PERSON_ENTRY` event is emitted.
   - If the crossing is forward across `EXIT_LINE`, a `PERSON_EXIT` event is emitted.
   - Crossings in the reverse direction are ignored.
3. **Anti-Duplicate Temporal Cooldown**:
   - A track ID crossing the line is cached with `(track_id, line_id, direction, timestamp)`.
   - Repeated triggers for the same person over subsequent frames are suppressed for `cooldown_seconds` (default: 60s).

---

## 6. Multi-Camera Non-Overlapping Aggregation
- **Total Occupancy**: Sum of current active tracks across designated non-overlapping zone cameras. Never sums detections across frames.
- **Total Entries**: Aggregate count of valid `PERSON_ENTRY` events across all active cameras within the selected time window.
- **Total Exits**: Aggregate count of valid `PERSON_EXIT` events across all active cameras within the selected time window.
- **Net Crowd Change**: $\text{Total Entries} - \text{Total Exits}$.
