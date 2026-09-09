"""
pipeline.py — Central Crowd AI Inference Pipeline Coordinator.

Orchestrates the complete multi-camera crowd inference workflow:
RTSP Input -> Person Detection -> Multi-Object Tracking -> ROI/Line Analytics ->
Crowd Metrics -> Risk Engine -> AI Event Engine -> Redis/WebSocket Telemetry.

Runs in an isolated background asyncio task, decoupled from FastAPI request handlers.
"""

import asyncio
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from loguru import logger

from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.analytics import CrowdMetricsResult, CrowdSpatialAnalytics
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import (
    BasePersonDetector,
    DeepStreamPersonDetector,
    DetectedPerson,
    YOLO11xPersonDetector,
)
from app.ai.pipelines.crowd.events import CrowdEventEngine
from app.ai.pipelines.crowd.health import PipelineHealthMonitor, PipelineHealthStatus
from app.ai.pipelines.crowd.risk import CrowdRiskEngine
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson
from app.redis.event_bus import event_bus


class CrowdPipeline:
    """
    Independent inference pipeline instance for a single camera stream.
    Instantiated via camera_id + profile_id + configuration.
    """

    def __init__(
        self,
        config: CrowdPipelineConfig,
        detector: Optional[BasePersonDetector] = None,
    ):
        self.config = config
        self.camera_id = config.camera_id
        self.camera_code = config.camera_code
        self.profile_id = config.profile_id

        # Sub-components
        if detector:
            self.detector = detector
        elif "YOLO11X" in self.profile_id.upper() or "yolo11" in config.model.model_id.lower():
            self.detector = YOLO11xPersonDetector(
                model=config.model,
                confidence_threshold=config.confidence_threshold,
                camera_code=self.camera_code,
            )
        else:
            self.detector = DeepStreamPersonDetector(
                model=config.model,
                confidence_threshold=config.confidence_threshold,
            )
        self.tracker = PersonTracker(
            max_age_frames=30,
            min_hits=1,
            iou_threshold=0.25,
        )
        self.analytics = CrowdSpatialAnalytics(config)
        self.risk_engine = CrowdRiskEngine()
        self.event_engine = CrowdEventEngine(cooldown_seconds=config.event_cooldown_seconds)
        self.health_monitor = PipelineHealthMonitor(
            camera_id=self.camera_id,
            camera_code=self.camera_code,
            profile_id=self.profile_id,
            target_fps=config.processing_fps,
        )

        # Lifecycle & Runtime State
        self.state = PipelineState.CREATED
        self.health_monitor.pipeline_state = self.state
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_requested = False
        self._latest_metrics: Optional[Dict[str, Any]] = None
        self._last_ws_broadcast_time: float = 0.0

    async def start(self) -> bool:
        """
        Validates requirements and launches background pipeline execution loop.
        """
        # 1. Check ROI Readiness
        if len(self.config.crowd_roi_points) < 3:
            self.state = PipelineState.FAILED
            self.health_monitor.pipeline_state = self.state
            self.health_monitor.record_error("CROWD_ROI geometry not configured")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "ROI_NOT_CONFIGURED",
                    "message": "Crowd ROI polygon is not configured. Configure spatial boundaries before starting pipeline.",
                },
            )

        self.state = PipelineState.STARTING
        self.health_monitor.pipeline_state = self.state

        # 2. Initialize Detector
        init_ok = await self.detector.initialize()
        if not init_ok:
            self.state = PipelineState.FAILED
            self.health_monitor.pipeline_state = self.state
            status_desc = getattr(self.detector, "status", "RUNTIME_UNAVAILABLE")
            is_yolo = "yolo11" in self.config.model.model_id.lower() or "yolo11" in self.profile_id.lower()
            err_code = "YOLO11X_UNAVAILABLE" if is_yolo else "RUNTIME_UNAVAILABLE"
            err_msg = (
                f"YOLO11x detection runtime unavailable ({status_desc}). Ensure model weights/engine are configured."
                if is_yolo
                else "NVIDIA DeepStream runtime unavailable on this host."
            )
            self.health_monitor.record_error(err_msg)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": err_code,
                    "message": err_msg,
                    "detector_status": status_desc,
                },
            )

        # 3. Transition to RUNNING
        self.state = PipelineState.RUNNING
        self.health_monitor.pipeline_state = self.state
        self._stop_requested = False

        # Launch async streaming loop
        self._worker_task = asyncio.create_task(self._run_stream_loop())
        logger.info(
            f"[CrowdPipeline] Started Crowd AI pipeline for {self.camera_code} "
            f"({self.profile_id}) with model {self.config.model.name}"
        )
        return True

    async def stop(self) -> bool:
        """Stops the pipeline execution loop and releases resources."""
        self.state = PipelineState.STOPPING
        self.health_monitor.pipeline_state = self.state
        self._stop_requested = True

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        await self.detector.close()
        self.tracker.reset()

        self.state = PipelineState.STOPPED
        self.health_monitor.pipeline_state = self.state
        logger.info(f"[CrowdPipeline] Stopped pipeline for {self.camera_code}")
        return True

    async def process_frame(
        self,
        frame_data: Any,
        frame_id: int,
        timestamp: float,
    ) -> Dict[str, Any]:
        """
        Executes a single end-to-end frame processing cycle:
        Detect -> Track -> Analytics -> Risk -> Events -> Telemetry.
        """
        t0 = time.time()

        # Step 1: Detect Persons
        detections: List[DetectedPerson] = await self.detector.detect(frame_data, frame_id, timestamp)
        t_det = (time.time() - t0) * 1000.0

        # Step 2: Multi-Object Tracking
        t1 = time.time()
        tracks: List[TrackedPerson] = self.tracker.update(detections, timestamp)
        t_trk = (time.time() - t1) * 1000.0

        # Step 3: Spatial ROI & Line Analytics
        metrics: CrowdMetricsResult = self.analytics.process_tracks(tracks, timestamp)

        # Step 4: Health Evaluation
        health_report = self.health_monitor.compute_health()

        # Step 5: Deterministic Risk Engine
        risk_score, risk_level, factors = self.risk_engine.calculate_risk(
            metrics,
            stream_health=health_report.health_status,
        )

        # Step 6: AI Event Generation & Cooldown Suppression
        events = await self.event_engine.evaluate_and_emit(
            metrics,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=factors,
            stream_health=health_report.health_status,
        )

        # Record health metrics
        self.health_monitor.record_frame(
            timestamp=timestamp,
            detection_latency_ms=t_det,
            tracking_latency_ms=t_trk,
        )

        # Package Metrics
        result_payload = {
            "camera_id": self.camera_id,
            "camera_code": self.camera_code,
            "camera_name": self.config.camera_name,
            "zone_id": self.config.zone_id,
            "zone_code": self.config.zone_code,
            "profile_id": self.profile_id,
            "timestamp": timestamp,
            "timestamp_iso": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
            "status": self.state.value,
            "health": health_report.health_status,
            "count": metrics.current_count,
            "density": metrics.density,
            "density_type": metrics.density_type,
            "density_unit": metrics.density_unit,
            "density_level": metrics.density_level,
            "inflow": metrics.inflow_rate,
            "outflow": metrics.outflow_rate,
            "flow_delta": metrics.flow_delta,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": factors,
            "events_fired": [e.event_type for e in events],
            "fps": health_report.processed_fps,
            "latencies": {
                "detection_ms": round(t_det, 1),
                "tracking_ms": round(t_trk, 1),
                "total_ms": round((time.time() - t0) * 1000.0, 1),
            },
            "model_info": self.detector.get_model_info() if hasattr(self.detector, "get_model_info") else {
                "model_id": self.config.model.model_id,
                "name": self.config.model.name,
                "version": self.config.model.version,
            },
        }
        self._latest_metrics = result_payload

        # Step 7: Broadcast WebSocket Telemetry (Throttled to max 2/sec)
        now = time.time()
        if (now - self._last_ws_broadcast_time) >= 0.5:
            self._last_ws_broadcast_time = now
            try:
                await event_bus.publish(
                    channel="crowd",
                    event_type="CROWD_METRICS_UPDATED",
                    payload=result_payload,
                )
            except Exception as ex:
                logger.debug(f"[CrowdPipeline] Telemetry publish error: {ex}")

        return result_payload

    async def _run_stream_loop(self) -> None:
        """
        Background stream processing loop.
        Connects to RTSP and processes frames at the configured FPS.
        """
        interval = 1.0 / max(float(self.config.processing_fps), 1.0)
        frame_id = 0

        while not self._stop_requested:
            try:
                now = time.time()
                frame_id += 1
                # In real DeepStream, frames are delivered via appsink callback.
                # In standalone/mock mode, this processes periodic intervals.
                await self.process_frame(frame_data=None, frame_id=frame_id, timestamp=now)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.health_monitor.record_error(str(e))
                logger.warning(f"[CrowdPipeline] Frame loop error on {self.camera_code}: {e}")
                await asyncio.sleep(1.0)

    def get_metrics(self) -> Dict[str, Any]:
        """Returns latest calculated metrics or baseline status."""
        if self._latest_metrics:
            return self._latest_metrics
        return {
            "camera_id": self.camera_id,
            "camera_code": self.camera_code,
            "camera_name": self.config.camera_name,
            "zone_id": self.config.zone_id,
            "zone_code": self.config.zone_code,
            "profile_id": self.profile_id,
            "timestamp": time.time(),
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "status": self.state.value,
            "health": self.health_monitor.compute_health().health_status,
            "count": 0,
            "density": 0.0,
            "density_type": "RELATIVE_DENSITY",
            "density_unit": "RELATIVE_DENSITY",
            "density_level": "LOW",
            "inflow": None,
            "outflow": None,
            "flow_delta": None,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "risk_factors": [],
            "events_fired": [],
            "fps": 0.0,
            "model_info": self.detector.get_model_info() if hasattr(self.detector, "get_model_info") else {
                "model_id": self.config.model.model_id,
                "name": self.config.model.name,
                "version": self.config.model.version,
            },
        }

    def get_health(self) -> PipelineHealthStatus:
        """Returns detailed health status."""
        return self.health_monitor.compute_health()
