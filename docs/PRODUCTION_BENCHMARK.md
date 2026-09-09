# Production Benchmark & Sizing Specification: YOLO11x Crowd & Queue AI

## 1. Overview & Hardware Sizing Guidelines
This specification defines the benchmarking methodology, multi-camera scaling limits, soak testing procedures, and hardware requirements for deploying **YOLO11x** in production at Khairatabad Ganesh.

---

## 2. Workload Profiles & Hardware Requirements

### 2.1. Model Resource Footprint (Per Stream)

| Metric | CROWD_YOLO11X | QUEUE_YOLO11X |
|---|---|---|
| **Input Resolution** | 1280x1280 | 1280x1280 |
| **Target FPS** | 15 FPS | 12 FPS |
| **Estimated VRAM** | 1.80 GB | 1.60 GB |
| **Estimated GPU Utilization** | 12.0% | 10.0% |
| **Estimated CPU Load** | 6.0% | 5.5% |
| **Estimated System RAM** | 800 MB | 750 MB |

### 2.2. Recommended Server Configurations

| Server Tier | GPU Model | VRAM | Max Concurrent Streams (YOLO11x) | Recommended Safe Streams |
|---|---|---|---|---|
| **Edge Box (Windows)** | RTX 3050 Laptop / Desktop | 6 GB | 2 streams (DirectML) | **1 stream** |
| **Mid-Tier Node** | RTX 4080 / RTX 4090 | 16–24 GB | 8–12 streams (TensorRT) | **6–8 streams** |
| **Enterprise AI Server** | NVIDIA L40S / A100 | 48–80 GB | 20–35 streams (TensorRT) | **20–25 streams** |

---

## 3. Incremental Multi-Camera Benchmark Protocol

When conducting physical on-site camera benchmarks, scale incrementally:
1. **Stage 1**: 1 Camera (Baseline verification: FPS, latency, GPU VRAM allocation).
2. **Stage 2**: 2 Cameras (Dual stream verification: multi-threading, Redis event throughput).
3. **Stage 3**: 5 Cameras (Subsystem load: 2 Zone + 3 Queue streams).
4. **Stage 4**: 10 Cameras (Intermediate cluster load: capacity headroom verification).
5. **Stage 5**: 25 Cameras (Full venue target: multi-GPU or distributed inference nodes).

### Measured Metrics per Stage:
- Input FPS vs Inference FPS vs Processing FPS
- Detection Latency (P50, P95, P99 in ms)
- GPU Utilization % and VRAM Allocation (GB)
- Host CPU Load % and RAM Allocation (GB)
- Pipeline Frame Drop Rate
- Total Active Tracks and Detections

---

## 4. Soak Testing & Long-Duration Stability Protocol
- **30-Minute Test**: Validates zero immediate memory leaks in OpenCV / ONNX Runtime buffers.
- **1-Hour Test**: Validates persistent WebSocket connection stability and Redis event bus throughput.
- **4-Hour Test**: Validates GPU thermal throttling behavior, sustained VRAM stability, and RTSP stream reconnect resilience.

---

## 5. Automatic Capacity Protection
The built-in `CapacityCalculator` enforces strict pre-flight protection:
- **Hard Ceilings**: GPU > 90%, VRAM > 90%, CPU > 85%, RAM > 90%.
- If any projected parameter exceeds safe budget, pipeline start is **BLOCKED** with `AI_CAPACITY_EXCEEDED`.
- Prevents out-of-memory crashes and kernel panics on edge and production hardware.

---

## 6. Hardware Availability Clause
Per Section 66 requirements:
If physical multi-camera RTSP hardware or production Linux TensorRT server is not physically connected during automated verification:
> `"REAL CAMERA E2E VALIDATION NOT EXECUTED — HARDWARE REQUIRED."`
Production metrics must not be synthetically invented.
