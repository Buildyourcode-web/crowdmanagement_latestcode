"""
pipeline.py — Queue AI Pipeline Central Coordinator.

Decouples RTSP frame ingestion, DeepStream person detection (Class 0 only),
multi-object tracking, spatial Queue ROI / line analytics, deterministic risk scoring,
event emission with cooldown, and health monitoring into an asynchronous loop.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from loguru import logger

from app.ai.pipelines.crowd.detector import (
    BasePersonDetector,
    DeepStreamPersonDetector,
    DetectedPerson,
    YOLO11xPersonDetector,
)
from app.ai.pipelines.crowd.health import PipelineHealthMonitor
from app.ai.pipelines.crowd.pipeline import PipelineState
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson
from app.ai.pipelines.queue.analytics import QueueMetricsResult, QueueSpatialAnalytics
from app.ai.pipelines.queue.config import QueuePipelineConfig
from app.ai.pipelines.queue.events import QueueEventEngine
from app.ai.pipelines.queue.risk import QueueRiskEngine


class QueuePipeline:
    """
    Real-time Queue AI video analytics pipeline for an individual camera stream.
    Runs an asynchronous execution loop isolated from other cameras.
    """

    def __init__(
        self,
        config: QueuePipelineConfig,
        detector: Optional[BasePersonDetector] = None,
        tracker: Optional[PersonTracker] = None,
    ):
        self.config = config
        self.state: PipelineState = PipelineState.CREATED
        self._stop_event = asyncio.Event()
        self._runner_task: Optional[asyncio.Task] = None

        # 1. Detector: Custom, YOLO11x, or DeepStream detector
        if detector:
            self.detector = detector
        elif "YOLO11X" in config.profile_id.upper() or "yolo11" in config.model.model_id.lower():
            self.detector = YOLO11xPersonDetector(
                model=config.model,
                confidence_threshold=config.confidence_threshold,
                camera_code=config.camera_code,
            )
        else:
            self.detector = DeepStreamPersonDetector(
                model=config.model,
                confidence_threshold=config.confidence_threshold,
            )

        # 2. Multi-Object Tracker (Transient IDs: TRK-xxxx)
        self.tracker = tracker or PersonTracker(
            max_age_frames=30,
            iou_threshold=config.model.iou_threshold,
            min_hits=2,
        )

        # 3. Spatial Analytics
        self.analytics = QueueSpatialAnalytics(config)

        # 4. Risk Engine
        self.risk_engine = QueueRiskEngine()

        # 5. Event Engine
        self.event_engine = QueueEventEngine(cooldown_seconds=config.event_cooldown_seconds)

        # 6. Health Monitor
        self.health_monitor = PipelineHealthMonitor(
            camera_id=config.camera_id,
            camera_code=config.camera_code,
            profile_id=config.profile_id,
            target_fps=config.processing_fps,
            no_frame_timeout_sec=10.0,
        )

        # Latest state
        self._latest_metrics: Optional[Dict[str, Any]] = None
        self._frame_count: int = 0

    async def start(self) -> None:
        """Starts the Queue AI pipeline."""
        if self.state in (PipelineState.RUNNING, PipelineState.STARTING):
            return

        self.state = PipelineState.STARTING
        logger.info(f"Starting Queue AI pipeline for camera '{self.config.camera_code}' (profile: {self.config.profile_id})")

        # Initialize detector
        try:
            if asyncio.iscoroutinefunction(self.detector.initialize):
                init_ok = await self.detector.initialize()
            else:
                res = self.detector.initialize()
                init_ok = await res if asyncio.iscoroutine(res) else res

            if init_ok is False:
                status_desc = getattr(self.detector, "status", "RUNTIME_UNAVAILABLE")
                is_yolo = "yolo11" in self.config.model.model_id.lower() or "yolo11" in self.config.profile_id.lower()
                err_code = "YOLO11X_UNAVAILABLE" if is_yolo else "RUNTIME_UNAVAILABLE"
                err_msg = (
                    f"Queue YOLO11x runtime unavailable ({status_desc}). Ensure model weights or GPU acceleration are configured."
                    if is_yolo
                    else "NVIDIA DeepStream runtime unavailable on this host."
                )
                self.state = PipelineState.FAILED
                self.health_monitor.pipeline_state = PipelineState.FAILED
                self.health_monitor.record_error(err_msg)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": err_code, "message": err_msg, "detector_status": status_desc},
                )
        except HTTPException:
            raise
        except Exception as e:
            self.state = PipelineState.FAILED
            self.health_monitor.record_error(f"Detector init failed: {e}")
            raise

        self._stop_event.clear()
        self.state = PipelineState.RUNNING
        self.health_monitor.pipeline_state = PipelineState.RUNNING
        logger.info(f"Queue AI pipeline running for '{self.config.camera_code}'")

    async def stop(self) -> None:
        """Gracefully terminates the Queue AI pipeline and releases resources."""
        if self.state in (PipelineState.STOPPED, PipelineState.STOPPING):
            return

        self.state = PipelineState.STOPPING
        self._stop_event.set()

        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass

        try:
            self.detector.close()
        except Exception as e:
            logger.warning(f"Error closing detector for '{self.config.camera_code}': {e}")

        self.state = PipelineState.STOPPED
        self.health_monitor.pipeline_state = PipelineState.STOPPED
        logger.info(f"Queue AI pipeline stopped for '{self.config.camera_code}'")

    async def process_frame(
        self,
        frame: Any,
        frame_id: int,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes the detection -> tracking -> spatial analytics -> risk -> event pipeline
        on a single video frame.
        """
        now = timestamp or time.time()
        self._frame_count += 1

        t0 = time.perf_counter()

        # 1. Person Detection (Strictly Class 0: person)
        detections: List[DetectedPerson] = await self.detector.detect(frame, frame_id, now)
        t1 = time.perf_counter()
        inference_latency = (t1 - t0) * 1000.0

        # 2. Multi-Object Tracking
        tracked_persons: List[TrackedPerson] = self.tracker.update(detections, now)
        t2 = time.perf_counter()
        tracking_latency = (t2 - t1) * 1000.0

        # 3. Spatial Queue Analytics
        metrics_res: QueueMetricsResult = self.analytics.process_tracks(tracked_persons, now)

        # 4. Deterministic Risk Evaluation
        risk_res = self.risk_engine.evaluate(metrics_res)

        # 5. Event Generation with 60s Cooldown
        await self.event_engine.evaluate_and_emit(
            metrics=metrics_res,
            risk_score=risk_res.risk_score,
            risk_level=risk_res.risk_level,
            risk_factors=risk_res.contributing_factors,
            zone_id=self.config.zone_id,
        )

        t3 = time.perf_counter()
        analytics_latency = (t3 - t2) * 1000.0

        # 6. Record Health
        self.health_monitor.record_frame(now, inference_latency, analytics_latency)

        # 7. Package Unified Metrics Payload
        payload = {
            "camera_id": self.config.camera_id,
            "camera_code": self.config.camera_code,
            "camera_name": self.config.camera_name,
            "zone_id": self.config.zone_id,
            "zone_code": self.config.zone_code,
            "profile_id": self.config.profile_id,
            "status": self.state.value,
            "timestamp": now,
            "queue_count": metrics_res.queue_count,
            "total_tracked_in_frame": metrics_res.total_tracked_in_frame,
            "excluded_count": metrics_res.excluded_count,
            "occupancy_percentage": metrics_res.occupancy_percentage,
            "occupancy_status": metrics_res.occupancy_status,
            "occupancy_note": metrics_res.occupancy_note,
            "density": metrics_res.density,
            "density_type": metrics_res.density_type,
            "density_unit": metrics_res.density_unit,
            "density_level": metrics_res.density_level,
            "queue_length": metrics_res.queue_length,
            "inflow": metrics_res.inflow,
            "outflow": metrics_res.outflow,
            "flow_delta": metrics_res.flow_delta,
            "queue_direction": metrics_res.queue_direction,
            "average_wait_seconds": metrics_res.average_wait_seconds,
            "median_wait_seconds": metrics_res.median_wait_seconds,
            "max_current_dwell_seconds": metrics_res.max_current_dwell_seconds,
            "completed_wait_samples": metrics_res.completed_wait_samples,
            "wait_status": metrics_res.wait_status,
            "growth_per_minute": metrics_res.growth_per_minute,
            "risk_score": risk_res.risk_score,
            "risk_level": risk_res.risk_level,
            "risk_factors": risk_res.contributing_factors,
            "active_queue_track_ids": metrics_res.active_queue_track_ids,
            "processing_fps": self.config.processing_fps,
            "is_geometry_configured": metrics_res.is_geometry_configured,
            "missing_requirements": metrics_res.missing_requirements,
            "model_info": self.detector.get_model_info() if hasattr(self.detector, "get_model_info") else {
                "model_id": self.config.model.model_id,
                "name": self.config.model.name,
                "version": self.config.model.version,
            },
        }

        self._latest_metrics = payload
        return payload

    def get_metrics(self) -> Dict[str, Any]:
        """Returns the latest calculated operational queue metrics."""
        if self._latest_metrics:
            return self._latest_metrics
        return {
            "camera_id": self.config.camera_id,
            "camera_code": self.config.camera_code,
            "camera_name": self.config.camera_name,
            "zone_id": self.config.zone_id,
            "zone_code": self.config.zone_code,
            "profile_id": self.config.profile_id,
            "status": self.state.value,
            "timestamp": time.time(),
            "queue_count": 0,
            "occupancy_percentage": None,
            "occupancy_status": "NORMAL",
            "occupancy_note": "No active frames processed yet.",
            "density": 0.0,
            "density_type": "RELATIVE",
            "density_unit": "RELATIVE",
            "density_level": "LOW",
            "queue_length": {"value": 0.0, "unit": "normalized_extent", "source": "RELATIVE"},
            "inflow": None,
            "outflow": None,
            "queue_direction": "UNKNOWN",
            "average_wait_seconds": None,
            "median_wait_seconds": None,
            "max_current_dwell_seconds": None,
            "completed_wait_samples": 0,
            "wait_status": "insufficient_data",
            "growth_per_minute": None,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "risk_factors": ["Pipeline initializing"],
            "processing_fps": self.config.processing_fps,
            "is_geometry_configured": self.analytics.has_roi and self.analytics.has_entry and self.analytics.has_exit,
            "missing_requirements": [],
            "model_info": self.detector.get_model_info() if hasattr(self.detector, "get_model_info") else {
                "model_id": self.config.model.model_id,
                "name": self.config.model.name,
                "version": self.config.model.version,
            },
        }

    def get_health(self) -> Dict[str, Any]:
        """Returns current pipeline health diagnostics."""
        return self.health_monitor.compute_health().model_dump()
