# YOLO11x Production Deployment Guide: Multi-Camera Crowd & Queue AI

## 1. Overview
This document specifies the deployment, hardware setup, model export, and configuration workflow for deploying **YOLO11x** inside the BYC AI Command & Control Platform.

---

## 2. Hardware Architecture & Runtime Backends

The platform supports two deployment topologies:

### 2.1. Linux Production Node (NVIDIA TensorRT / DeepStream)
- **Host OS**: Ubuntu 22.04 LTS x86_64
- **GPU**: NVIDIA RTX 4080 / 4090 / A10 / L4 / L40S (Ampere/Ada Architecture)
- **Driver**: NVIDIA Driver >= 550.54
- **CUDA**: 12.2+ / 12.4+
- **Inference Runtime**: TensorRT 10.x Engine (.engine) or DeepStream 7.0+

### 2.2. Windows Edge Node (ONNX DirectML / RTX 3050+)
- **Host OS**: Windows 11 64-bit
- **GPU**: NVIDIA GeForce RTX 3050 Laptop / Desktop GPU (CUDA 13.1, Driver 592.82)
- **Inference Runtime**: ONNX Runtime with `DmlExecutionProvider` (DirectML GPU acceleration)
- **CPU Fallback**: ONNX Runtime with `CPUExecutionProvider`

---

## 3. YOLO11x Model Acquisition & Engine Export

### 3.1. Downloading Weights
Place the official PyTorch weights into the `models/` directory:
```bash
# YOLO11x PyTorch weights
mkdir -p models
curl -L -o models/yolo11x.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt
```

### 3.2. Exporting to ONNX (for Windows DirectML or Linux ONNX Runtime)
```bash
# Using Ultralytics export utility
python -c "
from ultralytics import YOLO
model = YOLO('models/yolo11x.pt')
model.export(format='onnx', imgsz=1280, dynamic=False, simplify=True, opset=17)
"
# Result: models/yolo11x.onnx
```

### 3.3. Building TensorRT Engine (FP16 Production)
Using NVIDIA `trtexec`:
```bash
trtexec \
  --onnx=models/yolo11x.onnx \
  --saveEngine=models/yolo11x_crowd.engine \
  --fp16 \
  --inputIOFormats=fp16:chw \
  --outputIOFormats=fp16:chw \
  --memPoolSize=workspace:4096M
```

---

## 4. Environment Configuration

Set the following environment variables in `.env` or system environment:

```env
# Model & Engine Paths
YOLO_MODEL_PATH=models/yolo11x.pt
YOLO_ENGINE_PATH=models/yolo11x_crowd.engine

# Performance Parameters
YOLO_INPUT_WIDTH=1280
YOLO_INPUT_HEIGHT=1280
YOLO_CONFIDENCE_THRESHOLD=0.35
YOLO_QUEUE_CONFIDENCE_THRESHOLD=0.40
YOLO_IOU_THRESHOLD=0.50
YOLO_DEVICE=cuda:0
```

---

## 5. Camera & Geometry Configuration Workflow

1. **Onboard Cameras**: Navigate to `/cameras` -> **Onboard Camera**. Enter RTSP URL (`rtsp://192.168.1.xxx:554/stream1`), assign purpose (`CROWD` or `QUEUE`).
2. **Assign Profile**: Assign `CROWD_YOLO11X` for zone monitoring and entry/exit counting; assign `QUEUE_YOLO11X` for barricaded pedestrian channels.
3. **Configure Geometries**:
   - For Crowd cameras: Draw `CROWD_ROI` polygon around monitored floor plane. Draw `ENTRY_LINE` and `EXIT_LINE` with direction vectors.
   - For Queue cameras: Draw `QUEUE_ROI` polygon along the barricade corridor. Draw `ENTRY_LINE` at line start and `EXIT_LINE` at service counter.
4. **Pre-flight Capacity Check**: The platform calculates projected GPU, VRAM, and CPU utilization. If safe headroom exists, deployment is `ALLOWED`.
5. **Start Pipeline**: Click **Start** on the camera or AI Orchestrator page. The orchestrator transitions `CREATED -> STARTING -> RUNNING`.

---

## 6. Pipeline Supervision & Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| `YOLO11X_UNAVAILABLE` | Weights (`.pt`) or engine (`.engine`/`.onnx`) not found at path | Verify `models/yolo11x.*` exists or set `YOLO_MODEL_PATH` |
| `GPU_INFERENCE_UNAVAILABLE` | NVIDIA GPU not detected or driver error | Verify `nvidia-smi` reports active GPU |
| `AI_CAPACITY_EXCEEDED` | Projected GPU or VRAM utilization exceeds safety ceiling | Split cameras across nodes or reduce concurrent active streams |
| `ROI_NOT_CONFIGURED` | Camera missing required polygon geometries | Use the ROI Editor to draw minimum 3-point polygon |
| High Detection Latency (>70ms) | Resolution too high or CPU fallback active | Verify DirectML/TensorRT provider is active; lower resolution to 640x640 if needed |
