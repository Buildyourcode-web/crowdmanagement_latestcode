"""
pipeline.py — Integrated FRS Pipeline Coordinator.

Orchestrates:
1. RTSP Stream Ingestion / Frame decoding
2. Face Detection & Landmark Extraction
3. Face Quality Gate Validation
4. 512-D Embedding Generation
5. Active Reference Profile Matching & Cosine Similarity
6. Candidate Event Generation & Human Review Queue Routing
7. Health Monitoring & Frame Timeout Detection

Strict Operational Rule:
All matches enter REVIEW_REQUIRED for authorized human review.
Never automatically confirms identity. Never triggers enforcement.
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import cv2
import numpy as np
from loguru import logger

from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.frs.config import FRSPipelineConfig
from app.ai.pipelines.frs.detector import DetectedFace, FaceDetector
from app.ai.pipelines.frs.embedding import FaceEmbeddingEngine
from app.ai.pipelines.frs.events import FRSEventEngine, FRSEventPayload
from app.ai.pipelines.frs.health import FRSPipelineHealthTracker
from app.ai.pipelines.frs.matcher import CandidateMatch, CandidateMatcher
from app.ai.pipelines.frs.quality import FaceQualityGate, FaceQualityResult


class FRSPipeline:
    """Asynchronous pipeline coordinator for a single FRS camera deployment."""

    def __init__(
        self,
        config: FRSPipelineConfig,
        custom_detector: Optional[Callable[[np.ndarray], List[DetectedFace]]] = None,
        custom_embedder: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ):
        self.config = config
        self.camera_code = config.camera_code
        self.camera_id = config.camera_id

        # Subsystems
        self.detector = FaceDetector(
            confidence_threshold=config.detection_confidence_threshold,
            custom_detector=custom_detector,
        )
        self.quality_gate = FaceQualityGate(
            min_width=config.min_face_width,
            min_height=config.min_face_height,
            min_sharpness=config.min_sharpness_score,
            min_brightness=config.min_brightness,
            max_brightness=config.max_brightness,
            max_yaw=config.max_pose_yaw_deg,
            max_pitch=config.max_pose_pitch_deg,
        )
        self.embedder = FaceEmbeddingEngine(
            embedding_dim=512,
            custom_embedder=custom_embedder,
        )
        self.matcher = CandidateMatcher(
            match_threshold=config.match_threshold,
            top_k=config.top_k,
        )
        self.event_engine = FRSEventEngine(
            suppression_cooldown_seconds=config.duplicate_suppression_seconds
        )
        self.health_tracker = FRSPipelineHealthTracker(camera_code=self.camera_code)

        # Lifecycle state
        self.state: PipelineState = PipelineState.CREATED
        self.running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._last_candidate_at: Optional[datetime] = None
        self.save_candidate_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    async def start(self) -> bool:
        """Starts the FRS processing pipeline."""
        if self.running:
            logger.warning(f"FRSPipeline[{self.camera_code}] already running.")
            return True

        self.running = True
        self.state = PipelineState.RUNNING
        self._loop_task = asyncio.create_task(self._pipeline_loop())
        logger.info(f"FRSPipeline[{self.camera_code}] started successfully on {self.config.sanitized_rtsp_url}.")
        return True

    async def stop(self) -> bool:
        """Gracefully terminates the FRS pipeline."""
        self.running = False
        self.state = PipelineState.STOPPED
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info(f"FRSPipeline[{self.camera_code}] stopped.")
        return True

    async def _pipeline_loop(self):
        """Internal asynchronous loop simulating frame processing / RTSP feed."""
        interval = 1.0 / max(1, self.config.fps)
        while self.running:
            try:
                # Update health tracker
                self.health_tracker.evaluate_status()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"FRSPipeline[{self.camera_code}] loop exception: {e}")
                self.health_tracker.record_error(str(e))
                await asyncio.sleep(1.0)

    def process_frame(
        self,
        frame: np.ndarray,
        save_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Synchronous / directly invokable frame analysis.
        Executes face detection -> quality gate -> embedding -> matching -> candidate events.
        """
        if frame is None or frame.size == 0:
            return []

        t0 = time.perf_counter()

        # 1. Detection
        det_start = time.perf_counter()
        faces = self.detector.detect(frame)
        det_ms = (time.perf_counter() - det_start) * 1000

        emb_ms_total = 0.0
        match_ms_total = 0.0
        candidates_found: List[Dict[str, Any]] = []

        h, w = frame.shape[:2]

        for face in faces:
            x1, y1, x2, y2 = face.bbox
            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(x1 + 1, min(x2, w))
            y2 = max(y1 + 1, min(y2, h))

            crop = frame[y1:y2, x1:x2]

            # 2. Quality Gate
            quality_res: FaceQualityResult = self.quality_gate.assess_quality(crop, face)
            if not quality_res.passed:
                logger.debug(
                    f"FRSPipeline[{self.camera_code}] face rejected by quality gate: {quality_res.rejection_reason}"
                )
                continue

            # 3. Embedding
            emb_start = time.perf_counter()
            embedding = self.embedder.compute_embedding(crop)
            emb_ms_total += (time.perf_counter() - emb_start) * 1000

            if embedding is None:
                continue

            # 4. Matching against Gallery
            match_start = time.perf_counter()
            matches: List[CandidateMatch] = self.matcher.search(embedding)
            match_ms_total += (time.perf_counter() - match_start) * 1000

            if not matches:
                continue

            # Top match
            top_match = matches[0]

            # 5. Temporal Duplicate Suppression
            if self.event_engine.is_suppressed(self.camera_code, top_match.reference_id):
                logger.debug(
                    f"FRSPipeline[{self.camera_code}] match {top_match.reference_id} suppressed by cooldown."
                )
                continue

            # Record suppression
            self.event_engine.record_match(self.camera_code, top_match.reference_id)
            self._last_candidate_at = datetime.now(timezone.utc)

            # 6. Candidate metadata (strictly REVIEW_REQUIRED)
            candidate_code = f"FRS-EVT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            detected_crop_rel = f"/media/frs/detected/{candidate_code}.jpg"

            # Persist detected face crop to disk for human review UI
            try:
                media_dir = Path("media/frs/detected")
                media_dir.mkdir(parents=True, exist_ok=True)
                crop_path = media_dir / f"{candidate_code}.jpg"
                crop_to_write = crop
                if crop.ndim == 3 and crop.shape[2] == 3:
                    crop_to_write = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
                cv2.imwrite(str(crop_path), crop_to_write)
            except Exception as save_err:
                logger.warning(f"FRSPipeline[{self.camera_code}] Failed to save face crop: {save_err}")

            candidate_record = {
                "candidate_code": candidate_code,
                "camera_id": self.camera_id,
                "camera_code": self.camera_code,
                "camera_name": self.config.camera_name,
                "zone_id": self.config.zone_id,
                "zone_code": self.config.zone_code or "ZONE-A",
                "location": self.config.location_name,
                "reference_profile_id": top_match.reference_id,
                "reference_name": top_match.display_name,
                "detected_image_path": detected_crop_rel,
                "match_score": top_match.similarity_score,
                "detection_confidence": face.confidence,
                "quality_score": quality_res.quality_score,
                "status": "REVIEW_REQUIRED",
                "review_required": True,
                "priority": "HIGH" if top_match.similarity_score >= 85.0 else "NORMAL",
                "image_quality": f"Quality ({int(quality_res.quality_score * 100)}%)",
                "model_version": self.config.detector_model.version,
                "embedding_model_version": top_match.model_version,
                "detected_at": datetime.now(timezone.utc),
                "margin": top_match.margin,
            }

            candidates_found.append(candidate_record)

            # Dispatch Event
            event_payload = self.event_engine.build_candidate_event(
                camera_id=self.camera_id,
                camera_code=self.camera_code,
                zone_id=self.config.zone_id,
                zone_code=self.config.zone_code,
                location=self.config.location_name,
                candidate_code=candidate_code,
                reference_id=top_match.reference_id,
                reference_name=top_match.display_name,
                similarity_score=top_match.similarity_score,
                review_status="REVIEW_REQUIRED",
            )

            # Async emit
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.event_engine.emit_event(event_payload))
            except Exception:
                pass

            # Persistence callback if provided
            cb = save_callback or self.save_candidate_callback
            if cb:
                try:
                    cb(candidate_record)
                except Exception as ex:
                    logger.error(f"FRSPipeline[{self.camera_code}] callback error: {ex}")

        # Record health metrics
        total_time = time.perf_counter() - t0
        proc_fps = 1.0 / max(0.001, total_time)
        self.health_tracker.record_frame(
            det_ms=det_ms,
            emb_ms=emb_ms_total,
            match_ms=match_ms_total,
            processing_fps=proc_fps,
        )

        return candidates_found

    def get_health(self) -> Dict[str, Any]:
        """Returns the health status dict matching orchestrator expectations."""
        return self.health_tracker.get_health()

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive operational status."""
        health = self.get_health()
        return {
            "camera_code": self.camera_code,
            "pipeline_type": "FRS",
            "state": self.state.value if isinstance(self.state, PipelineState) else str(self.state),
            "running": self.running,
            "fps": health.get("fps", 0.0),
            "health_status": health.get("status", "HEALTHY"),
            "gallery_size": self.matcher.gallery_size,
            "match_threshold": self.config.match_threshold,
            "last_candidate_at": self._last_candidate_at.isoformat() if self._last_candidate_at else None,
            "last_error": health.get("last_error"),
        }
