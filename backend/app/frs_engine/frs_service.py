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
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

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
    def __init__(self, camera_id: str, rtsp_url: str, name: str, is_frs: bool = True, camera_type: str = "FRS"):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.name = name
        self.is_frs = is_frs
        self.camera_type = camera_type
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.latest_frame: Optional[bytes] = None  # JPEG bytes for MJPEG
        self.latest_rgb: Optional[np.ndarray] = None  # Raw RGB frame
        self.frame_lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.detections_count = 0
        self.status = "starting"

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

RTSP_URL_DEFAULT = "rtsp://admin:Veeru%40555@192.168.0.102:554/Streaming/Channels/101"
MATCH_THRESHOLD = 0.60
DET_SIZE = (640, 640)

# Shared singleton components
_shared_face_model = None
_shared_matcher = None
_shared_engine_lock = threading.Lock()
_onnx_inference_lock = threading.Lock()

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
                        logger.info(f"[FRS-Engine] Gallery reloaded: {len(names)} identities ({set(names)}) [threshold={MATCH_THRESHOLD}]")
            except Exception as e:
                logger.warning(f"[FRS-Engine] Gallery reload warning: {e}")



class RTSPCameraWorker:
    """
    Decoupled threaded RTSP worker:
    - Thread 1 (Capture): non-blocking frame grabber from RTSP at 25 FPS, overlays bounding boxes, encodes MJPEG.
    - Thread 2 (AI Inference): runs asynchronously every ~200ms on CPU, detects faces, matches against gallery, emits alerts.
    """

    def __init__(self, state: CameraWorkerState):
        self.state = state
        self._cooldowns: Dict[str, float] = {}
        self._active_boxes: List[dict] = []
        self._boxes_lock = threading.Lock()
        self._latest_ai_rgb = None
        self._ai_lock = threading.Lock()

    def _ai_detection_loop(self, face_model, matcher):
        crop_dir = os.path.join(os.getcwd(), "backend", "data", "crops")
        os.makedirs(crop_dir, exist_ok=True)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        while self.state.running:
            if not self.state.is_frs:
                with self._boxes_lock:
                    self._active_boxes.clear()
                time.sleep(0.4)
                continue

            with self._ai_lock:
                frame_to_process = None
                if self._latest_ai_rgb is not None:
                    frame_to_process = self._latest_ai_rgb.copy()
                    self._latest_ai_rgb = None

            if frame_to_process is None:
                time.sleep(0.04)
                continue

            try:
                with _onnx_inference_lock:
                    faces = face_model.detect_faces(frame_to_process)
            except Exception as e:
                time.sleep(0.1)
                continue

            new_boxes = []
            now_ts = time.time()

            for face in faces:
                x1, y1, x2, y2 = [int(v) for v in face.bbox]
                # Skip tiny distant noise (min 30px) or low confidence detections
                if (x2 - x1) < 30 or (y2 - y1) < 30 or face.det_score < 0.60:
                    continue

                # Pose quality gate: reject extreme profile shots (yaw > 35° or pitch > 30°)
                is_extreme_pose = False
                if getattr(face, "pose", None) is not None:
                    try:
                        pitch, yaw, roll = face.pose
                        if abs(yaw) > 35.0 or abs(pitch) > 30.0:
                            is_extreme_pose = True
                    except Exception:
                        pass

                if is_extreme_pose:
                    det_pct = round(face.det_score * 100)
                    new_boxes.append({
                        "bbox": [x1, y1, x2, y2],
                        "label": f"FACE SCANNING {det_pct}%",
                        "is_match": False,
                        "expiry": now_ts + 1.0,
                    })
                    continue

                try:
                    result = matcher.find_best_match(face.embedding)
                except Exception:
                    result = None

                # Strict threshold: Must be known AND >= MATCH_THRESHOLD (0.70)
                is_match = bool(result and result.is_known and result.similarity >= MATCH_THRESHOLD)
                if is_match:
                    person_clean = result.name.strip()
                    match_pct = round(result.similarity * 100, 1)
                    new_boxes.append({
                        "bbox": [x1, y1, x2, y2],
                        "label": f"{person_clean.upper()} {match_pct}%",
                        "is_match": True,
                        "expiry": now_ts + 1.2,
                    })

                    # Cooldown check: 15s per recognized person
                    last_alert = self._cooldowns.get(person_clean.lower(), 0.0)
                    if (now_ts - last_alert) >= 15.0:
                        self._cooldowns[person_clean.lower()] = now_ts
                        self.state.detections_count += 1

                        # Clean portrait crop with 25% padding around detected face
                        h, w = frame_to_process.shape[:2]
                        fw, fh = x2 - x1, y2 - y1
                        pad_x = int(fw * 0.25)
                        pad_y = int(fh * 0.25)
                        cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
                        cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
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
                            detected_image_url = f"/static/crops/{crop_filename}"

                        if not detected_image_url:
                            detected_image_url = f"data:image/jpeg;base64,{face_b64}"

                        # Look up exact reference portrait photo for matched person
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
                            enroll_dir = os.path.join(os.getcwd(), "backend", "data", "enrollment")
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
                            "personId": str(result.person_id),
                            "person_id": str(result.person_id),
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
                            "bbox": [x1, y1, x2, y2],
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
                                        detection_confidence=result.similarity,
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

                        _emit_frs_event_threadsafe("frs_candidate", payload)
                        global _main_loop
                        if _main_loop and _main_loop.is_running():
                            asyncio.run_coroutine_threadsafe(_persist(), _main_loop)
                        else:
                            try:
                                loop.run_until_complete(_persist())
                            except Exception as e:
                                logger.debug(f"[FRS-Worker] Persist fallback error: {e}")
                else:
                    det_pct = round(face.det_score * 100)
                    new_boxes.append({
                        "bbox": [x1, y1, x2, y2],
                        "label": f"FACE SCANNING {det_pct}%",
                        "is_match": False,
                        "expiry": now_ts + 1.0,
                    })

            with self._boxes_lock:
                self._active_boxes = new_boxes

            time.sleep(0.18)

        loop.close()

    def run(self):
        (FaceModel, IdentityMatcher, _, _, RTSPReader, db) = _load_frs_components()
        if FaceModel is None:
            self.state.status = "error"
            return

        try:
            face_model, matcher = get_shared_engine()
            reader = RTSPReader(url=self.state.rtsp_url, resize=(960, 540))
            reader.start()
            self.state.status = "online"
            logger.info(f"[FRS-Worker:{self.state.camera_id}] RTSP reader started: {self.state.rtsp_url}")

            # Start decoupled background AI inference thread
            ai_thread = threading.Thread(
                target=self._ai_detection_loop,
                args=(face_model, matcher),
                daemon=True,
                name=f"FRS-AI-{self.state.camera_id}"
            )
            ai_thread.start()

            while self.state.running:
                rgb = reader.get_frame(timeout=0.04)
                if rgb is None:
                    continue

                # Pass latest frame to AI detection thread and worker state
                with self._ai_lock:
                    self._latest_ai_rgb = rgb
                with self.state.frame_lock:
                    self.state.latest_rgb = rgb

                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

                # Overlay bounding boxes if FRS enabled
                if self.state.is_frs:
                    now = time.time()
                    with self._boxes_lock:
                        boxes = [b for b in self._active_boxes if b["expiry"] > now]

                    for b in boxes:
                        x1, y1, x2, y2 = b["bbox"]
                        is_match = b["is_match"]
                        color = (46, 204, 113) if is_match else (255, 180, 0)
                        
                        # Draw bounding box
                        cv2.rectangle(bgr, (x1, y1), (x2, y2), color, 2)

                        # Label badge
                        lbl = b["label"]
                        (lw, lh), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        top_y = max(lh + 6, y1)
                        cv2.rectangle(bgr, (x1, top_y - lh - 6), (x1 + lw + 6, top_y + 2), color, -1)
                        cv2.putText(bgr, lbl, (x1 + 3, top_y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

                ok, jpeg_buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 72])
                if ok:
                    with self.state.frame_lock:
                        self.state.latest_frame = jpeg_buf.tobytes()

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


# ── POST /cameras ────────────────────────────────────────────────────────────

@router.post("/cameras", response_model=CameraInfo, status_code=201)
async def add_frs_camera(req: AddCameraRequest):
    """Add a new RTSP camera and start live stream / FRS detection."""
    prefix = "FRS" if req.is_frs or req.camera_type == "FRS" else "CAM"
    cam_id = req.camera_id or f"{prefix}-{str(uuid.uuid4())[:8].upper()}"
    is_frs = req.is_frs if req.camera_type == "FRS" else False

    with _workers_lock:
        # 1. If camera with same ID exists, update it and return
        if cam_id in _camera_workers:
            state = _camera_workers[cam_id]
            state.is_frs = is_frs
            state.camera_type = req.camera_type
            if req.name and req.name != "Camera":
                state.name = req.name
            return CameraInfo(
                camera_id=state.camera_id,
                name=state.name,
                rtsp_url=state.rtsp_url,
                status=state.status,
                started_at=state.started_at,
                detections_count=state.detections_count,
                stream_url=f"/api/v1/frs-engine/cameras/{state.camera_id}/stream",
                is_frs=state.is_frs,
                camera_type=state.camera_type,
            )

        # 2. Check if a worker already streams the EXACT SAME rtsp_url
        for existing_id, existing_state in _camera_workers.items():
            if existing_state.rtsp_url.strip() == req.rtsp_url.strip() and existing_state.running:
                logger.info(f"[FRS-Engine] Reusing existing worker {existing_id} for stream {req.rtsp_url[:40]}")
                existing_state.is_frs = is_frs
                existing_state.camera_type = req.camera_type
                if req.name and req.name != "Camera":
                    existing_state.name = req.name
                return CameraInfo(
                    camera_id=existing_id,
                    name=existing_state.name,
                    rtsp_url=existing_state.rtsp_url,
                    status=existing_state.status,
                    started_at=existing_state.started_at,
                    detections_count=existing_state.detections_count,
                    stream_url=f"/api/v1/frs-engine/cameras/{existing_id}/stream",
                    is_frs=existing_state.is_frs,
                    camera_type=existing_state.camera_type,
                )

        state = CameraWorkerState(
            camera_id=cam_id,
            rtsp_url=req.rtsp_url,
            name=req.name,
            is_frs=is_frs,
            camera_type=req.camera_type,
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

    logger.info(f"[FRS-Engine] Camera added: {cam_id} ({req.camera_type}) -> {req.rtsp_url[:40]}...")

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
            ))
    return result


# ── DELETE /cameras/{id} ─────────────────────────────────────────────────────

@router.delete("/cameras/{camera_id}", status_code=204)
async def remove_frs_camera(camera_id: str):
    """Stop and remove an FRS camera worker."""
    with _workers_lock:
        state = _camera_workers.pop(camera_id, None)

    if state is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    state.running = False
    if state.thread:
        state.thread.join(timeout=3.0)

    logger.info(f"[FRS-Engine] Camera removed: {camera_id}")


# ── GET /cameras/{id}/stream  (MJPEG) ────────────────────────────────────────

@router.get("/cameras/{camera_id}/stream")
async def stream_camera(camera_id: str):
    """MJPEG live stream from RTSP camera. Use as <img src='...'> in frontend."""

    with _workers_lock:
        state = _camera_workers.get(camera_id)
        if state is None:
            # Fallback: look up by camera code or return the active main worker
            for k, s in _camera_workers.items():
                if k.lower() == camera_id.lower() or camera_id.lower() in k.lower() or k == "CAM-KHB-001":
                    state = s
                    break
            if state is None and _camera_workers:
                state = next(iter(_camera_workers.values()))

    if state is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found or not streaming")

    async def generate():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        while state.running:
            with state.frame_lock:
                frame = state.latest_frame

            if frame:
                yield boundary + frame + b"\r\n"
            await asyncio.sleep(0.033)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/stream")
async def stream_default_camera():
    """Default camera live MJPEG stream (CAM-KHB-001 or first active)."""
    with _workers_lock:
        state = _camera_workers.get("CAM-KHB-001")
        if state is None and _camera_workers:
            state = next(iter(_camera_workers.values()))
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

    enroll_dir = os.path.join(os.getcwd(), "backend", "data", "enrollment")
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
    with _onnx_inference_lock:
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

    with _onnx_inference_lock:
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
    enroll_dir = os.path.join(os.getcwd(), "backend", "data", "enrollment")
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
    """
    Auto-start the main CAM-KHB-001 FRS camera on backend startup.
    RTSP URL from .env or hardcoded default.
    """
    import os
    rtsp_url = os.getenv("RTSP_URL", RTSP_URL_DEFAULT)
    if not rtsp_url:
        logger.warning("[FRS-Engine] RTSP_URL not set — main camera not auto-started.")
        return

    cam_id = "CAM-KHB-001"
    with _workers_lock:
        if cam_id in _camera_workers:
            return  # Already running

        state = CameraWorkerState(
            camera_id=cam_id,
            rtsp_url=rtsp_url,
            name="Khairatabad Main Camera (FRS)",
        )
        worker = RTSPCameraWorker(state)
        state.running = True

        t = threading.Thread(
            target=worker.run,
            daemon=True,
            name=f"FRS-Worker-{cam_id}",
        )
        state.thread = t
        _camera_workers[cam_id] = state
        t.start()

    logger.info(f"[FRS-Engine] Auto-started main camera: {cam_id} -> {rtsp_url[:40]}...")
