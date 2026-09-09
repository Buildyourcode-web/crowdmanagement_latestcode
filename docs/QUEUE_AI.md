# Queue AI: Real-Time Pedestrian Queue Monitoring & Dwell Analytics

## 1. Overview & Scope
The **Queue AI Pipeline** monitors pedestrian lines, physical barricade channels, and entry gates at the Khairatabad Ganesh festival. It calculates real-time queue headcount, estimated queue length, individual and aggregate wait times (dwell duration), queue growth rate, and movement direction.

All queue operations are integrated within the consolidated **Crowd Management** system. There is no isolated queue application.

---

## 2. Model Profiles & Hardware Requirements

| Parameter | QUEUE_STANDARD | QUEUE_YOLO11X (Production) |
|---|---|---|
| **Model** | YOLOv8s | **YOLO11x** |
| **Input Resolution** | 640x640 | **1280x1280** (configurable) |
| **Target FPS** | 10 FPS | **12 FPS** (configurable) |
| **Confidence Threshold** | 0.50 | **0.40** (configurable: `YOLO_QUEUE_CONFIDENCE_THRESHOLD`) |
| **IoU Threshold** | 0.45 | **0.50** (configurable: `YOLO_IOU_THRESHOLD`) |
| **Allowed Classes** | `[0]` (Person only) | `[0]` (Person only) |
| **Estimated VRAM** | 0.55 GB | **1.60 GB** per stream |
| **Estimated GPU Load** | 4.0% | **10.0%** per stream |
| **Backends Supported** | TensorRT / DeepStream | **TensorRT / ONNX DirectML / PyTorch / CPU fallback** |

---

## 3. Spatial Analytics & Geometry Requirements
Each Queue AI camera requires:
1. **QUEUE_ROI**: Polygon defining the physical barricade or queue corridor.
2. **ENTRY_LINE**: Line at the queue entry point with forward direction vector.
3. **EXIT_LINE**: Line at the queue service/exit point with forward direction vector.
4. **Optional EXCLUSION_ZONE**: Polygons masking security guards, staff booths, or outside walkways.

Detections are grounded using the **bottom-center point** `((x1+x2)/2, y2)`.

---

## 4. Key Metrics Calculation

### 4.1. Queue People Count
$$\text{Queue Count} = \text{COUNT}(\{T \in \text{Active Tracks} \mid \text{point}(T) \in \text{QUEUE\_ROI} \setminus \text{EXCLUSION\_ZONES}\})$$
- Current valid occupancy only. Detections are never summed across frames.

### 4.2. Queue Length
- If calibrated ground-plane scale is provided: physical length in meters along the corridor centerline.
- If uncalibrated: **RELATIVE QUEUE LENGTH** (normalized extent $[0.0, 1.0]$ within the ROI).

### 4.3. Waiting Time & Dwell Tracking
For each track ID $T$:
- $t_{\text{enter}}$: Timestamp when $T$'s bottom-center coordinate entered `QUEUE_ROI`.
- Current in-queue dwell: $t_{\text{now}} - t_{\text{enter}}$.
- Completed dwell: Recorded when $T$ crosses `EXIT_LINE` or exits the ROI forward.
- Metrics emitted: Average wait time (seconds/minutes), median wait time, maximum current wait time, and completed wait sample count.

### 4.4. Queue Movement & Dynamics
Answers the operator question: *"Is the queue moving?"*
- **Inflow**: Persons crossing `ENTRY_LINE` per minute.
- **Outflow**: Persons crossing `EXIT_LINE` per minute.
- **Net Growth**: $\text{Inflow} - \text{Outflow}$.
- **Movement State**:
  - `DRAINING`: Outflow significantly exceeds Inflow ($\text{Growth} < -3/\text{min}$).
  - `STEADY`: Inflow and Outflow roughly equal ($-3 \le \text{Growth} \le +3/\text{min}$).
  - `GROWING`: Inflow exceeds Outflow ($+3 < \text{Growth} \le +10/\text{min}$).
  - `SURGING`: Rapid accumulation ($\text{Growth} > +10/\text{min}$ with high risk alert).
  - `STAGNANT`: Queue headcount $> 50$ and Outflow $< 2/\text{min}$ for $> 3$ minutes.
