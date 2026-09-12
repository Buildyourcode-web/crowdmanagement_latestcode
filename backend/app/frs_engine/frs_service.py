"""
frs_service.py — Live RTSP FRS Engine Service for Khairatabad Command Center.

Architecture:
  - RTSPCameraWorker: background thread per camera
      - Reads frames from RTSP via RTSPReader
      - Detects & embeds faces via FaceModel
      - Matches against enrolled gallery from DB
      - Emits frs_candidate events over existing WebSocket bus
      - Streams MJPEG frames to /api/v1/frs-engine/cameras/{id}/stream
  - FastAPI router mounted at /api/v1/frs-engine
      - POST /cameras          → add RTSP camera & start worker
      - DELETE /cameras/{id}   → stop & remove camera
      - GET /cameras           → list active cameras
      - GET /cameras/{id}/stream → MJPEG live stream
      - GET /gallery           → list enrolled persons
      - WebSocket /ws/v1/frs-stream (alternative ws endpoint)

Does NOT overwrite: backend/app/main.py, backend/app/api/v1/frs.py, backend/app/config.py
"""

from __future__ import annotations

import asyncio
import base64
import math
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

_PKG_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend root directory
_DATA_CROPS_DIR = _PKG_BACKEND_DIR / "data" / "crops"
_DATA_ENROLLMENT_DIR = _PKG_BACKEND_DIR / "data" / "enrollment"
_DATA_CROPS_DIR.mkdir(parents=True, exist_ok=True)
_DATA_ENROLLMENT_DIR.mkdir(parents=True, exist_ok=True)



def _bbox_iou(a, b) -> float:
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)

    ix1 = max(a_arr[0], b_arr[0])
    iy1 = max(a_arr[1], b_arr[1])
    ix2 = min(a_arr[2], b_arr[2])
    iy2 = min(a_arr[3], b_arr[3])

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, a_arr[2] - a_arr[0]) * max(0.0, a_arr[3] - a_arr[1])
    area_b = max(0.0, b_arr[2] - b_arr[0]) * max(0.0, b_arr[3] - b_arr[1])

    union = area_a + area_b - inter
    return float(inter / union) if union > 0.0 else 0.0


def _bbox_center_dist(a, b) -> float:
    ca = np.array([(a[0] + a[2]) * 0.5, (a[1] + a[3]) * 0.5])
    cb = np.array([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5])
    return float(np.linalg.norm(ca - cb))


# ---------------------------------------------------------------------------
# Lazy-import FRS engine components (so backend still starts even without GPU)
# ---------------------------------------------------------------------------

def _load_frs_components():
    try:
        from app.frs_engine.models.face_model import FaceModel
        from app.frs_engine.recognition.matcher import IdentityMatcher
        from app.frs_engine.recognition.quality import FaceQualityAssessor
        from app.frs_engine.tracking.tracker import FaceTracker
        from app.frs_engine.input.rtsp_input import RTSPReader
        from app.frs_engine.database import repository as db
        return FaceModel, IdentityMatcher, FaceQualityAssessor, FaceTracker, RTSPReader, db
    except Exception as e:
        logger.warning(f"[FRS-Engine] Failed to load FRS components: {e}. Engine will be disabled.")
        return None, None, None, None, None, None


# ---------------------------------------------------------------------------
# Global camera registry
# ---------------------------------------------------------------------------

class CameraWorkerState:
    def __init__(self, camera_id: str, rtsp_url: str, name: str, is_frs: bool = True, camera_type: str = "FRS", ai_purposes: Optional[List[str]] = None, zone_code: Optional[str] = None):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.name = name
        self.is_frs = is_frs
        self.camera_type = camera_type
        self.ai_purposes = ai_purposes or (["ENTRY_EXIT", "ZONE"] if camera_type == "CROWD" else ["FRS"])
        self.zone_code = zone_code or "ZONE-A"
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.latest_frame: Optional[bytes] = None  # JPEG bytes for MJPEG (annotated if AI active)
        self.latest_clean_frame: Optional[bytes] = None  # Pure clean JPEG bytes (zero AI annotations)
        self.latest_crowd_frame: Optional[bytes] = None  # JPEG bytes with YOLO11x person & line counting overlays
        self.latest_rgb: Optional[np.ndarray] = None  # Raw RGB frame
        self.frame_lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.detections_count = 0
        self.status = "starting"
        # Crowd AI & Counting Line state
        self.crowd_ai_active: bool = False
        self.in_count: int = 0
        self.out_count: int = 0
        self.occupancy_count: int = 0
        self.queue_movement_status: str = "STOPPED"
        self.zone_data: List[dict] = []

_camera_workers: Dict[str, CameraWorkerState] = {}
_workers_lock = threading.Lock()


# ---------------------------------------------------------------------------
# WebSocket broadcast helper (use existing WS manager)
# ---------------------------------------------------------------------------

def _get_ws_manager():
    try:
        from app.websocket.manager import ws_manager
        return ws_manager
    except Exception:
        return None

_main_loop: Optional[asyncio.AbstractEventLoop] = None

def set_main_event_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop

def _fetch_rois_sync(state) -> tuple:
    """Synchronously fetch ROI configs from DB. Safe to call from any background thread."""
    from app.db.session import SyncSessionLocal
    from app.models.camera_roi import CameraROIConfiguration
    from sqlalchemy import select as sa_select

    if SyncSessionLocal is None:
        return [], []

    clean_id = state.camera_id.replace("-FRS", "").replace("-CROWD", "")
    all_valid_types = [
        "COUNTING_LINE", "ENTRY_LINE", "EXIT_LINE",
        "CROWD_ROI", "EXCLUSION_ZONE", "ZONE_BOUNDARY",
        "QUEUE_ROI", "DIRECTION_LINE",
    ]

    with SyncSessionLocal() as db:
        stmt = sa_select(CameraROIConfiguration).where(
            CameraROIConfiguration.camera_code.in_([state.camera_id, clean_id]),
            CameraROIConfiguration.enabled.is_(True),
            CameraROIConfiguration.roi_type.in_(all_valid_types),
        )
        items = db.execute(stmt).scalars().all()
        lines = []
        polygons = []
        found_types = set()
        for item in items:
            found_types.add(item.roi_type)
            geom = item.geometry_json or {}
            if "start" in geom and "end" in geom:
                lines.append({
                    "id": str(item.id),
                    "name": item.name or item.roi_name or "Counting Line",
                    "type": item.roi_type,
                    "start": geom["start"],
                    "end": geom["end"],
                    "direction": geom.get("direction", "BOTH"),
                })
            elif item.polygon_points and len(item.polygon_points) == 2 and item.roi_type in ("COUNTING_LINE", "ENTRY_LINE", "EXIT_LINE", "DIRECTION_LINE"):
                lines.append({
                    "id": str(item.id),
                    "name": item.name or item.roi_name or "Counting Line",
                    "type": item.roi_type,
                    "start": item.polygon_points[0],
                    "end": item.polygon_points[1],
                    "direction": item.direction or "BOTH",
                })
            pts = geom.get("points") or item.polygon_points or []
            if isinstance(pts, list) and len(pts) >= 3:
                polygons.append({
                    "id": str(item.id),
                    "name": geom.get("zone_name") or item.name or item.roi_name or "Monitored Zone",
                    "type": item.roi_type,
                    "points": pts,
                    "warning_threshold": int(geom.get("warning_threshold") or 50),
                    "danger_threshold": int(geom.get("danger_threshold") or 80),
                    "capacity": int(geom.get("capacity") or 100),
                })

        # Dynamically sync camera purposes based on actual ROIs saved in DB
        derived_purposes = []
        if "ENTRY_LINE" in found_types and "EXIT_LINE" not in found_types and "COUNTING_LINE" not in found_types:
            derived_purposes.append("ENTRY")
        elif "EXIT_LINE" in found_types and "ENTRY_LINE" not in found_types and "COUNTING_LINE" not in found_types:
            derived_purposes.append("EXIT")
        elif any(t in found_types for t in ("COUNTING_LINE", "ENTRY_LINE", "EXIT_LINE")):
            derived_purposes.append("ENTRY_EXIT")

        if "CROWD_ROI" in found_types or "ZONE_BOUNDARY" in found_types:
            derived_purposes.append("ZONE")
        if "QUEUE_ROI" in found_types or "DIRECTION_LINE" in found_types:
            derived_purposes.append("QUEUE")

        if derived_purposes:
            current_purps = getattr(state, "ai_purposes", None) or []
            # Merge current and derived, preserving order, max 2
            merged = []
            for p in current_purps + derived_purposes:
                if p in ("ENTRY_EXIT", "ZONE", "QUEUE", "ENTRY", "EXIT") and p not in merged:
                    merged.append(p)
                if len(merged) >= 2:
                    break
            state.ai_purposes = merged or derived_purposes[:2]

        return lines, polygons



def _emit_frs_event_threadsafe(event_type: str, payload: dict):
    mgr = _get_ws_manager()
    if mgr:
        try:
            global _main_loop
            if _main_loop and _main_loop.is_running():
                asyncio.run_coroutine_threadsafe(mgr.broadcast_event(event_type, payload), _main_loop)
            else:
                curr_loop = None
                try:
                    curr_loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
                if curr_loop and curr_loop.is_running():
                    asyncio.create_task(mgr.broadcast_event(event_type, payload))
        except Exception as e:
            logger.debug(f"[FRS-Engine] WS broadcast error: {e}")

async def _emit_frs_event(event_type: str, payload: dict):
    _emit_frs_event_threadsafe(event_type, payload)


# ---------------------------------------------------------------------------
# RTSP Camera Worker thread
# ---------------------------------------------------------------------------

MATCH_THRESHOLD = 0.60
DET_SIZE = (640, 640)

# Shared singleton FRS (InsightFace) components — these are model-level singletons
# because InsightFace buffalo_l is pinned to one GPU per process.
# For multi-GPU FRS, deploy separate container per GPU.
_shared_face_model = None
_shared_matcher = None
_shared_engine_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Per-GPU YOLO pool for crowd/queue AI — replaces the old single-lock approach.
# Each camera thread obtains its own GPU session via gpu_pool.acquire().
# ---------------------------------------------------------------------------
def _get_yolo_pool_onnx_path() -> Optional[str]:
    """Finds the YOLO11x ONNX model path."""
    candidates = [
        "models/yolo11x.onnx",
        "models/yolo11x_crowd.onnx",
        os.path.join(os.getcwd(), "backend", "models", "yolo11x.onnx"),
        os.path.join(os.getcwd(), "models", "yolo11x.onnx"),
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def get_shared_engine():
    global _shared_face_model, _shared_matcher
    with _shared_engine_lock:
        if _shared_face_model is None:
            (FaceModel, IdentityMatcher, _, _, _, db) = _load_frs_components()
            if FaceModel is not None:
                _shared_face_model = FaceModel()
                _shared_matcher = IdentityMatcher(threshold=MATCH_THRESHOLD)
                try:
                    embeddings, ids, names = db.load_all_embeddings()
                    if embeddings:
                        _shared_matcher.load_gallery(embeddings, ids, names)
                        logger.info(f"[FRS-Engine] Shared gallery loaded: {len(names)} identities ({set(names)})")
                except Exception as e:
                    logger.warning(f"[FRS-Engine] Gallery load warning: {e}")
        return _shared_face_model, _shared_matcher


def reload_shared_gallery():
    global _shared_matcher
    with _shared_engine_lock:
        if _shared_matcher is not None:
            try:
                (_, _, _, _, _, db) = _load_frs_components()
                if db:
                    embeddings, ids, names = db.load_all_embeddings()
                    if embeddings:
                        _shared_matcher.threshold = MATCH_THRESHOLD
                        _shared_matcher.load_gallery(embeddings, ids, names)
            except Exception as e:
                logger.warning(f"[FRS-Engine] Gallery reload warning: {e}")


def get_shared_yolo_engine():
    """
    Returns the gpu_pool-managed ONNX session for the *calling thread's camera*.
    
    DEPRECATED SIGNATURE preserved for compatibility — new code should call
    gpu_pool.acquire(camera_code) directly.  This function is retained for the
    _crowd_ai_detection_loop which calls it without a camera code; it returns
    the first available session (GPU-0 by default) when no camera context is
    available.
    """
    try:
        from app.ai.gpu_allocator import gpu_pool, initialize_gpu_pool
        model_path = _get_yolo_pool_onnx_path()
        if model_path is None:
            logger.warning("[YOLO11x-Crowd] No ONNX model file found in models/")
            return None
        if not gpu_pool.is_ready:
            success = initialize_gpu_pool(model_path)
            if not success:
                return None
        # Return first pool entry's session (caller must use per-GPU lock separately)
        if gpu_pool._pool:
            return gpu_pool._pool[0].session
    except Exception as e:
        logger.warning(f"[YOLO11x-Crowd] Failed to get GPU pool session: {e}")
    return None


def _check_ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

def _segments_cross(p1, p2, l1, l2):
    return _check_ccw(p1, l1, l2) != _check_ccw(p2, l1, l2) and _check_ccw(p1, p2, l1) != _check_ccw(p1, p2, l2)

def _point_to_segment_dist(p, s1, s2):
    px, py = p
    x1, y1 = s1
    x2, y2 = s2
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)

def _box_touches_line(box, l1, l2):
    """
    Checks if a bounding box [x1, y1, x2, y2] touches or intersects a line segment l1->l2.
    Checks all 4 box edges, centroid trajectory, and point proximity.
    """
    x1, y1, x2, y2 = box
    # 4 bounding box edge segments
    e_top = ((x1, y1), (x2, y1))
    e_bot = ((x1, y2), (x2, y2))
    e_lft = ((x1, y1), (x1, y2))
    e_rgt = ((x2, y1), (x2, y2))

    if _segments_cross(e_top[0], e_top[1], l1, l2):
        return True
    if _segments_cross(e_bot[0], e_bot[1], l1, l2):
        return True
    if _segments_cross(e_lft[0], e_lft[1], l1, l2):
        return True
    if _segments_cross(e_rgt[0], e_rgt[1], l1, l2):
        return True

    # Check if any corner or center is within 16px of line segment
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    if _point_to_segment_dist((cx, cy), l1, l2) <= 16.0:
        return True
    if _point_to_segment_dist((cx, y1), l1, l2) <= 16.0:  # head
        return True
    if _point_to_segment_dist((cx, y2), l1, l2) <= 16.0:  # feet
        return True

    # Check if either endpoint of line segment is inside the bounding box
    if x1 <= l1[0] <= x2 and y1 <= l1[1] <= y2:
        return True
    if x1 <= l2[0] <= x2 and y1 <= l2[1] <= y2:
        return True

    return False

def _point_in_polygon(pt: tuple[float, float], polygon_pts: list) -> bool:
    """
    Ray-casting algorithm to test if point pt (x, y) is inside polygon_pts.
    Works for normalized [0, 1] coords or pixel coords.
    """
    if not polygon_pts or len(polygon_pts) < 3:
        return False
    x, y = pt
    inside = False
    n = len(polygon_pts)
    p1 = polygon_pts[0]
    p1x = p1["x"] if isinstance(p1, dict) else p1[0]
    p1y = p1["y"] if isinstance(p1, dict) else p1[1]

    for i in range(1, n + 1):
        p2 = polygon_pts[i % n]
        p2x = p2["x"] if isinstance(p2, dict) else p2[0]
        p2y = p2["y"] if isinstance(p2, dict) else p2[1]

        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _box_iou(b1, b2):
    """Calculate IoU for two bounding boxes [x1, y1, x2, y2]."""
    xA = max(b1[0], b2[0])
    yA = max(b1[1], b2[1])
    xB = min(b1[2], b2[2])
    yB = min(b1[3], b2[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    area1 = max(0, b1[2] - b1[0]) * max(0, b1[3] - b1[1])
    area2 = max(0, b2[2] - b2[0]) * max(0, b2[3] - b2[1])
    denom = area1 + area2 - inter
    return (inter / denom) if denom > 0 else 0.0


def _persist_crowd_snapshot_threadsafe(camera_code: str, inflow_delta: int, outflow_delta: int, headcount: int, zone_code_override: Optional[str] = None):
    """Asynchronously persist line-crossing or crowd headcount snapshot to PostgreSQL, updating Camera and Zone tables."""
    async def _do_persist():
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.camera import Camera
            from app.models.crowd import CrowdSnapshot
            from app.models.zone import Zone
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                clean_code = camera_code.replace("-FRS", "").replace("-CROWD", "")
                stmt = select(Camera).where(Camera.camera_code.in_([camera_code, clean_code])).limit(1)
                res = await session.execute(stmt)
                cam = res.scalars().first()

                now = datetime.now(timezone.utc)
                target_zone = zone_code_override or (cam.zone_code if (cam and cam.zone_code) else "ZONE-A")

                snap = CrowdSnapshot(
                    id=uuid.uuid4(),
                    event_id=cam.event_id if cam else None,
                    zone_id=cam.zone_id if cam else None,
                    zone_code=target_zone,
                    camera_id=cam.id if cam else None,
                    camera_code=camera_code,
                    profile_id="CROWD_STANDARD",
                    timestamp=now,
                    people_count=headcount,
                    density=round(headcount / 100.0, 2),
                    inflow_rate=inflow_delta,
                    outflow_rate=outflow_delta,
                    occupancy_percentage=min(100.0, max(0.0, round((headcount / 200.0) * 100, 1))),
                    risk_level="LOW" if headcount < 10 else ("MODERATE" if headcount < 25 else "HIGH"),
                    risk_score=round(headcount * 0.04, 2),
                )
                session.add(snap)

                # 1. Update Camera in DB
                if cam:
                    cam.people_count = headcount
                    cam.last_seen_at = now
                    if target_zone and cam.zone_code != target_zone:
                        cam.zone_code = target_zone

                # 2. Update Zone in DB
                stmt_z = select(Zone).where(Zone.zone_code == target_zone).limit(1)
                res_z = await session.execute(stmt_z)
                zone_obj = res_z.scalars().first()
                if zone_obj:
                    zone_obj.current_people = max(0, headcount)
                    cap = zone_obj.capacity or 100
                    density_ratio = (headcount / float(cap)) if cap > 0 else 0.0
                    zone_obj.density = round(density_ratio, 2)
                    zone_obj.density_label = "HIGH" if density_ratio >= 0.75 else ("MODERATE" if density_ratio >= 0.50 else "LOW")
                    zone_obj.risk_level = "CRITICAL" if density_ratio >= 0.85 else ("HIGH" if density_ratio >= 0.60 else "LOW")
                    zone_obj.status = "ACTIVE"

                await session.commit()
        except Exception as e:
            logger.debug(f"[Crowd-AI] Snapshot persist notice: {e}")

    global _main_loop
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_persist(), _main_loop)


def _persist_queue_snapshot_threadsafe(camera_code: str, headcount: int, movement_status: str, zone_code_override: Optional[str] = None):
    """Asynchronously persist queue status snapshot to PostgreSQL."""
    async def _do_persist_queue():
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.camera import Camera
            from app.models.queue import QueueSnapshot
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                clean_code = camera_code.replace("-FRS", "").replace("-CROWD", "")
                stmt = select(Camera).where(Camera.camera_code.in_([camera_code, clean_code])).limit(1)
                res = await session.execute(stmt)
                cam = res.scalars().first()

                now = datetime.now(timezone.utc)
                target_zone = zone_code_override or (cam.zone_code if (cam and cam.zone_code) else "ZONE-A")
                wait_min = max(1, int(round(headcount * 0.8)))

                snap = QueueSnapshot(
                    id=uuid.uuid4(),
                    event_id=cam.event_id if cam else None,
                    zone_id=cam.zone_id if cam else None,
                    zone_code=target_zone,
                    camera_id=cam.id if cam else None,
                    camera_code=camera_code,
                    queue_code=f"QUEUE-{target_zone}",
                    queue_name=f"Queue {target_zone}",
                    timestamp=now,
                    people_count=headcount,
                    wait_time_minutes=wait_min,
                    movement_status=movement_status,
                    service_rate=12.0,
                    risk_level="LOW" if headcount < 20 else ("MODERATE" if headcount < 50 else "HIGH"),
                )
                session.add(snap)
                await session.commit()
        except Exception as e:
            logger.debug(f"[Queue-AI] Queue snapshot persist notice: {e}")

    global _main_loop
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_persist_queue(), _main_loop)



class RTSPCameraWorker:
    """
    Decoupled threaded RTSP worker:
    - Thread 1 (Capture): non-blocking frame grabber from RTSP at 25 FPS, overlays bounding boxes, encodes MJPEG.
    - Thread 2 (AI Inference): runs asynchronously every ~200ms on CPU, detects faces, matches against gallery, emits alerts.
    """

    def __init__(self, state: CameraWorkerState):
        self.state = state
        self.state.worker = self
        self._cooldowns: Dict[str, float] = {}
        self._active_boxes: List[dict] = []
        self._boxes_lock = threading.Lock()
        self._latest_ai_rgb = None
        self._ai_lock = threading.Lock()
        # Crowd AI & YOLO11x state
        self._crowd_boxes: List[dict] = []
        self._crowd_boxes_lock = threading.Lock()
        self._cached_roi_lines: List[dict] = []
        self._cached_roi_polygons: List[dict] = []
        self._zone_stats: List[dict] = []
        self._roi_lines_last_fetch: float = 0.0
        self._prev_centroids: List[tuple] = []
        self._prev_queue_centroids: List[tuple] = []
        self._queue_displacement_history = deque(maxlen=8)
        self._line_cross_cooldown: float = 0.0
        self._crowd_tracks: Dict[int, dict] = {}
        self._next_track_id: int = 1
        self._queue_tracks: Dict[int, dict] = {}
        self._next_queue_track_id: int = 1
        self._last_snapshot_persist: float = 0.0
        self._recent_crossings: List[dict] = []

    def _ai_detection_loop(self, face_model, matcher, tracker):
        crop_dir = str(_DATA_CROPS_DIR)
        os.makedirs(crop_dir, exist_ok=True)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        frame_counter = 0

        while self.state.running:
            if not self.state.is_frs:
                with self._boxes_lock:
                    self._active_boxes.clear()
                tracker.clear()
                time.sleep(0.3)
                continue

            with self._ai_lock:
                frame_to_process = None
                if self._latest_ai_rgb is not None:
                    frame_to_process = self._latest_ai_rgb.copy()
                    self._latest_ai_rgb = None

            if frame_to_process is None:
                time.sleep(0.03)
                continue

            try:
                frame_counter += 1
                try:
                    with _shared_engine_lock:
                        faces = face_model.detect_faces(frame_to_process)
                except Exception as e:
                    time.sleep(0.05)
                    continue

                # Update FaceTracker with detected faces for continuous, smooth tracking
                active_tracks = tracker.update(faces, frame_counter)
                new_boxes = []
                now_ts = time.time()
                rendered_bboxes = []

                for track in active_tracks:
                    if track.misses > 6:
                        continue

                    tx1, ty1, tx2, ty2 = [int(v) for v in track.bbox]
                    # Allow distant faces down to 14px
                    if (tx2 - tx1) < 14 or (ty2 - ty1) < 14:
                        continue

                    # Find if any face detection corresponds to this track in current frame
                    matched_face = None
                    for face in faces:
                        fx1, fy1, fx2, fy2 = face.bbox
                        if _bbox_iou(track.bbox, face.bbox) > 0.20 or _bbox_center_dist(track.bbox, face.bbox) < 90.0:
                            matched_face = face
                            break

                    if matched_face is not None and matched_face.embedding is not None:
                        try:
                            result = matcher.find_best_match(matched_face.embedding)
                        except Exception:
                            result = None

                        if result and result.is_known and result.similarity >= MATCH_THRESHOLD:
                            track.candidate_name = result.name.strip()
                            track.candidate_similarity = result.similarity
                            track.candidate_id = result.person_id
                        elif track.candidate_name == "Unknown":
                            track.candidate_similarity = getattr(matched_face, "det_score", 0.85)

                    is_known = bool(track.candidate_name and track.candidate_name != "Unknown" and track.candidate_similarity >= MATCH_THRESHOLD)

                    if is_known:
                        person_clean = track.candidate_name
                        match_pct = round(track.candidate_similarity * 100, 1)
                        new_boxes.append({
                            "bbox": [tx1, ty1, tx2, ty2],
                            "label": f"{person_clean.upper()} {match_pct}%",
                            "is_match": True,
                            "expiry": now_ts + 1.2,
                        })
                        rendered_bboxes.append((tx1, ty1, tx2, ty2))

                        # Cooldown check: 15s per recognized person
                        last_alert = self._cooldowns.get(person_clean.lower(), 0.0)
                        if (now_ts - last_alert) >= 15.0:
                            self._cooldowns[person_clean.lower()] = now_ts
                            self.state.detections_count += 1

                            h, w = frame_to_process.shape[:2]
                            fw, fh = tx2 - tx1, ty2 - ty1
                            pad_x = int(fw * 0.25)
                            pad_y = int(fh * 0.25)
                            cx1, cy1 = max(0, tx1 - pad_x), max(0, ty1 - pad_y)
                            cx2, cy2 = min(w, tx2 + pad_x), min(h, ty2 + pad_y)
                            crop = frame_to_process[cy1:cy2, cx1:cx2]

                            face_b64 = ""
                            detected_image_url = ""
                            crop_id = str(uuid.uuid4())[:8]
                            cand_code = f"CAND-{crop_id.upper()}"

                            if crop.size > 0:
                                crop_bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
                                _, crop_buf = cv2.imencode(".jpg", crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
                                face_b64 = base64.b64encode(crop_buf.tobytes()).decode("utf-8")
                                crop_filename = f"crop_{person_clean.lower()}_{crop_id}.jpg"
                                crop_filepath = os.path.join(crop_dir, crop_filename)
                                cv2.imwrite(crop_filepath, crop_bgr)
                                # Also write to nested directory if present to keep in sync
                                try:
                                    nested_dir = _PKG_BACKEND_DIR / "backend" / "data" / "crops"
                                    if nested_dir.exists():
                                        cv2.imwrite(str(nested_dir / crop_filename), crop_bgr)
                                except Exception:
                                    pass
                                detected_image_url = f"/static/crops/{crop_filename}"

                            if not detected_image_url:
                                detected_image_url = f"data:image/jpeg;base64,{face_b64}"

                            ref_img_url = ""
                            try:
                                p_info = db.get_person_by_name(person_clean)
                                if p_info:
                                    embs_for_p = db.get_embeddings_for_person(p_info["id"])
                                    if embs_for_p and embs_for_p[0].get("image_path"):
                                        fname = os.path.basename(embs_for_p[0]["image_path"])
                                        ref_img_url = f"/static/enrollment/{fname}"
                            except Exception:
                                pass

                            if not ref_img_url:
                                enroll_dir = str(_DATA_ENROLLMENT_DIR)
                                if os.path.exists(enroll_dir):
                                    for fn in os.listdir(enroll_dir):
                                        if fn.lower().startswith(person_clean.lower()):
                                            ref_img_url = f"/static/enrollment/{fn}"
                                            break
                            if not ref_img_url:
                                ref_img_url = f"/static/enrollment/{person_clean.lower()}_1.jpg"

                            ref_id_str = f"WL-{person_clean.upper()}-001"
                            time_str = datetime.now().strftime("%H:%M:%S")
                            date_str = datetime.now().strftime("%d %b %Y")
                            iso_ts = datetime.now(timezone.utc).isoformat()

                            payload = {
                                "id": str(uuid.uuid4()),
                                "candidateCode": cand_code,
                                "candidate_code": cand_code,
                                "cameraId": self.state.camera_id,
                                "camera_id": self.state.camera_id,
                                "cameraName": self.state.name,
                                "camera_name": self.state.name,
                                "personId": str(track.candidate_id or uuid.uuid4()),
                                "person_id": str(track.candidate_id or uuid.uuid4()),
                                "personName": person_clean,
                                "person_name": person_clean,
                                "referenceName": person_clean,
                                "reference_name": person_clean,
                                "referenceId": ref_id_str,
                                "reference_id": ref_id_str,
                                "matchScore": match_pct,
                                "match_score": match_pct,
                                "detectedImage": detected_image_url,
                                "detected_image": detected_image_url,
                                "referenceImage": ref_img_url,
                                "reference_image": ref_img_url,
                                "faceImageB64": face_b64,
                                "face_image_b64": face_b64,
                                "timestamp": iso_ts,
                                "timeStr": time_str,
                                "time_str": time_str,
                                "dateStr": date_str,
                                "date_str": date_str,
                                "status": "PENDING_REVIEW",
                                "location": "Khairatabad Main Entry",
                                "category": "Authorized Watchlist",
                                "priority": "HIGH",
                                "imageQuality": "High (94%)",
                                "image_quality": "High (94%)",
                                "bbox": [tx1, ty1, tx2, ty2],
                            }

                            logger.info(f"[FRS-Worker:{self.state.camera_id}] MATCH: {person_clean} ({match_pct}%) -> Broadcast & Save")

                            async def _persist():
                                try:
                                    from app.db.session import AsyncSessionLocal
                                    from app.models.frs import FRSCandidate, FRSReferenceProfile
                                    from sqlalchemy import select
                                    async with AsyncSessionLocal() as pg_db:
                                        prof_q = await pg_db.execute(
                                            select(FRSReferenceProfile).where(
                                                FRSReferenceProfile.display_name.ilike(person_clean)
                                            ).limit(1)
                                        )
                                        prof = prof_q.scalars().first()
                                        prof_id = prof.id if prof else None

                                        cand = FRSCandidate(
                                            candidate_code=cand_code,
                                            camera_code=self.state.camera_id,
                                            camera_name=self.state.name,
                                            zone_code="ZONE-A",
                                            location="Khairatabad Main Entry",
                                            reference_profile_id=prof_id,
                                            detected_image_path=detected_image_url,
                                            match_score=match_pct,
                                            detection_confidence=track.candidate_similarity,
                                            quality_score=0.94,
                                            status="REVIEW_REQUIRED",
                                            review_required=True,
                                            priority="HIGH",
                                            image_quality="High (94%)",
                                            date_str=date_str,
                                            time_str=time_str,
                                        )
                                        pg_db.add(cand)
                                        await pg_db.commit()
                                except Exception as dberr:
                                    logger.warning(f"[FRS-Worker] DB save error: {dberr}")

                            global _main_loop
                            if _main_loop and _main_loop.is_running():
                                asyncio.run_coroutine_threadsafe(_persist(), _main_loop)

                            _emit_frs_event_threadsafe("frs_candidate", payload)
                    else:
                        # Unmatched / scanning face: ALWAYS show detection bounding box so every person is detected!
                        conf_val = track.candidate_similarity if track.candidate_similarity > 0.0 else 0.85
                        det_pct = round(max(0.35, min(0.99, conf_val)) * 100)
                        new_boxes.append({
                            "bbox": [tx1, ty1, tx2, ty2],
                            "label": f"FACE SCANNING {det_pct}%",
                            "is_match": False,
                            "expiry": now_ts + 1.2,
                        })
                        rendered_bboxes.append((tx1, ty1, tx2, ty2))

                # Safety fallback: If any face detected by model was missed by tracker, render it directly
                for face in faces:
                    fx1, fy1, fx2, fy2 = [int(v) for v in face.bbox]
                    already_rendered = False
                    for rx1, ry1, rx2, ry2 in rendered_bboxes:
                        if _bbox_iou([fx1, fy1, fx2, fy2], [rx1, ry1, rx2, ry2]) > 0.3:
                            already_rendered = True
                            break
                    if not already_rendered:
                        det_score = getattr(face, "det_score", 0.85)
                        det_pct = round(float(det_score) * 100)
                        new_boxes.append({
                            "bbox": [fx1, fy1, fx2, fy2],
                            "label": f"FACE SCANNING {det_pct}%",
                            "is_match": False,
                            "expiry": now_ts + 1.2,
                        })

                with self._boxes_lock:
                    self._active_boxes = new_boxes

            except Exception as e:
                logger.error(f"[FRS-AI-Worker:{self.state.camera_id}] Inference loop error: {e}")

            time.sleep(0.06)

        loop.close()

    def _refresh_roi_lines(self):
        """Query DB for ROI configs synchronously from the crowd AI thread."""
        try:
            res_lines, res_polygons = _fetch_rois_sync(self.state)
            self._cached_roi_lines = res_lines
            self._cached_roi_polygons = res_polygons
            if res_lines or res_polygons:
                logger.info(f"[Crowd-AI-Worker:{self.state.camera_id}] ROI loaded: {len(res_lines)} line(s), {len(res_polygons)} polygon(s)")
        except Exception as e:
            logger.warning(f"[Crowd-AI-Worker:{self.state.camera_id}] _refresh_roi_lines failed: {type(e).__name__}: {e}")


    def _crowd_ai_detection_loop(self):
        logger.info(f"[Crowd-AI-Worker:{self.state.camera_id}] Crowd AI detection loop started.")
        while self.state.running:
            is_crowd = getattr(self.state, "crowd_ai_active", False) and not self.state.is_frs
            if not is_crowd:
                with self._crowd_boxes_lock:
                    self._crowd_boxes.clear()
                self._prev_centroids.clear()
                self._prev_queue_centroids.clear()
                time.sleep(0.3)
                continue

            now = time.time()
            _refresh_interval = 5.0 if not self._cached_roi_lines else 60.0
            if (now - self._roi_lines_last_fetch) > _refresh_interval:
                self._roi_lines_last_fetch = now
                self._refresh_roi_lines()

            with self._ai_lock:
                frame_to_process = None
                if self._latest_ai_rgb is not None:
                    frame_to_process = self._latest_ai_rgb.copy()

            if frame_to_process is None:
                time.sleep(0.04)
                continue

            yolo_sess = None
            yolo_lock = None
            try:
                from app.ai.gpu_allocator import gpu_pool, initialize_gpu_pool
                model_path = _get_yolo_pool_onnx_path()
                if model_path:
                    if not gpu_pool.is_ready:
                        initialize_gpu_pool(model_path)
                    cam_key = self.state.camera_id
                    yolo_sess, yolo_lock, _gpu_id = gpu_pool.acquire(cam_key)
            except Exception as _pool_err:
                logger.debug(f"[Crowd-AI-Worker:{self.state.camera_id}] GPU pool error: {_pool_err}")
                # Fallback: use the legacy compatibility helper
                yolo_sess = get_shared_yolo_engine()

            if yolo_sess is None:
                time.sleep(0.2)
                continue

            try:
                h_orig, w_orig = frame_to_process.shape[:2]
                img_resized = cv2.resize(frame_to_process, (640, 640))
                inp = (img_resized.transpose(2, 0, 1).astype(np.float32) / 255.0)[np.newaxis, ...]
                inp_name = yolo_sess.get_inputs()[0].name
                out_name = yolo_sess.get_outputs()[0].name

                # Per-GPU lock: only cameras sharing the same GPU serialize here.
                # Cameras on different GPUs (e.g. GPU-0 vs GPU-3) run in parallel.
                if yolo_lock is not None:
                    with yolo_lock:
                        outputs = yolo_sess.run([out_name], {inp_name: inp})
                else:
                    outputs = yolo_sess.run([out_name], {inp_name: inp})


                preds = np.squeeze(outputs[0]).T  # (8400, 84)
                person_scores = preds[:, 4]
                # Dual-threshold detection: low threshold (0.16) for existing track continuity, high (0.26) for new tracks
                mask = person_scores > 0.16
                filtered_preds = preds[mask]

                sx = w_orig / 640.0
                sy = h_orig / 640.0
                raw_boxes = []
                raw_scores = []
                for row in filtered_preds:
                    cx, cy, bw, bh = row[0], row[1], row[2], row[3]
                    x1 = int((cx - bw / 2) * sx)
                    y1 = int((cy - bh / 2) * sy)
                    raw_boxes.append([x1, y1, int(bw * sx), int(bh * sy)])
                    raw_scores.append(float(row[4]))

                indices = cv2.dnn.NMSBoxes(raw_boxes, raw_scores, score_threshold=0.16, nms_threshold=0.45)
                high_detections = []
                low_detections = []

                if len(indices) > 0:
                    for idx in indices.flatten():
                        bx, by, bw, bh = raw_boxes[idx]
                        x1 = max(0, bx)
                        y1 = max(0, by)
                        x2 = min(w_orig, bx + bw)
                        y2 = min(h_orig, by + bh)
                        conf = raw_scores[idx]
                        det_c = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
                        det_tc = (det_c[0], float(y1))
                        det_bc = (det_c[0], float(y2))
                        det_obj = {
                            "bbox": [float(x1), float(y1), float(x2), float(y2)],
                            "centroid": det_c,
                            "top_center": det_tc,
                            "bottom_center": det_bc,
                            "confidence": conf,
                        }
                        if conf >= 0.26:
                            high_detections.append(det_obj)
                        else:
                            low_detections.append(det_obj)

                curr_time = time.time()
                dt = max(0.02, min(0.4, curr_time - getattr(self, "_last_track_time", curr_time)))
                self._last_track_time = curr_time

                # -----------------------------------------------------------
                # Continuous Multi-Object Tracking with Temporal Smoothing & Coasting
                # -----------------------------------------------------------
                # 1. Predict next positions for all existing active tracks based on velocity
                for trk in self._crowd_tracks.values():
                    vx, vy = trk.get("velocity", (0.0, 0.0))
                    decay = 0.88 if trk.get("misses", 0) > 0 else 1.0
                    vx *= decay
                    vy *= decay
                    trk["velocity"] = (vx, vy)

                    bw = trk["bbox"][2] - trk["bbox"][0]
                    bh = trk["bbox"][3] - trk["bbox"][1]
                    pred_cx = trk["centroid"][0] + vx * dt
                    pred_cy = trk["centroid"][1] + vy * dt
                    trk["pred_bbox"] = [
                        max(0.0, pred_cx - bw / 2.0),
                        max(0.0, pred_cy - bh / 2.0),
                        min(float(w_orig), pred_cx + bw / 2.0),
                        min(float(h_orig), pred_cy + bh / 2.0),
                    ]
                    trk["pred_centroid"] = (pred_cx, pred_cy)

                # 2. Greedy bipartite matching helper
                def _match_tracks(track_ids, detections, min_iou=0.15, max_dist_mult=1.4):
                    matches = []
                    unmatched_t = set(track_ids)
                    unmatched_d = set(range(len(detections)))
                    candidates = []
                    for tid in track_ids:
                        trk = self._crowd_tracks[tid]
                        p_box = trk["pred_bbox"]
                        p_c = trk["pred_centroid"]
                        bw = p_box[2] - p_box[0]
                        bh = p_box[3] - p_box[1]
                        max_d = max(160.0, max(bw, bh) * max_dist_mult)
                        for d_idx, det in enumerate(detections):
                            iou = _box_iou(p_box, det["bbox"])
                            dist = math.hypot(det["centroid"][0] - p_c[0], det["centroid"][1] - p_c[1])
                            if iou >= min_iou or dist <= max_d:
                                score = (iou * 2.5) + max(0.0, 1.0 - (dist / max_d))
                                candidates.append((tid, d_idx, score))
                    candidates.sort(key=lambda x: x[2], reverse=True)
                    for tid, d_idx, _ in candidates:
                        if tid in unmatched_t and d_idx in unmatched_d:
                            matches.append((tid, d_idx))
                            unmatched_t.discard(tid)
                            unmatched_d.discard(d_idx)
                    return matches, list(unmatched_t), list(unmatched_d)

                all_tids = list(self._crowd_tracks.keys())
                # Pass 1: Match against high-confidence detections
                high_matches, unassigned_t, unassigned_high_d = _match_tracks(all_tids, high_detections, min_iou=0.15, max_dist_mult=1.4)
                # Pass 2: Match remaining tracks against low-confidence detections (keeps occluded/sitting humans alive!)
                low_matches, still_unmatched_t, _ = _match_tracks(unassigned_t, low_detections, min_iou=0.10, max_dist_mult=1.2)

                matched_det_map = {}
                for tid, d_idx in high_matches:
                    matched_det_map[tid] = high_detections[d_idx]
                for tid, d_idx in low_matches:
                    matched_det_map[tid] = low_detections[d_idx]

                # Update matched tracks with smooth bounding box and velocity
                for tid, det in matched_det_map.items():
                    trk = self._crowd_tracks[tid]
                    trk["misses"] = 0
                    trk["hits"] = trk.get("hits", 0) + 1
                    trk["confidence"] = det["confidence"]
                    det_c = det["centroid"]
                    inst_vx = (det_c[0] - trk["centroid"][0]) / dt
                    inst_vy = (det_c[1] - trk["centroid"][1]) / dt
                    trk["velocity"] = (0.5 * trk.get("velocity", (0.0, 0.0))[0] + 0.5 * inst_vx, 0.5 * trk.get("velocity", (0.0, 0.0))[1] + 0.5 * inst_vy)
                    # Smooth box (75% new detection, 25% previous box)
                    trk["bbox"] = [0.75 * d + 0.25 * b for d, b in zip(det["bbox"], trk["bbox"])]
                    trk["centroid"] = ((trk["bbox"][0] + trk["bbox"][2]) / 2.0, (trk["bbox"][1] + trk["bbox"][3]) / 2.0)
                    trk["top_center"] = (trk["centroid"][0], trk["bbox"][1])
                    trk["bottom_center"] = (trk["centroid"][0], trk["bbox"][3])
                    trk["last_seen"] = curr_time
                    if "history" not in trk:
                        trk["history"] = deque(maxlen=20)
                    trk["history"].append((trk["centroid"], curr_time))
                    if "loco_history" not in trk:
                        trk["loco_history"] = deque(maxlen=25)
                    bh_curr = trk["bbox"][3] - trk["bbox"][1]
                    trk["loco_history"].append((curr_time, trk["centroid"], trk["bottom_center"], bh_curr))

                # Update still unmatched tracks (coast mode: advances with velocity, keeps box alive!)
                for tid in still_unmatched_t:
                    trk = self._crowd_tracks[tid]
                    trk["misses"] = trk.get("misses", 0) + 1
                    trk["bbox"] = trk["pred_bbox"]
                    trk["centroid"] = trk["pred_centroid"]
                    trk["top_center"] = (trk["centroid"][0], trk["bbox"][1])
                    trk["bottom_center"] = (trk["centroid"][0], trk["bbox"][3])
                    if "history" not in trk:
                        trk["history"] = deque(maxlen=20)
                    trk["history"].append((trk["centroid"], curr_time))
                    if "loco_history" not in trk:
                        trk["loco_history"] = deque(maxlen=25)
                    bh_curr = trk["bbox"][3] - trk["bbox"][1]
                    trk["loco_history"].append((curr_time, trk["centroid"], trk["bottom_center"], bh_curr))

                # Spawn new tracks for unassigned high detections
                for d_idx in unassigned_high_d:
                    det = high_detections[d_idx]
                    det_c = det["centroid"]
                    # Prevent duplicate track if too close to an existing track
                    too_close = False
                    for existing_trk in self._crowd_tracks.values():
                        if math.hypot(det_c[0] - existing_trk["centroid"][0], det_c[1] - existing_trk["centroid"][1]) < 45.0:
                            too_close = True
                            break
                    if too_close:
                        continue

                    new_tid = self._next_track_id
                    self._next_track_id += 1
                    new_crossed = set()
                    for old_trk in self._crowd_tracks.values():
                        if old_trk.get("crossed_lines"):
                            if math.hypot(det_c[0] - old_trk["centroid"][0], det_c[1] - old_trk["centroid"][1]) < 100.0:
                                new_crossed.update(old_trk["crossed_lines"])
                                break
                    bh_new = det["bbox"][3] - det["bbox"][1]
                    self._crowd_tracks[new_tid] = {
                        "track_id": new_tid,
                        "bbox": det["bbox"],
                        "centroid": det_c,
                        "top_center": det["top_center"],
                        "bottom_center": det["bottom_center"],
                        "velocity": (0.0, 0.0),
                        "confidence": det["confidence"],
                        "hits": 1,
                        "misses": 0,
                        "last_seen": curr_time,
                        "history": deque([(det_c, curr_time)], maxlen=20),
                        "loco_history": deque([(curr_time, det_c, det["bottom_center"], bh_new)], maxlen=25),
                        "cooldown_until": 0.0,
                        "crossed_lines": new_crossed,
                        "movement_state": "MOVING",
                        "last_moving_time": curr_time,
                        "stopped_frames": 0,
                    }

                # Prune tracks inactive for > 18 frames (~2.5s) or off-screen
                stale_tids = [
                    tid for tid, trk in self._crowd_tracks.items()
                    if trk.get("misses", 0) > 18 or (curr_time - trk.get("last_seen", curr_time)) > 3.0
                    or trk["bbox"][2] < 0 or trk["bbox"][3] < 0 or trk["bbox"][0] > w_orig or trk["bbox"][1] > h_orig
                ]
                for tid in stale_tids:
                    del self._crowd_tracks[tid]

                purposes = self.state.ai_purposes or ["ENTRY_EXIT"]

                # -----------------------------------------------------------
                # 1. ENTRY / EXIT Mode: Trajectory Segment Crossing (Strict No-Touch)
                # -----------------------------------------------------------
                if any(p in purposes for p in ("ENTRY", "EXIT", "ENTRY_EXIT")) and self._cached_roi_lines:
                    for trk in list(self._crowd_tracks.values()):
                        if trk.get("hits", 0) < 2:
                            continue
                        hist = list(trk.get("history", []))
                        if len(hist) < 2:
                            continue

                        for line in self._cached_roi_lines:
                            line_id = str(line.get("id") or line.get("name") or "line")

                            # Deduplication: already counted for this person
                            if line_id in trk.get("crossed_lines", set()):
                                continue

                            # Cooldown
                            if curr_time < trk.get("cooldown_until", 0.0):
                                continue

                            l1 = (int(line["start"]["x"] * w_orig), int(line["start"]["y"] * h_orig))
                            l2 = (int(line["end"]["x"] * w_orig), int(line["end"]["y"] * h_orig))

                            vx = l2[0] - l1[0]
                            vy = l2[1] - l1[1]
                            l_len = math.hypot(vx, vy)
                            if l_len > 0:
                                ext_x = int(vx / l_len * 25)
                                ext_y = int(vy / l_len * 25)
                                el1 = (l1[0] - ext_x, l1[1] - ext_y)
                                el2 = (l2[0] + ext_x, l2[1] + ext_y)
                            else:
                                el1, el2 = l1, l2

                            has_crossed = False
                            crossing_prev = None

                            # Check trajectory segments across el1 -> el2 over last 6 history frames
                            for i in range(max(0, len(hist) - 6), len(hist) - 1):
                                p_a = hist[i][0]
                                p_b = hist[i + 1][0]
                                # Centroid trajectory crossing
                                if _segments_cross(p_a, p_b, el1, el2):
                                    has_crossed = True
                                    crossing_prev = p_a
                                    break
                                # Feet trajectory crossing
                                bh = trk["bbox"][3] - trk["bbox"][1]
                                bc_a = (p_a[0], p_a[1] + bh * 0.45)
                                bc_b = (p_b[0], p_b[1] + bh * 0.45)
                                if _segments_cross(bc_a, bc_b, el1, el2):
                                    has_crossed = True
                                    crossing_prev = p_a
                                    break

                            if not has_crossed:
                                continue

                            # Rule A: Mark line crossed for this track IMMEDIATELY
                            trk["crossed_lines"].add(line_id)
                            trk["cooldown_until"] = curr_time + 4.0

                            # Rule B: Spatial deduplication against recent crossings
                            is_dup = False
                            for rc in self._recent_crossings:
                                if (curr_time - rc["time"]) < 2.2 and rc.get("line_id") == line_id:
                                    if math.hypot(trk["centroid"][0] - rc["pos"][0], trk["centroid"][1] - rc["pos"][1]) < 120.0:
                                        is_dup = True
                                        break
                            if is_dup:
                                continue

                            self._recent_crossings.append({
                                "time": curr_time,
                                "pos": trk["centroid"],
                                "line_id": line_id,
                                "track_id": trk["track_id"],
                            })
                            self._recent_crossings = [rc for rc in self._recent_crossings if (curr_time - rc["time"]) < 10.0]

                            # Direction determination using trajectory vector
                            start_c = crossing_prev or hist[0][0]
                            end_c = trk["centroid"]
                            mv_x = end_c[0] - start_c[0]
                            mv_y = end_c[1] - start_c[1]

                            cross_prod = vx * mv_y - vy * mv_x
                            line_type = str(line.get("type") or "").upper()
                            line_dir = (line.get("direction") or ("IN" if "ENTRY" in line_type else ("OUT" if "EXIT" in line_type else "BOTH"))).upper()

                            is_pure_entry = ("ENTRY" in purposes and "EXIT" not in purposes) or line_type == "ENTRY_LINE"
                            is_pure_exit = ("EXIT" in purposes and "ENTRY" not in purposes) or line_type == "EXIT_LINE"

                            if is_pure_exit or (not is_pure_entry and (line_dir == "OUT" or (cross_prod < 0 and line_dir == "BOTH"))):
                                self.state.out_count += 1
                                inflow_d, outflow_d = 0, 1
                                crossing_label = "OUT"
                            else:
                                self.state.in_count += 1
                                inflow_d, outflow_d = 1, 0
                                crossing_label = "IN"

                            self.state.occupancy_count = max(0, self.state.in_count - self.state.out_count)
                            logger.info(
                                f"[YOLO11x-Crowd:{self.state.camera_id}] Track #{trk['track_id']} CROSSED '{line.get('name')}': "
                                f"{crossing_label} | IN={self.state.in_count} OUT={self.state.out_count} OCCUPANCY={self.state.occupancy_count}"
                            )

                            telemetry_payload = {
                                "camera_id": self.state.camera_id,
                                "camera_code": self.state.camera_id,
                                "in_count": self.state.in_count,
                                "out_count": self.state.out_count,
                                "occupancy": self.state.occupancy_count,
                                "current_occupancy": self.state.occupancy_count,
                                "headcount": len(self._crowd_tracks),
                                "crossing": crossing_label,
                                "inflow_delta": inflow_d,
                                "outflow_delta": outflow_d,
                                "line_name": line.get("name"),
                                "zone_code": getattr(self.state, "zone_code", "ZONE-A"),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            _emit_frs_event_threadsafe("crowd_telemetry", telemetry_payload)
                            _emit_frs_event_threadsafe("crowd_update", telemetry_payload)

                            _persist_crowd_snapshot_threadsafe(
                                camera_code=self.state.camera_id,
                                inflow_delta=inflow_d,
                                outflow_delta=outflow_d,
                                headcount=len(self._crowd_tracks),
                            )

                    # Periodic telemetry snapshot flush (every 30s)
                    if (curr_time - self._last_snapshot_persist) > 30.0:
                        self._last_snapshot_persist = curr_time
                        _persist_crowd_snapshot_threadsafe(
                            camera_code=self.state.camera_id,
                            inflow_delta=0,
                            outflow_delta=0,
                            headcount=len(self._crowd_tracks),
                        )

                # -----------------------------------------------------------
                # 2. ZONE Mode: Point-in-polygon headcount + density alert
                # -----------------------------------------------------------
                curr_centroids = [trk["centroid"] for trk in self._crowd_tracks.values() if trk.get("misses", 0) <= 10 and trk.get("hits", 0) >= 1]
                if "ZONE" in purposes:
                    zone_stats = []
                    total_zone_count = 0
                    for poly in self._cached_roi_polygons:
                        if poly.get("type") in ("CROWD_ROI", "ZONE_BOUNDARY"):
                            pts = poly["points"]
                            count = 0
                            for c in curr_centroids:
                                norm_pt = (c[0] / float(w_orig), c[1] / float(h_orig))
                                if _point_in_polygon(norm_pt, pts):
                                    count += 1

                            w_thresh = poly.get("warning_threshold", 50)
                            d_thresh = poly.get("danger_threshold", 80)
                            cap = poly.get("capacity", 100)

                            if count > d_thresh:
                                z_status = "DANGER"
                                z_color = (0, 0, 235)  # Red BGR
                            elif count > w_thresh:
                                z_status = "WARNING"
                                z_color = (0, 140, 255)  # Orange/Amber BGR
                            else:
                                z_status = "NORMAL"
                                z_color = (46, 204, 113)  # Green BGR

                            zone_stats.append({
                                "id": poly["id"],
                                "name": poly["name"],
                                "points": pts,
                                "count": count,
                                "warning_threshold": w_thresh,
                                "danger_threshold": d_thresh,
                                "capacity": cap,
                                "status": z_status,
                                "color": z_color,
                            })
                            total_zone_count += count

                    self._zone_stats = zone_stats
                    eff_count = total_zone_count if zone_stats else len(curr_centroids)
                    self.state.occupancy_count = eff_count
                    self.state.zone_data = [
                        {
                            "name": z["name"],
                            "count": z["count"],
                            "status": z["status"],
                            "warning_threshold": z["warning_threshold"],
                            "danger_threshold": z["danger_threshold"],
                        }
                        for z in zone_stats
                    ]

                    # Periodic zone persistence (every 5s or significant count change)
                    if (curr_time - getattr(self, "_last_zone_persist", 0.0)) > 5.0 or abs(eff_count - getattr(self, "_last_zone_count", -999)) >= 2:
                        self._last_zone_persist = curr_time
                        self._last_zone_count = eff_count
                        z_code = getattr(self.state, "zone_code", "ZONE-A")
                        first_poly = zone_stats[0] if zone_stats else {}
                        poly_cap = first_poly.get("capacity") or getattr(self.state, "zone_capacity", 100)
                        poly_warn = first_poly.get("warning_threshold") or getattr(self.state, "warning_threshold", 50)
                        poly_dang = first_poly.get("danger_threshold") or getattr(self.state, "danger_threshold", 80)

                        if eff_count >= poly_dang:
                            calc_status = "RED"
                        elif eff_count >= poly_warn:
                            calc_status = "ORANGE"
                        else:
                            calc_status = "GREEN"

                        calc_pct = round((eff_count / float(poly_cap)) * 100.0, 1) if poly_cap > 0 else 0.0

                        _persist_crowd_snapshot_threadsafe(
                            camera_code=self.state.camera_id,
                            inflow_delta=0,
                            outflow_delta=0,
                            headcount=eff_count,
                            zone_code_override=z_code,
                        )
                        _emit_frs_event_threadsafe("zone_update", {
                            "camera_id": self.state.camera_id,
                            "camera_code": self.state.camera_id,
                            "zone_code": z_code,
                            "current_people": eff_count,
                            "capacity": poly_cap,
                            "status": calc_status,
                            "density_pct": calc_pct,
                            "occupancy": eff_count,
                            "zone_data": self.state.zone_data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                # -----------------------------------------------------------
                # Locomotion Speed & Movement State for All Active Tracks
                # -----------------------------------------------------------
                for trk in self._crowd_tracks.values():
                    if trk.get("misses", 0) > 4:
                        continue
                    l_hist = list(trk.get("loco_history", []))
                    if len(l_hist) < 3:
                        continue

                    t_now = l_hist[-1][0]
                    # Select baseline sample from ~0.35s - 1.0s ago
                    s_base = l_hist[0]
                    for s in l_hist:
                        if (t_now - s[0]) <= 1.0:
                            s_base = s
                            break

                    dt_loco = t_now - s_base[0]
                    if dt_loco >= 0.28:
                        # Ground feet displacement
                        d_feet = math.hypot(l_hist[-1][2][0] - s_base[2][0], l_hist[-1][2][1] - s_base[2][1])
                        # Centroid displacement
                        d_c = math.hypot(l_hist[-1][1][0] - s_base[1][0], l_hist[-1][1][1] - s_base[1][1])
                        # Perspective height expansion/contraction
                        d_bh = abs(l_hist[-1][3] - s_base[3])

                        speed_feet_s = d_feet / dt_loco
                        speed_c_s = d_c / dt_loco
                        speed_bh_s = d_bh / dt_loco

                        # Combined effective locomotion speed:
                        # Captures lateral walking (d_c/d_feet) and axial approach down hallway (d_feet + d_bh)
                        eff_speed = max(speed_feet_s, speed_c_s, speed_feet_s * 0.7 + speed_bh_s * 0.5)

                        current_bh = max(50.0, trk["bbox"][3] - trk["bbox"][1])
                        norm_speed = eff_speed / current_bh

                        # Locomotion classification:
                        # WALKING: eff_speed >= 15.0 px/s OR feet speed >= 13.0 px/s OR height expansion >= 15.0 px/s OR norm_speed >= 0.05
                        is_walking = (
                            eff_speed >= 15.0
                            or speed_feet_s >= 13.0
                            or speed_bh_s >= 15.0
                            or norm_speed >= 0.05
                        )
                        # SLOW WALK: creeping / shuffling in queue
                        is_slow = (
                            eff_speed >= 5.0
                            or speed_feet_s >= 4.5
                            or norm_speed >= 0.018
                        )

                        if is_walking:
                            trk["last_moving_time"] = curr_time
                            trk["movement_state"] = "MOVING"
                            trk["stopped_frames"] = 0
                        elif is_slow:
                            # Hold MOVING through natural gait pauses between steps (up to 1.1s)
                            if (curr_time - trk.get("last_moving_time", 0.0)) < 1.1:
                                trk["movement_state"] = "MOVING"
                            else:
                                trk["movement_state"] = "SLOW"
                            trk["stopped_frames"] = 0
                        else:
                            # Below slow threshold: potential stationary
                            trk["stopped_frames"] = trk.get("stopped_frames", 0) + 1
                            # Hold MOVING during step transitions (up to 1.2s)
                            if (curr_time - trk.get("last_moving_time", 0.0)) < 1.2:
                                trk["movement_state"] = "MOVING"
                            elif trk["stopped_frames"] < 6:
                                trk["movement_state"] = "SLOW"
                            else:
                                trk["movement_state"] = "STOPPED"

                # -----------------------------------------------------------
                # 3. QUEUE Mode: Ground-truth queue tracking
                # -----------------------------------------------------------
                if "QUEUE" in purposes:
                    queue_polygons = [p for p in self._cached_roi_polygons if p.get("type") in ("QUEUE_ROI", "QUEUE_AREA")]

                    q_count = 0
                    for trk in self._crowd_tracks.values():
                        if trk.get("misses", 0) > 3:
                            trk["in_queue"] = False
                            continue
                        cx, cy = trk["centroid"]
                        bc = trk["bottom_center"]
                        in_q = False
                        if queue_polygons:
                            norm_c = (cx / float(w_orig), cy / float(h_orig))
                            norm_bc = (bc[0] / float(w_orig), bc[1] / float(h_orig))
                            for poly in queue_polygons:
                                pts = poly["points"]
                                if _point_in_polygon(norm_c, pts) or _point_in_polygon(norm_bc, pts):
                                    in_q = True
                                    break
                        else:
                            in_q = True

                        trk["in_queue"] = in_q
                        if in_q:
                            q_count += 1

                    self.state.occupancy_count = q_count
                    if q_count == 0:
                        self.state.queue_movement_status = "EMPTY"
                    else:
                        active_states = [
                            trk.get("movement_state", "STOPPED")
                            for trk in self._crowd_tracks.values()
                            if trk.get("in_queue") and trk.get("misses", 0) <= 2
                        ]
                        if not active_states:
                            self.state.queue_movement_status = "STOPPED"
                        elif "MOVING" in active_states:
                            self.state.queue_movement_status = "MOVING"
                        elif "SLOW" in active_states:
                            self.state.queue_movement_status = "SLOW"
                        else:
                            self.state.queue_movement_status = "STOPPED"

                    if (curr_time - getattr(self, "_last_queue_persist", 0.0)) > 8.0 or self.state.queue_movement_status != getattr(self, "_last_queue_status", ""):
                        self._last_queue_persist = curr_time
                        self._last_queue_status = self.state.queue_movement_status
                        _persist_queue_snapshot_threadsafe(
                            camera_code=self.state.camera_id,
                            headcount=q_count,
                            movement_status=self.state.queue_movement_status,
                            zone_code_override=getattr(self.state, "zone_code", "ZONE-A"),
                        )
                        _emit_frs_event_threadsafe("queue_update", {
                            "camera_id": self.state.camera_id,
                            "camera_code": self.state.camera_id,
                            "zone_code": getattr(self.state, "zone_code", "ZONE-A"),
                            "headcount": q_count,
                            "occupancy": q_count,
                            "queue_movement_status": self.state.queue_movement_status,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                self._prev_centroids = curr_centroids
                with self._crowd_boxes_lock:
                    self._crowd_boxes = [
                        {
                            "track_id": trk["track_id"],
                            "bbox": [int(round(v)) for v in trk["bbox"]],
                            "head": [int(round(trk["top_center"][0])), int(round(trk["bbox"][1] + max(4, (trk["bbox"][3] - trk["bbox"][1]) * 0.18)))],
                            "centroid": [int(round(trk["centroid"][0])), int(round(trk["centroid"][1]))],
                            "bottom_center": [int(round(trk["bottom_center"][0])), int(round(trk["bottom_center"][1]))],
                            "label": f"HUMAN {round(trk.get('confidence', 0.85) * 100)}%",
                            "confidence": trk.get("confidence", 0.85),
                            "expiry": curr_time + 1.5,
                            "in_queue": trk.get("in_queue", False),
                            "movement_state": trk.get("movement_state", "STOPPED"),
                            "misses": trk.get("misses", 0),
                        }
                        for trk in self._crowd_tracks.values()
                        if trk.get("misses", 0) <= 2 and trk.get("hits", 0) >= 1
                    ]
                self.state.detections_count = len(self._crowd_boxes)

            except Exception as e:
                logger.warning(f"[Crowd-AI-Worker:{self.state.camera_id}] Inference loop warning: {type(e).__name__}: {e}")

            time.sleep(0.12)

    def run(self):
        (FaceModel, IdentityMatcher, FaceQualityAssessor, FaceTracker, RTSPReader, db) = _load_frs_components()

        # For CROWD-only cameras, RTSPReader is enough — FaceModel is not needed.
        # Only abort if RTSPReader itself failed to load (truly unrecoverable).
        if RTSPReader is None:
            self.state.status = "error"
            logger.error(f"[FRS-Worker:{self.state.camera_id}] RTSPReader unavailable — cannot start worker.")
            return

        if FaceModel is None and not self.state.is_frs:
            # CROWD camera: FRS/InsightFace not needed. Proceed with RTSP + YOLO only.
            logger.info(f"[FRS-Worker:{self.state.camera_id}] CROWD mode — skipping FRS components (InsightFace not loaded).")
            face_model, matcher, tracker = None, None, None
        elif FaceModel is None:
            self.state.status = "error"
            logger.error(f"[FRS-Worker:{self.state.camera_id}] FRS mode requested but FaceModel unavailable.")
            return
        else:
            face_model, matcher = get_shared_engine()
            tracker = FaceTracker(max_missed_frames=15, min_iou=0.10, max_center_distance=180.0) if FaceTracker else None

        try:
            reader = RTSPReader(url=self.state.rtsp_url, resize=(1280, 720))
            self.state.reader = reader
            self.reader = reader
            reader.start()
            self.state.status = "online"
            logger.info(f"[FRS-Worker:{self.state.camera_id}] RTSP reader started: {self.state.rtsp_url}")

            # Start decoupled background FRS AI thread (only if face model loaded)
            if face_model is not None and tracker is not None:
                ai_thread = threading.Thread(
                    target=self._ai_detection_loop,
                    args=(face_model, matcher, tracker),
                    daemon=True,
                    name=f"FRS-AI-{self.state.camera_id}"
                )
                ai_thread.start()

            # Start decoupled background YOLO11x Crowd AI thread (always)
            crowd_thread = threading.Thread(
                target=self._crowd_ai_detection_loop,
                daemon=True,
                name=f"CROWD-AI-{self.state.camera_id}"
            )
            crowd_thread.start()

            while self.state.running:
                rgb = reader.get_frame(timeout=0.04)
                if rgb is None:
                    continue

                # Pass latest frame to AI detection threads and worker state
                with self._ai_lock:
                    self._latest_ai_rgb = rgb
                with self.state.frame_lock:
                    self.state.latest_rgb = rgb

                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                h, w = bgr.shape[:2]

                # 1. Clean frame without ANY annotations/overlays (always pure camera video)
                ok_clean, clean_buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 72])
                if ok_clean:
                    with self.state.frame_lock:
                        self.state.latest_clean_frame = clean_buf.tobytes()

                # 2. FRS Mode Overlays
                if self.state.is_frs:
                    bgr_annotated = bgr.copy()
                    now = time.time()
                    with self._boxes_lock:
                        boxes = [b for b in self._active_boxes if b["expiry"] > now]

                    for b in boxes:
                        x1, y1, x2, y2 = b["bbox"]
                        is_match = b["is_match"]
                        color = (46, 204, 113) if is_match else (255, 180, 0)
                        
                        # Draw bounding box
                        cv2.rectangle(bgr_annotated, (x1, y1), (x2, y2), color, 2)

                        # Label badge
                        lbl = b["label"]
                        (lw, lh), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        top_y = max(lh + 6, y1)
                        cv2.rectangle(bgr_annotated, (x1, top_y - lh - 6), (x1 + lw + 6, top_y + 2), color, -1)
                        cv2.putText(bgr_annotated, lbl, (x1 + 3, top_y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

                    ok, jpeg_buf = cv2.imencode(".jpg", bgr_annotated, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    if ok:
                        with self.state.frame_lock:
                            self.state.latest_frame = jpeg_buf.tobytes()

                # 3. Crowd Mode Overlays (YOLO11x Person Detection & Line/Zone/Queue Analytics)
                elif getattr(self.state, "crowd_ai_active", False):
                    bgr_crowd = bgr.copy()
                    now = time.time()
                    with self._crowd_boxes_lock:
                        cboxes = [b for b in self._crowd_boxes if b.get("expiry", 0) > now]

                    purposes = self.state.ai_purposes or ["ENTRY_EXIT"]

                    # -------------------------------------------------------
                    # A. ENTRY / EXIT COUNTING OVERLAY
                    # -------------------------------------------------------
                    is_entry = "ENTRY" in purposes and "EXIT" not in purposes
                    is_exit = "EXIT" in purposes and "ENTRY" not in purposes
                    if is_entry or is_exit or "ENTRY_EXIT" in purposes:
                        # Draw person boxes
                        box_col = (46, 204, 113) if is_entry else ((0, 80, 245) if is_exit else (46, 204, 113))
                        for cb in cboxes:
                            x1, y1, x2, y2 = cb["bbox"]
                            cv2.rectangle(bgr_crowd, (x1, y1), (x2, y2), box_col, 2)
                            clbl = cb["label"]
                            (lw, lh), _ = cv2.getTextSize(clbl, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                            top_y = max(lh + 6, y1)
                            cv2.rectangle(bgr_crowd, (x1, top_y - lh - 6), (x1 + lw + 6, top_y + 2), box_col, -1)
                            cv2.putText(bgr_crowd, clbl, (x1 + 3, top_y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

                        # Draw configured counting lines
                        for line in self._cached_roi_lines:
                            l1 = (int(line["start"]["x"] * w), int(line["start"]["y"] * h))
                            l2 = (int(line["end"]["x"] * w), int(line["end"]["y"] * h))
                            line_type = str(line.get("type") or "").upper()
                            if is_entry or line_type == "ENTRY_LINE":
                                line_color = (46, 204, 113)  # Green
                                tag = f"ENTRY LINE | TOTAL IN: {self.state.in_count}"
                            elif is_exit or line_type == "EXIT_LINE":
                                line_color = (0, 0, 235)  # Red
                                tag = f"EXIT LINE | TOTAL OUT: {self.state.out_count}"
                            else:
                                line_color = (0, 215, 255) if "ENTRY" in line_type else ((255, 100, 50) if "EXIT" in line_type else (255, 200, 0))
                                tag = f"{line.get('name', 'LINE')} | IN: {self.state.in_count} | OUT: {self.state.out_count}"

                            cv2.line(bgr_crowd, l1, l2, line_color, 3, cv2.LINE_AA)
                            cv2.circle(bgr_crowd, l1, 6, line_color, -1)
                            cv2.circle(bgr_crowd, l2, 6, line_color, -1)
                            mx = (l1[0] + l2[0]) // 2
                            my = (l1[1] + l2[1]) // 2
                            cv2.putText(bgr_crowd, tag, (max(10, mx - 100), max(22, my - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

                        # End of Entry/Exit lines and boxes

                    # -------------------------------------------------------
                    # B. ZONE DENSITY MANAGEMENT OVERLAY (Polygons + Head Dots)
                    # -------------------------------------------------------
                    if "ZONE" in purposes:
                        worst_status = "NORMAL"
                        overlay = bgr_crowd.copy()

                        # 1. Draw semi-transparent color-coded zone polygons
                        for z in self._zone_stats:
                            pts = z["points"]
                            if len(pts) >= 3:
                                poly_arr = np.array(
                                    [[int(p["x"] * w if isinstance(p, dict) else p[0] * w), int(p["y"] * h if isinstance(p, dict) else p[1] * h)] for p in pts],
                                    dtype=np.int32
                                )
                                z_color = z["color"]
                                cv2.fillPoly(overlay, [poly_arr], z_color)
                                cv2.polylines(bgr_crowd, [poly_arr], True, z_color, 3, cv2.LINE_AA)

                                # Centroid for zone tag
                                M = cv2.moments(poly_arr)
                                if M["m00"] != 0:
                                    cx = int(M["m10"] / M["m00"])
                                    cy = int(M["m01"] / M["m00"])
                                else:
                                    cx, cy = poly_arr[0][0], poly_arr[0][1]

                                z_tag = f"{z['name']}: {z['count']}/{z['warning_threshold']} ({z['status']})"
                                (tw, th), _ = cv2.getTextSize(z_tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                                cv2.rectangle(bgr_crowd, (max(5, cx - tw // 2 - 6), max(25, cy - 18)), (min(w - 5, cx + tw // 2 + 6), min(h - 5, cy + 6)), (15, 23, 42), -1)
                                cv2.rectangle(bgr_crowd, (max(5, cx - tw // 2 - 6), max(25, cy - 18)), (min(w - 5, cx + tw // 2 + 6), min(h - 5, cy + 6)), z_color, 1)
                                cv2.putText(bgr_crowd, z_tag, (max(10, cx - tw // 2), max(20, cy - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

                                if z["status"] == "DANGER":
                                    worst_status = "DANGER"
                                elif z["status"] == "WARNING" and worst_status != "DANGER":
                                    worst_status = "WARNING"

                        # Blend polygon fill overlay (25% opacity)
                        if self._zone_stats:
                            cv2.addWeighted(overlay, 0.25, bgr_crowd, 0.75, 0, bgr_crowd)

                        # 2. Draw Head Count Dots (glowing cyan / amber dots at head location)
                        for cb in cboxes:
                            hx, hy = cb.get("head", ((cb["bbox"][0] + cb["bbox"][2]) // 2, cb["bbox"][1] + 10))
                            # Outer ring
                            cv2.circle(bgr_crowd, (hx, hy), 7, (255, 255, 0), -1, cv2.LINE_AA)
                            cv2.circle(bgr_crowd, (hx, hy), 9, (0, 255, 255), 2, cv2.LINE_AA)
                            # Center dot
                            cv2.circle(bgr_crowd, (hx, hy), 2, (0, 0, 0), -1, cv2.LINE_AA)

                    # -------------------------------------------------------
                    # C. QUEUE MANAGEMENT OVERLAY (Queue Box + Speed Flow)
                    # -------------------------------------------------------
                    if "QUEUE" in purposes:
                        # Draw Queue Polygons / Area Box in Amber
                        for poly in self._cached_roi_polygons:
                            if poly.get("type") not in ("QUEUE_ROI", "QUEUE_AREA"):
                                continue
                            pts = poly["points"]
                            if len(pts) >= 3:
                                poly_arr = np.array(
                                    [[int(p["x"] * w if isinstance(p, dict) else p[0] * w), int(p["y"] * h if isinstance(p, dict) else p[1] * h)] for p in pts],
                                    dtype=np.int32
                                )
                                cv2.polylines(bgr_crowd, [poly_arr], True, (34, 153, 210), 3, cv2.LINE_AA)
                                for pt in poly_arr:
                                    cv2.circle(bgr_crowd, tuple(pt), 5, (34, 153, 210), -1)
                                p0 = poly_arr[0]
                                cv2.putText(bgr_crowd, "QUEUE AREA", (max(10, p0[0]), max(20, p0[1] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (34, 153, 210), 1, cv2.LINE_AA)

                        # Draw direction lines if any (only DIRECTION_LINE type)
                        for line in self._cached_roi_lines:
                            if line.get("type") != "DIRECTION_LINE":
                                continue
                            l1 = (int(line["start"]["x"] * w), int(line["start"]["y"] * h))
                            l2 = (int(line["end"]["x"] * w), int(line["end"]["y"] * h))
                            cv2.line(bgr_crowd, l1, l2, (34, 153, 210), 2, cv2.LINE_AA)
                            cv2.circle(bgr_crowd, l1, 4, (34, 153, 210), -1)
                            cv2.circle(bgr_crowd, l2, 4, (34, 153, 210), -1)

                        # Draw person boxes & status indicators
                        for cb in cboxes:
                            x1, y1, x2, y2 = cb["bbox"]
                            in_q = cb.get("in_queue", False)
                            p_state = cb.get("movement_state", "STOPPED")

                            if not in_q:
                                box_color = (160, 160, 160)
                                tag = "HUMAN"
                            elif p_state == "MOVING":
                                box_color = (46, 204, 113)  # Bright Green
                                tag = "WALKING"
                            elif p_state == "SLOW":
                                box_color = (34, 153, 210)  # Amber
                                tag = "SLOW WALK"
                            else:
                                box_color = (0, 0, 235)  # Distinct Red
                                tag = "STANDING"

                            cv2.rectangle(bgr_crowd, (x1, y1), (x2, y2), box_color, 2)
                            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                            top_y = max(th + 6, y1)
                            cv2.rectangle(bgr_crowd, (x1, top_y - th - 6), (x1 + tw + 6, top_y + 2), box_color, -1)
                            cv2.putText(bgr_crowd, tag, (x1 + 3, top_y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

                            # Head indicator
                            hx, hy = cb.get("head", ((x1 + x2) // 2, y1 + 10))
                            cv2.circle(bgr_crowd, (hx, hy), 4, (0, 255, 255), -1, cv2.LINE_AA)

                            # Ground / Feet indicator for queue members
                            if in_q:
                                gx, gy = cb.get("bottom_center", ((x1 + x2) // 2, y2))
                                cv2.circle(bgr_crowd, (gx, gy), 4, box_color, -1, cv2.LINE_AA)

                    # -------------------------------------------------------
                    # D. CONSOLIDATED MULTI-PURPOSE TOP HUD BAR
                    # -------------------------------------------------------
                    cv2.rectangle(bgr_crowd, (0, 0), (w, 30), (15, 23, 42), -1)
                    hud_parts = []
                    if is_entry:
                        hud_parts.append(f"ENTRY: {self.state.in_count}")
                    elif is_exit:
                        hud_parts.append(f"EXIT: {self.state.out_count}")
                    elif "ENTRY_EXIT" in purposes or ("ENTRY" in purposes and "EXIT" in purposes):
                        hud_parts.append(f"IN: {self.state.in_count} | OUT: {self.state.out_count}")

                    if "ZONE" in purposes:
                        z_occ = getattr(self.state, "occupancy_count", 0)
                        hud_parts.append(f"ZONE: {z_occ} PAX")

                    if "QUEUE" in purposes:
                        q_stat = getattr(self.state, "queue_movement_status", "STOPPED")
                        hud_parts.append(f"QUEUE: {self.state.occupancy_count} ({q_stat})")

                    hud_body = " | ".join(hud_parts) if hud_parts else f"OCCUPANCY: {self.state.occupancy_count}"
                    hud_final = f"YOLO11x AI | {hud_body}"
                    cv2.putText(bgr_crowd, hud_final, (12, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (46, 204, 113), 2, cv2.LINE_AA)

                    ok_cr, crowd_buf = cv2.imencode(".jpg", bgr_crowd, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    if ok_cr:
                        with self.state.frame_lock:
                            self.state.latest_crowd_frame = crowd_buf.tobytes()
                            self.state.latest_frame = crowd_buf.tobytes()
                else:
                    # Neither AI mode active: use clean frames
                    if ok_clean:
                        with self.state.frame_lock:
                            self.state.latest_frame = clean_buf.tobytes()
                            self.state.latest_crowd_frame = clean_buf.tobytes()

            reader.stop()
            self.state.status = "offline"
        except Exception as e:
            logger.error(f"[FRS-Worker:{self.state.camera_id}] Error: {e}")
            self.state.status = "error"


# ---------------------------------------------------------------------------
# API Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/frs-engine", tags=["FRS Engine (Live RTSP)"])


# ── Request / Response schemas ──────────────────────────────────────────────

class AddCameraRequest(BaseModel):
    camera_id: Optional[str] = None
    name: str = "Camera"
    rtsp_url: str
    camera_type: str = "FRS"  # "FRS" or "CROWD"
    is_frs: bool = True
    ai_purposes: Optional[List[str]] = Field(default_factory=lambda: ["ENTRY_EXIT", "ZONE"])
    zone_code: Optional[str] = "ZONE-A"


class CameraInfo(BaseModel):
    camera_id: str
    name: str
    rtsp_url: str
    status: str
    started_at: str
    detections_count: int
    stream_url: str
    is_frs: bool = True
    camera_type: str = "FRS"
    crowd_ai_active: bool = False
    in_count: int = 0
    out_count: int = 0
    occupancy_count: int = 0
    ai_purposes: List[str] = Field(default_factory=list)
    queue_movement_status: Optional[str] = "STOPPED"
    zone_data: Optional[List[dict]] = Field(default_factory=list)
    zone_code: Optional[str] = "ZONE-A"


# ── POST /cameras ────────────────────────────────────────────────────────────

@router.post("/cameras", response_model=CameraInfo, status_code=201)
async def add_frs_camera(req: AddCameraRequest):
    if req.camera_id and req.camera_id.strip():
        cam_id = req.camera_id.strip()
    else:
        with _workers_lock:
            existing_ids = set(_camera_workers.keys())
        idx = 1
        candidate = f"CAM-KHB-{idx:03d}"
        while candidate in existing_ids:
            idx += 1
            candidate = f"CAM-KHB-{idx:03d}"
        cam_id = candidate

    is_frs = req.is_frs if req.camera_type == "FRS" else False
    ai_purp = req.ai_purposes or (["ENTRY"] if req.camera_type == "CROWD" else ["FRS"])
    if req.camera_type == "CROWD" and isinstance(ai_purp, list):
        ai_purp = ai_purp[:2]
    zone_cd = (req.zone_code or "ZONE-A").upper().strip()

    with _workers_lock:
        existing_match = (cam_id, _camera_workers[cam_id]) if cam_id in _camera_workers else None

        if existing_match:
            old_id, state = existing_match
            url_changed = state.rtsp_url.strip() != req.rtsp_url.strip()

            if url_changed:
                logger.info(f"[FRS-Engine] RTSP URL changed for {cam_id}: {state.rtsp_url} -> {req.rtsp_url}. Stopping old worker and restarting.")
                state.running = False
                if hasattr(state, "reader") and state.reader:
                    try:
                        state.reader.stop()
                    except Exception:
                        pass
                if state.thread and state.thread.is_alive():
                    state.thread.join(timeout=1.5)
                _camera_workers.pop(old_id, None)
                existing_match = None
            else:
                if old_id != cam_id:
                    _camera_workers.pop(old_id, None)
                    state.camera_id = cam_id
                    _camera_workers[cam_id] = state
                state.is_frs = is_frs
                state.camera_type = req.camera_type
                state.ai_purposes = ai_purp
                state.zone_code = zone_cd
                if req.name and req.name != "Camera":
                    state.name = req.name
                logger.info(f"[FRS-Engine] Re-keyed and updated worker for {cam_id} ({req.camera_type}) in zone {zone_cd} with purposes {ai_purp}")

                # DB sync
                try:
                    from app.db.session import AsyncSessionLocal
                    from app.models.camera import Camera
                    from app.security.encryption import encrypt_credential
                    from sqlalchemy import select
                    async def _sync_cam_db():
                        async with AsyncSessionLocal() as pg_db:
                            clean_id = cam_id.replace("-FRS", "").replace("-CROWD", "")
                            stmt = select(Camera).where(Camera.camera_code.in_([cam_id, clean_id]))
                            res = await pg_db.execute(stmt)
                            for c in res.scalars().all():
                                c.zone_code = zone_cd
                                c.rtsp_url_encrypted = encrypt_credential(req.rtsp_url)
                                c.status = "online"
                                c.stream_status = "ONLINE"
                            await pg_db.commit()
                    await _sync_cam_db()
                except Exception as e:
                    logger.warning(f"Error updating camera in DB: {e}")

                return CameraInfo(
                    camera_id=cam_id,
                    name=state.name,
                    rtsp_url=state.rtsp_url,
                    status=state.status,
                    started_at=state.started_at,
                    detections_count=state.detections_count,
                    stream_url=f"/api/v1/frs-engine/cameras/{cam_id}/stream",
                    is_frs=state.is_frs,
                    camera_type=state.camera_type,
                    crowd_ai_active=getattr(state, "crowd_ai_active", False),
                    in_count=getattr(state, "in_count", 0),
                    out_count=getattr(state, "out_count", 0),
                    occupancy_count=getattr(state, "occupancy_count", 0),
                    ai_purposes=state.ai_purposes,
                    queue_movement_status=getattr(state, "queue_movement_status", "STOPPED"),
                    zone_data=getattr(state, "zone_data", []),
                    zone_code=getattr(state, "zone_code", "ZONE-A"),
                )

        state = CameraWorkerState(
            camera_id=cam_id,
            rtsp_url=req.rtsp_url,
            name=req.name,
            is_frs=is_frs,
            camera_type=req.camera_type,
            ai_purposes=ai_purp,
            zone_code=zone_cd,
        )
        worker = RTSPCameraWorker(state)
        state.running = True

        t = threading.Thread(
            target=worker.run,
            daemon=True,
            name=f"Camera-Worker-{cam_id}",
        )
        state.thread = t
        _camera_workers[cam_id] = state
        t.start()

    logger.info(f"[FRS-Engine] Camera added: {cam_id} ({req.camera_type}) in {zone_cd} -> {req.rtsp_url[:40]}...")

    # DB sync
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.camera import Camera
        from app.security.encryption import encrypt_credential
        from sqlalchemy import select
        async def _sync_new_cam_db():
            async with AsyncSessionLocal() as pg_db:
                clean_id = cam_id.replace("-FRS", "").replace("-CROWD", "")
                stmt = select(Camera).where(Camera.camera_code.in_([cam_id, clean_id]))
                res = await pg_db.execute(stmt)
                cams = res.scalars().all()
                if not cams:
                    import uuid
                    new_c = Camera(
                        id=uuid.uuid4(),
                        camera_code=clean_id,
                        name=req.name or f"Camera {clean_id}",
                        label=req.name or f"Camera {clean_id}",
                        camera_type=req.camera_type or "CROWD",
                        zone_code=zone_cd,
                        rtsp_url_encrypted=encrypt_credential(req.rtsp_url),
                        status="online",
                        stream_status="ONLINE",
                        enabled=True,
                    )
                    pg_db.add(new_c)
                else:
                    for c in cams:
                        c.zone_code = zone_cd
                        c.rtsp_url_encrypted = encrypt_credential(req.rtsp_url)
                        c.status = "online"
                        c.stream_status = "ONLINE"
                await pg_db.commit()
        await _sync_new_cam_db()
    except Exception as e:
        logger.warning(f"Error persisting new camera to DB: {e}")

    return CameraInfo(
        camera_id=cam_id,
        name=req.name,
        rtsp_url=req.rtsp_url,
        status="starting",
        started_at=state.started_at,
        detections_count=0,
        stream_url=f"/api/v1/frs-engine/cameras/{cam_id}/stream",
        is_frs=is_frs,
        camera_type=req.camera_type,
        zone_code=zone_cd,
    )


# ── GET /cameras ─────────────────────────────────────────────────────────────

@router.get("/cameras", response_model=List[CameraInfo])
async def list_frs_engine_cameras():
    """List all active FRS engine camera workers."""
    result = []
    with _workers_lock:
        for cam_id, state in _camera_workers.items():
            result.append(CameraInfo(
                camera_id=cam_id,
                name=state.name,
                rtsp_url=state.rtsp_url,
                status=state.status,
                started_at=state.started_at,
                detections_count=state.detections_count,
                stream_url=f"/api/v1/frs-engine/cameras/{cam_id}/stream",
                is_frs=state.is_frs,
                camera_type=state.camera_type,
                crowd_ai_active=getattr(state, "crowd_ai_active", False),
                in_count=getattr(state, "in_count", 0),
                out_count=getattr(state, "out_count", 0),
                occupancy_count=getattr(state, "occupancy_count", 0),
                ai_purposes=state.ai_purposes,
                queue_movement_status=getattr(state, "queue_movement_status", "STOPPED"),
                zone_data=getattr(state, "zone_data", []),
                zone_code=getattr(state, "zone_code", "ZONE-A"),
            ))
    return result


# ── DELETE /cameras/{id} ─────────────────────────────────────────────────────


@router.delete("/cameras/{camera_id}", status_code=200)
async def remove_frs_camera(camera_id: str, sync_db: bool = True):
    """Stop and remove an FRS camera worker and delete/disable from DB."""
    with _workers_lock:
        state = _camera_workers.pop(camera_id, None)
        if state is None:
            target_key = None
            target_clean = camera_id.replace("-FRS", "").replace("-CROWD", "").strip().lower()
            for cid, s in _camera_workers.items():
                cid_clean = cid.replace("-FRS", "").replace("-CROWD", "").strip().lower()
                if cid_clean == target_clean or cid.lower() == camera_id.lower():
                    target_key = cid
                    break
            if target_key:
                state = _camera_workers.pop(target_key, None)

    if state is not None:
        state.running = False
        if hasattr(state, "reader") and state.reader:
            try:
                state.reader.stop()
            except Exception:
                pass
        logger.info(f"[FRS-Engine] Camera removed: {camera_id}")

    if sync_db:
        try:
            from app.db.session import AsyncSessionLocal
            from app.services.camera_service import CameraService
            async def _sync_del():
                async with AsyncSessionLocal() as pg_db:
                    srv = CameraService(pg_db)
                    await srv.delete_camera(camera_id)
            if _main_loop and _main_loop.is_running():
                asyncio.run_coroutine_threadsafe(_sync_del(), _main_loop)
            else:
                asyncio.create_task(_sync_del())
        except Exception as ex:
            logger.warning(f"Error syncing camera deletion to DB: {ex}")

    return {"status": "ok", "removed": camera_id, "had_active_worker": state is not None}


def get_worker_for_camera(camera_code_or_id: str) -> Optional[CameraWorkerState]:
    """Resolves a CameraWorkerState for the requested camera code or ID with flexible mapping."""
    with _workers_lock:
        if not _camera_workers:
            return None
        # 1. Exact match
        if camera_code_or_id in _camera_workers:
            return _camera_workers[camera_code_or_id]

        # 2. Match without -FRS or -CROWD
        target_clean = camera_code_or_id.replace("-FRS", "").replace("-CROWD", "").strip().lower()
        for cid, state in _camera_workers.items():
            cid_clean = cid.replace("-FRS", "").replace("-CROWD", "").strip().lower()
            if cid_clean == target_clean or target_clean in cid_clean or cid_clean in target_clean:
                return state

        # 3. If there is a single active worker in the system, map it to the physical camera
        if len(_camera_workers) == 1:
            return next(iter(_camera_workers.values()))


        return None


def stop_frs_camera_worker(camera_code_or_id: str) -> bool:
    """Safely stops and unregisters any FRS engine worker running for the given physical camera."""
    state = get_worker_for_camera(camera_code_or_id)
    if state and state.running:
        state.running = False
        state.is_frs = False
        if state.thread and state.thread.is_alive():
            state.thread.join(timeout=2.0)
        with _workers_lock:
            keys_to_del = [k for k, v in _camera_workers.items() if v is state]
            for k in keys_to_del:
                _camera_workers.pop(k, None)
        logger.info(f"[FRS-Engine] Stopped and released RTSP worker for physical camera: {camera_code_or_id}")
        return True
    return False


def is_frs_worker_running(camera_code_or_id: str) -> bool:
    """Checks if an FRS engine worker is actively running for the given physical camera."""
    state = get_worker_for_camera(camera_code_or_id)
    return bool(state and state.running and state.is_frs)


def is_crowd_worker_running(camera_code_or_id: str) -> bool:
    """Checks if a Crowd AI (YOLO11x) worker is actively running for the given camera."""
    state = get_worker_for_camera(camera_code_or_id)
    return bool(state and state.running and getattr(state, "crowd_ai_active", False) and not state.is_frs)


def toggle_crowd_ai_camera_worker(camera_code_or_id: str, active: bool = True) -> bool:
    """Toggles Crowd AI (YOLO11x) on the existing RTSP stream without disconnecting the physical camera."""
    state = get_worker_for_camera(camera_code_or_id)
    if state and state.running:
        state.crowd_ai_active = active
        if active:
            state.is_frs = False
            state.camera_type = "CROWD"
        logger.info(f"[FRS-Engine] Camera {camera_code_or_id} crowd_ai_active set to {active} (is_frs={state.is_frs})")
        return True
    return False


def toggle_frs_camera_worker(camera_code_or_id: str, active: bool = True) -> bool:
    """Toggles FRS on the existing RTSP stream without disconnecting the physical camera."""
    state = get_worker_for_camera(camera_code_or_id)
    if state and state.running:
        state.is_frs = active
        if active:
            state.crowd_ai_active = False
            state.camera_type = "FRS"
        logger.info(f"[FRS-Engine] Camera {camera_code_or_id} is_frs set to {active} (crowd_ai_active={state.crowd_ai_active})")
        return True
    return False


def sync_worker_roi_lines(camera_code_or_id: str) -> bool:
    """Instructs the active worker to reload ROI counting lines and automatically start Crowd AI."""
    state = get_worker_for_camera(camera_code_or_id)
    if state and state.running:
        state.crowd_ai_active = True
        state.is_frs = False
        state.camera_type = "CROWD"
        if hasattr(state, "worker") and state.worker:
            state.worker._roi_lines_last_fetch = 0.0
            if hasattr(state.worker, "_queue_tracks"):
                state.worker._queue_tracks.clear()
            if hasattr(state.worker, "_crowd_tracks"):
                state.worker._crowd_tracks.clear()
        logger.info(f"[FRS-Engine] Camera {camera_code_or_id} synced ROI lines & activated YOLO11x Crowd AI")
        return True
    return False


def _generate_placeholder_jpeg(camera_id: str, message: str = "Connecting to camera stream...", submessage: str = "") -> bytes:
    try:
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        img[:] = (15, 23, 42)  # #0f172a
        cv2.rectangle(img, (20, 20), (1260, 700), (30, 41, 59), 2)
        cv2.putText(img, f"CAMERA: {camera_id}", (60, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (88, 166, 255), 2, cv2.LINE_AA)
        cv2.putText(img, message, (60, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (227, 179, 65), 2, cv2.LINE_AA)
        if submessage:
            cv2.putText(img, submessage[:80], (60, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(img, "Khairatabad Ganesh Command Center - Live Engine", (60, 640), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 116, 139), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes() if ok else b""
    except Exception:
        return b""


# ── GET /cameras/{id}/stream  (MJPEG) ────────────────────────────────────────

@router.get("/cameras/{camera_id}/stream")
async def stream_camera(camera_id: str):
    """MJPEG live stream from RTSP camera. Use as <img src='...'> in frontend."""
    state = get_worker_for_camera(camera_id)
    if state is None or not state.running:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} is not actively streaming")

    # Strict isolation: if request is for CROWD or worker is not in FRS mode, serve crowd or clean frames
    is_crowd = "-CROWD" in camera_id.upper() or state.camera_type == "CROWD" or not state.is_frs

    async def generate():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        placeholder_timer = 0.0
        while state.running:
            with state.frame_lock:
                if is_crowd:
                    if getattr(state, "crowd_ai_active", False):
                        frame = getattr(state, "latest_crowd_frame", None) or state.latest_clean_frame
                    else:
                        frame = getattr(state, "latest_clean_frame", None) or state.latest_frame
                else:
                    if state.is_frs:
                        frame = state.latest_frame
                    else:
                        frame = getattr(state, "latest_clean_frame", None) or state.latest_frame

            if frame:
                yield boundary + frame + b"\r\n"
                await asyncio.sleep(0.033)
            else:
                now = time.monotonic()
                if now - placeholder_timer >= 1.0:
                    placeholder_timer = now
                    status_text = "Connecting to camera stream..." if state.status != "error" else "RTSP stream offline / reconnecting..."
                    import re
                    safe_url = re.sub(r"://(.*)@", "://***:***@", state.rtsp_url) if "@" in state.rtsp_url else state.rtsp_url
                    ph_frame = _generate_placeholder_jpeg(state.camera_id, status_text, safe_url)
                    if ph_frame:
                        yield boundary + ph_frame + b"\r\n"
                await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.patch("/cameras/{camera_id}/toggle-crowd-ai")
async def api_toggle_crowd_ai(camera_id: str, active: bool = True):
    success = toggle_crowd_ai_camera_worker(camera_id, active)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera worker for {camera_id} not found or not running")
    return {"status": "success", "camera_id": camera_id, "crowd_ai_active": active}


@router.patch("/cameras/{camera_id}/toggle-frs")
async def api_toggle_frs(camera_id: str, active: bool = True):
    success = toggle_frs_camera_worker(camera_id, active)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera worker for {camera_id} not found or not running")
    return {"status": "success", "camera_id": camera_id, "is_frs": active}


@router.patch("/cameras/{camera_id}/reassign-purpose")
async def api_reassign_camera_purpose(camera_id: str, new_purpose: str):
    """
    Stops/disconnects existing pipeline configuration for a camera,
    permanently deletes old ROI geometries from PostgreSQL,
    and reassigns to the new purpose (ENTRY_EXIT, ZONE, or QUEUE).
    """
    valid_purposes = {"ENTRY", "EXIT", "ENTRY_EXIT", "ZONE", "QUEUE"}
    if isinstance(new_purpose, list):
        parsed_purposes = [str(p).strip().upper() for p in new_purpose if p]
    else:
        parsed_purposes = [p.strip().upper() for p in str(new_purpose).split(",") if p.strip()]

    invalid = [p for p in parsed_purposes if p not in valid_purposes]
    if invalid or not parsed_purposes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid purpose(s): {invalid}. Each must be one of: {', '.join(sorted(valid_purposes))}"
        )

    # Maximum 2 crowd functionalities per camera
    parsed_purposes = parsed_purposes[:2]

    state = get_worker_for_camera(camera_id)
    if state is None or not state.running:
        raise HTTPException(status_code=404, detail=f"Camera worker for {camera_id} not found or not running")

    clean_id = camera_id.replace("-FRS", "").replace("-CROWD", "")

    # 1. Permanently DELETE existing ROI geometry in PostgreSQL database
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.camera_roi import CameraROIConfiguration
        from sqlalchemy import delete

        async with AsyncSessionLocal() as pg_db:
            stmt = delete(CameraROIConfiguration).where(
                CameraROIConfiguration.camera_code.in_([camera_id, clean_id, state.camera_id])
            )
            res = await pg_db.execute(stmt)
            await pg_db.commit()
            logger.info(f"[FRS-Engine] Permanently deleted {res.rowcount} previous ROI geometries for camera {camera_id} in DB.")
    except Exception as e:
        logger.warning(f"[FRS-Engine] Disconnecting old DB geometry warning: {e}")

    # 2. Stop and disconnect worker pipeline in-memory
    with state.frame_lock:
        state.roi_lines = []
        if hasattr(state, "worker") and state.worker:
            state.worker._cached_roi_lines = []
            state.worker._cached_roi_polygons = []
            state.worker._zone_stats = []
            state.worker._roi_lines_last_fetch = 0.0
            state.worker._prev_centroids = []
            state.worker._prev_queue_centroids = []
            if hasattr(state.worker, "_queue_displacement_history"):
                state.worker._queue_displacement_history.clear()
            if hasattr(state.worker, "_crowd_boxes_lock"):
                with state.worker._crowd_boxes_lock:
                    state.worker._crowd_boxes.clear()

        # Reset counts & states
        state.in_count = 0
        state.out_count = 0
        state.occupancy_count = 0
        state.queue_movement_status = "STOPPED"
        state.zone_data = []

        # Assign new profile (support up to 2 crowd purposes)
        if isinstance(new_purpose, list):
            parsed_purposes = [str(p).strip().upper() for p in new_purpose if p]
        elif "," in str(new_purpose):
            parsed_purposes = [str(p).strip().upper() for p in str(new_purpose).split(",") if p.strip()]
        else:
            parsed_purposes = [str(new_purpose).strip().upper()]

        # Limit to maximum 2 crowd functionalities
        parsed_purposes = parsed_purposes[:2] if parsed_purposes else ["ENTRY_EXIT"]

        state.ai_purposes = parsed_purposes
        state.camera_type = "CROWD"
        state.is_frs = False
        state.crowd_ai_active = True

    # 3. Broadcast WebSocket event
    _emit_frs_event_threadsafe("camera_reassigned", {
        "camera_id": state.camera_id,
        "ai_purposes": state.ai_purposes,
        "new_purpose": ",".join(state.ai_purposes),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[FRS-Engine] Camera {camera_id} successfully reassigned to purposes: {state.ai_purposes}. Previous pipeline deleted and disconnected.")
    return {
        "status": "success",
        "camera_id": state.camera_id,
        "assigned_purpose": state.ai_purposes[0] if state.ai_purposes else "ENTRY_EXIT",
        "ai_purposes": state.ai_purposes,
        "in_count": state.in_count,
        "out_count": state.out_count,
    }


@router.patch("/cameras/{camera_id}/assign-zone")
async def api_assign_camera_zone(camera_id: str, zone_code: str):
    """
    Dynamically reassigns a camera to a specific zone (ZONE-A, ZONE-B, ZONE-C, ZONE-D),
    updates PostgreSQL cameras table, and updates active worker state.
    """
    valid_zones = {"ZONE-A", "ZONE-B", "ZONE-C", "ZONE-D", "ZONE-E", "ZONE-F", "ZONE-G", "ZONE-H", "ZONE-I", "ZONE-J", "ZONE-K", "ZONE-L"}
    zone_code = zone_code.upper().strip()
    norm_map = {"ZONE A": "ZONE-A", "ZONE B": "ZONE-B", "ZONE C": "ZONE-C", "ZONE D": "ZONE-D"}
    zone_code = norm_map.get(zone_code, zone_code)

    state = get_worker_for_camera(camera_id)
    if state:
        state.zone_code = zone_code

    clean_id = camera_id.replace("-FRS", "").replace("-CROWD", "")

    # Persist in PostgreSQL cameras table
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.camera import Camera
        from sqlalchemy import select

        async with AsyncSessionLocal() as pg_db:
            stmt = select(Camera).where(Camera.camera_code.in_([camera_id, clean_id]))
            res = await pg_db.execute(stmt)
            cams = res.scalars().all()
            for cam in cams:
                cam.zone_code = zone_code
            await pg_db.commit()
    except Exception as e:
        logger.warning(f"[FRS-Engine] DB error updating camera zone for {camera_id}: {e}")

    _emit_frs_event_threadsafe("camera_zone_changed", {
        "camera_id": camera_id,
        "zone_code": zone_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[FRS-Engine] Camera {camera_id} assigned to zone: {zone_code}")
    return {
        "status": "success",
        "camera_id": camera_id,
        "zone_code": zone_code,
    }


@router.get("/cameras/{camera_id}/raw-stream")

async def stream_camera_raw(camera_id: str):
    """Clean MJPEG stream without any FRS annotations, YOLO boxes, or counting lines."""
    state = get_worker_for_camera(camera_id)
    if state is None or not state.running:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} is not actively streaming")

    async def generate_clean():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        placeholder_timer = 0.0
        while state.running:
            with state.frame_lock:
                frame = getattr(state, "latest_clean_frame", None) or state.latest_frame

            if frame:
                yield boundary + frame + b"\r\n"
                await asyncio.sleep(0.033)
            else:
                now = time.monotonic()
                if now - placeholder_timer >= 1.0:
                    placeholder_timer = now
                    status_text = "Connecting to camera feed..." if state.status != "error" else "RTSP stream offline / reconnecting..."
                    import re
                    safe_url = re.sub(r"://(.*)@", "://***:***@", state.rtsp_url) if "@" in state.rtsp_url else state.rtsp_url
                    ph_frame = _generate_placeholder_jpeg(state.camera_id, status_text, safe_url)
                    if ph_frame:
                        yield boundary + ph_frame + b"\r\n"
                await asyncio.sleep(0.1)

    return StreamingResponse(
        generate_clean(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/stream")
async def stream_default_camera():
    """Default camera live MJPEG stream (first active worker)."""
    with _workers_lock:
        state = next(iter(_camera_workers.values())) if _camera_workers else None
    if state is None:
        raise HTTPException(status_code=404, detail="No active camera stream available")
    return await stream_camera(state.camera_id)


@router.patch("/cameras/{camera_id}/toggle-frs")
async def toggle_frs_camera_worker(camera_id: str, enabled: Optional[bool] = None):
    """Direct toggle of FRS AI detection on this worker."""
    with _workers_lock:
        state = _camera_workers.get(camera_id)
        if not state:
            for k, s in _camera_workers.items():
                if k.lower() == camera_id.lower() or camera_id.lower() in k.lower():
                    state = s
                    break
        if not state:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

        new_val = enabled if enabled is not None else not state.is_frs
        state.is_frs = new_val
        state.camera_type = "FRS" if new_val else "CROWD"
        logger.info(f"[FRS-Engine] Camera {camera_id} FRS toggled to: {new_val}")
        return {
            "camera_id": state.camera_id,
            "is_frs": state.is_frs,
            "camera_type": state.camera_type,
            "status": state.status,
        }


# ── POST /enroll (UI Watchlist Person Enrollment) ────────────────────────────

from fastapi import UploadFile, File, Form
import shutil

@router.post("/enroll")
async def enroll_person_api(
    name: str = Form(...),
    category: str = Form("Authorized Watchlist"),
    photo: UploadFile = File(...),
):
    """
    Enroll a new watchlist person directly via UI upload.
    Extracts 512-D InsightFace embedding, saves image to backend/data/enrollment,
    persists in SQLite & PostgreSQL frs_reference_profiles, and updates active gallery.
    """
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    enroll_dir = str(_DATA_ENROLLMENT_DIR)
    os.makedirs(enroll_dir, exist_ok=True)

    # Save uploaded file
    ext = os.path.splitext(photo.filename)[1].lower() or ".jpg"
    filename = f"{name_clean.lower()}_{str(uuid.uuid4())[:6]}{ext}"
    dest_path = os.path.join(enroll_dir, filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(photo.file, f)

    # Detect face & generate embedding
    (FaceModel, IdentityMatcher, FaceQualityAssessor,
     FaceTracker, RTSPReader, db) = _load_frs_components()

    from app.frs_engine.input.image_input import load_image
    rgb = load_image(dest_path)
    if rgb is None:
        os.remove(dest_path)
        raise HTTPException(status_code=400, detail="Could not read uploaded image")

    face_model, _ = get_shared_engine()
    with _shared_engine_lock:
        faces = face_model.detect_faces(rgb)
    if not faces:
        os.remove(dest_path)
        raise HTTPException(status_code=400, detail="No face detected in the photo. Please use a clear frontal photo.")

    face = faces[0]
    emb = face.embedding

    # Crop clean face portrait with 25% padding for database reference
    h_img, w_img = rgb.shape[:2]
    fx1, fy1, fx2, fy2 = [int(v) for v in face.bbox]
    fw, fh = fx2 - fx1, fy2 - fy1
    pad_x = int(fw * 0.25)
    pad_y = int(fh * 0.25)
    cx1 = max(0, fx1 - pad_x)
    cy1 = max(0, fy1 - pad_y)
    cx2 = min(w_img, fx2 + pad_x)
    cy2 = min(h_img, fy2 + pad_y)
    portrait_rgb = rgb[cy1:cy2, cx1:cx2]
    portrait_bgr = cv2.cvtColor(portrait_rgb, cv2.COLOR_RGB2BGR)
    cv2.imwrite(dest_path, portrait_bgr)

    # 1. SQLite R&D DB
    existing_p = db.get_person_by_name(name_clean)
    if existing_p:
        pid = existing_p["id"]
    else:
        pid = db.insert_person(name_clean)
    db.insert_embedding(pid, emb, dest_path)

    # 2. PostgreSQL frs_reference_profiles table
    rel_url = f"/static/enrollment/{filename}"
    ref_id = f"WL-{name_clean.upper()}-001"
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.frs import FRSReferenceProfile
        from sqlalchemy import select
        async with AsyncSessionLocal() as pg_db:
            res = await pg_db.execute(select(FRSReferenceProfile).where(FRSReferenceProfile.display_name == name_clean))
            prof = res.scalars().first()
            if not prof:
                prof = FRSReferenceProfile(
                    reference_id=ref_id,
                    reference_code=ref_id,
                    display_name=name_clean,
                    category=category,
                    status="ACTIVE",
                    active=True,
                    reference_image_path=rel_url,
                    embedding_vector=emb.tolist(),
                    embedding_model="buffalo_l",
                    embedding_version="1.0.0",
                    created_by="Command Officer",
                    last_updated_date=datetime.now().strftime("%d %b %Y"),
                )
                pg_db.add(prof)
            else:
                prof.reference_image_path = rel_url
                prof.embedding_vector = emb.tolist()
                prof.category = category
                prof.active = True
            await pg_db.commit()
    except Exception as e:
        logger.warning(f"[FRS-Enroll] PostgreSQL sync warning: {e}")

    # Reload in-memory matcher gallery immediately
    reload_shared_gallery()

    logger.info(f"[FRS-Engine] Successfully enrolled {name_clean} (det_score={face.det_score:.2f})")
    return {
        "success": True,
        "message": f"Successfully enrolled {name_clean}",
        "reference_id": ref_id,
        "display_name": name_clean,
        "category": category,
        "reference_image": rel_url,
        "det_score": round(float(face.det_score), 3),
    }


# ── POST /enroll-from-camera (1-Click Live Camera Snapshot Enrollment) ────────

class CameraEnrollRequest(BaseModel):
    name: str
    camera_id: Optional[str] = "CAM-KHB-001"
    category: Optional[str] = "Authorized Watchlist"


@router.post("/enroll-from-camera")
async def enroll_from_camera_api(req: CameraEnrollRequest):
    """
    1-Click Live Camera Snapshot Enrollment:
    Captures current frame from camera, runs InsightFace detection,
    extracts the embedding of the detected face, saves snapshot to backend/data/enrollment/,
    persists in SQLite & PostgreSQL, and reloads matcher gallery in-memory!
    """
    name_clean = req.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    target_cam_id = req.camera_id or "CAM-KHB-001"
    worker_to_use = None
    with _workers_lock:
        worker_to_use = _camera_workers.get(target_cam_id)
        if not worker_to_use:
            for k, s in _camera_workers.items():
                if k.lower() == target_cam_id.lower() or target_cam_id.lower() in k.lower():
                    worker_to_use = s
                    break
            if not worker_to_use and _camera_workers:
                worker_to_use = next(iter(_camera_workers.values()))

    if not worker_to_use:
        raise HTTPException(status_code=404, detail="No active camera worker found for snapshot")

    # Get latest raw RGB frame
    rgb = None
    with worker_to_use.frame_lock:
        if worker_to_use.latest_rgb is not None:
            rgb = worker_to_use.latest_rgb.copy()
        elif worker_to_use.latest_frame is not None:
            buf = np.frombuffer(worker_to_use.latest_frame, dtype=np.uint8)
            bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if bgr is not None:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    if rgb is None:
        raise HTTPException(status_code=400, detail="No camera frame available yet. Please wait 2 seconds.")

    (FaceModel, IdentityMatcher, _, _, _, db) = _load_frs_components()
    face_model, matcher = get_shared_engine()
    if face_model is None:
        raise HTTPException(status_code=500, detail="Face recognition model not loaded")

    with _shared_engine_lock:
        faces = face_model.detect_faces(rgb)
    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in live camera frame. Please look directly into the camera.")

    # Filter out extreme poses and small distant noise, then pick the best frontal face
    valid_faces = []
    for f in faces:
        if getattr(f, "pose", None) is not None:
            try:
                pitch, yaw, roll = f.pose
                if abs(yaw) > 35.0 or abs(pitch) > 30.0:
                    continue
            except Exception:
                pass
        w_f = f.bbox[2] - f.bbox[0]
        h_f = f.bbox[3] - f.bbox[1]
        if w_f >= 30 and h_f >= 30:
            valid_faces.append(f)

    if not valid_faces:
        raise HTTPException(
            status_code=400,
            detail="No clear frontal face detected. Please face the camera directly with good lighting."
        )

    # Pick largest frontal face
    best_face = max(valid_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    emb = best_face.embedding

    # Save cropped face portrait (square portrait with 25% margin)
    enroll_dir = str(_DATA_ENROLLMENT_DIR)
    os.makedirs(enroll_dir, exist_ok=True)
    filename = f"{name_clean.lower()}_{str(uuid.uuid4())[:6]}.jpg"
    dest_path = os.path.join(enroll_dir, filename)

    h_img, w_img = rgb.shape[:2]
    fx1, fy1, fx2, fy2 = [int(v) for v in best_face.bbox]
    fw, fh = fx2 - fx1, fy2 - fy1
    pad_x = int(fw * 0.25)
    pad_y = int(fh * 0.25)
    cx1 = max(0, fx1 - pad_x)
    cy1 = max(0, fy1 - pad_y)
    cx2 = min(w_img, fx2 + pad_x)
    cy2 = min(h_img, fy2 + pad_y)
    portrait_rgb = rgb[cy1:cy2, cx1:cx2]
    portrait_bgr = cv2.cvtColor(portrait_rgb, cv2.COLOR_RGB2BGR)
    cv2.imwrite(dest_path, portrait_bgr)

    # 1. SQLite R&D DB
    existing_p = db.get_person_by_name(name_clean)
    if existing_p:
        pid = existing_p["id"]
    else:
        pid = db.insert_person(name_clean)
    db.insert_embedding(pid, emb, dest_path)

    # 2. PostgreSQL frs_reference_profiles table
    rel_url = f"/static/enrollment/{filename}"
    ref_id = f"WL-{name_clean.upper()}-001"
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.frs import FRSReferenceProfile
        from sqlalchemy import select
        async with AsyncSessionLocal() as pg_db:
            res = await pg_db.execute(select(FRSReferenceProfile).where(FRSReferenceProfile.display_name == name_clean))
            prof = res.scalars().first()
            if not prof:
                prof = FRSReferenceProfile(
                    reference_id=ref_id,
                    reference_code=ref_id,
                    display_name=name_clean,
                    category=req.category,
                    status="ACTIVE",
                    active=True,
                    reference_image_path=rel_url,
                    embedding_vector=emb.tolist(),
                    embedding_model="buffalo_l",
                    embedding_version="1.0.0",
                    created_by="Live Camera Enrollment",
                    last_updated_date=datetime.now().strftime("%d %b %Y"),
                )
                pg_db.add(prof)
            else:
                prof.reference_image_path = rel_url
                prof.embedding_vector = emb.tolist()
                prof.category = req.category
                prof.active = True
            await pg_db.commit()
    except Exception as e:
        logger.warning(f"[FRS-Enroll] PostgreSQL sync warning: {e}")

    # Reload shared gallery in memory so recognition starts IMMEDIATELY
    reload_shared_gallery()

    logger.info(f"[FRS-Engine] 1-Click camera enrollment success: {name_clean} (det_score={best_face.det_score:.2f})")
    return {
        "success": True,
        "message": f"Successfully enrolled {name_clean} directly from live camera!",
        "reference_id": ref_id,
        "display_name": name_clean,
        "category": req.category,
        "reference_image": rel_url,
        "det_score": round(float(best_face.det_score), 3),
    }


# ── GET /gallery ──────────────────────────────────────────────────────────────

@router.get("/gallery")
async def list_gallery():
    """List all enrolled persons in the FRS watchlist gallery."""
    try:
        from app.frs_engine.database import repository as db
        people = db.list_people()
        return {"persons": people, "total": len(people)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gallery load failed: {e}")



# ── WebSocket /ws/v1/frs-stream ──────────────────────────────────────────────

@router.websocket("/ws/frs-stream")
async def frs_stream_websocket(websocket: WebSocket):
    """
    Alternative dedicated WebSocket for FRS-only events.
    The main events bus /ws/v1/events also carries frs_candidate events.
    """
    await websocket.accept()
    mgr = _get_ws_manager()
    if mgr:
        mgr.active_connections.add(websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "payload": {"message": "FRS Stream connected", "timestamp": datetime.now(timezone.utc).isoformat()},
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        if mgr:
            mgr.disconnect(websocket)
    except Exception as e:
        logger.warning(f"[FRS-WS] error: {e}")
        if mgr:
            mgr.disconnect(websocket)


# ── Startup: auto-register the main camera ───────────────────────────────────

def auto_start_main_camera():
    """No-op: Cameras are now onboarded and started dynamically via the UI/API."""
    pass
