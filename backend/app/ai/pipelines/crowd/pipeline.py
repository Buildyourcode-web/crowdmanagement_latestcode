"""
pipeline.py — Central Crowd AI Inference Pipeline Coordinator.

Orchestrates the complete multi-camera crowd inference workflow:
RTSP Input -> Person Detection (YOLO11x) -> Multi-Object Tracking (ByteTrack) ->
Boundary State Machine & Spatial Analytics -> Durable PostgreSQL Line Crossing Ledger ->
Crowd Metrics & Reliability Scoring -> Risk Engine -> AI Event Engine -> Redis/WebSocket Telemetry.

Runs in an isolated background asyncio task, decoupled from FastAPI request handlers.
"""

import asyncio
from datetime import datetime, timezone
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.analytics import CrowdMetricsResult, CrowdSpatialAnalytics, ValidatedCrossing
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import (
    BasePersonDetector,
    DeepStreamPersonDetector,
    DetectedPerson,
    YOLO11xPersonDetector,
)
from app.ai.pipelines.crowd.events import CrowdEventEngine
from app.ai.pipelines.crowd.health import PipelineHealthMonitor, PipelineHealthStatus
from app.ai.pipelines.crowd.queue_engine import QueueMetricsResult, QueueMovementEngine
from app.ai.pipelines.crowd.risk import CrowdRiskEngine
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson
from app.db.session import AsyncSessionLocal
from app.models.line_crossing import LineCrossingEvent
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

        # Single Common ByteTrack Tracker
        self.tracker = PersonTracker(
            max_age_frames=45,
            min_hits=1,
            high_threshold=0.50,
            low_threshold=0.15,
            iou_threshold=0.25,
            iou_low_threshold=0.15,
        )

        # Crossing Engine (Signed Distance State Machine)
        self.analytics = CrowdSpatialAnalytics(config)

        # Queue Movement Engine (Shared Tracks Consumer)
        custom_vec = (
            (config.queue_direction_vector["x"], config.queue_direction_vector["y"])
            if config.queue_direction_vector
            else None
        )
        self.queue_engine = QueueMovementEngine(
            passage_roi_points=config.passage_roi_points or config.crowd_roi_points,
            direction=config.queue_direction,
            custom_direction_vector=custom_vec,
        )

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
        self._total_entries_session: int = 0
        self._total_exits_session: int = 0

    async def start(self) -> bool:
        """Validates requirements and launches background pipeline execution loop."""
        # Check ROI Readiness
        if len(self.config.crowd_roi_points) < 3 and len(self.config.counting_lines) == 0:
            self.state = PipelineState.FAILED
            self.health_monitor.pipeline_state = self.state
            self.health_monitor.record_error("Spatial geometries (ROI or counting lines) not configured")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "ROI_NOT_CONFIGURED",
                    "message": "Spatial boundary is not configured. Configure spatial boundaries before starting pipeline.",
                },
            )

        self.state = PipelineState.STARTING
        self.health_monitor.pipeline_state = self.state

        # Initialize Detector
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

        self.state = PipelineState.RUNNING
        self.health_monitor.pipeline_state = self.state
        self._stop_requested = False

        self._worker_task = asyncio.create_task(self._run_stream_loop())
        logger.info(
            f"[CrowdPipeline] Started Crowd AI pipeline for {self.camera_code} "
            f"({self.profile_id}) with ByteTrack MOT & Boundary State Machine."
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
        self.queue_engine.reset()

        self.state = PipelineState.STOPPED
        self.health_monitor.pipeline_state = self.state
        logger.info(f"[CrowdPipeline] Stopped pipeline for {self.camera_code}")
        return True

    async def _persist_crossings_durable(self, crossings: List[ValidatedCrossing]) -> None:
        """Persists crossing events into PostgreSQL line_crossing_events with ON CONFLICT DO NOTHING."""
        if not crossings:
            return

        try:
            async with AsyncSessionLocal() as session:
                bind = session.bind or session.get_bind()
                if bind and "sqlite" in bind.dialect.name:
                    from sqlalchemy.dialects.sqlite import insert as dialect_insert
                else:
                    from sqlalchemy.dialects.postgresql import insert as dialect_insert

                for c in crossings:
                    evt_uuid = uuid.UUID(c.event_id) if c.event_id else None
                    site_uuid = uuid.UUID(c.site_id) if c.site_id else None
                    cam_uuid = uuid.UUID(c.camera_id) if isinstance(c.camera_id, str) else c.camera_id

                    stmt = dialect_insert(LineCrossingEvent).values(
                        id=uuid.uuid4(),
                        event_id=evt_uuid,
                        site_id=site_uuid,
                        camera_id=cam_uuid,
                        camera_code=c.camera_code,
                        line_id=c.line_id,
                        line_name=c.line_name,
                        track_session_id=c.track_session_id,
                        track_token=c.track_token,
                        crossing_sequence=c.crossing_sequence,
                        direction=c.direction,
                        count_delta=c.count_delta,
                        detection_confidence=c.detection_confidence,
                        frame_id=c.frame_id,
                        crossing_timestamp=datetime.fromtimestamp(c.timestamp, tz=timezone.utc),
                        idempotency_key=c.idempotency_key,
                        ground_x=c.ground_x,
                        ground_y=c.ground_y,
                        signed_distance=c.signed_distance,
                    ).on_conflict_do_nothing(
                        index_elements=["idempotency_key"]
                    )
                    await session.execute(stmt)
                await session.commit()
        except Exception as ex:
            logger.warning(f"[CrowdPipeline] Error persisting durable crossing event: {ex}")

    def _compute_count_reliability(self, health: PipelineHealthStatus) -> Tuple[str, float]:
        """Calculates count reliability tier and confidence score (0-100%)."""
        fps = health.processed_fps
        target_fps = max(1.0, float(self.config.processing_fps))
        fps_ratio = min(1.0, fps / target_fps)

        if health.health_status == "HEALTHY" and fps_ratio >= 0.8:
            score = round(90.0 + fps_ratio * 10.0, 1)
            tier = "HIGH"
        elif health.health_status in ("HEALTHY", "DEGRADED") and fps_ratio >= 0.5:
            score = round(70.0 + fps_ratio * 20.0, 1)
            tier = "MEDIUM"
        else:
            score = round(max(30.0, fps_ratio * 60.0), 1)
            tier = "LOW"
        return tier, score

    async def process_frame(
        self,
        frame_data: Any,
        frame_id: int,
        timestamp: float,
    ) -> Dict[str, Any]:
        """Executes a single end-to-end frame cycle with ByteTrack and Durable Ledger."""
        t0 = time.time()

        # Step 1: Detect Persons (YOLO11x)
        detections: List[DetectedPerson] = await self.detector.detect(frame_data, frame_id, timestamp)
        t_det = (time.time() - t0) * 1000.0

        # Step 2: Multi-Object Tracking (ByteTrack 2-Stage)
        t1 = time.time()
        tracks: List[TrackedPerson] = self.tracker.update(detections, timestamp)
        t_trk = (time.time() - t1) * 1000.0

        # Step 3: Spatial Boundary State Machine & Line Analytics
        metrics: CrowdMetricsResult = self.analytics.process_tracks(tracks, timestamp, frame_id=frame_id)
        validated_crossings: List[ValidatedCrossing] = self.analytics.get_and_clear_crossings()

        # Step 4: Queue Movement Engine (Uses Same Shared Tracks)
        queue_metrics: QueueMetricsResult = self.queue_engine.process_tracks(tracks, timestamp)

        # Step 5: Durable Event Persistence & Live Rollup
        if validated_crossings:
            asyncio.create_task(self._persist_crossings_durable(validated_crossings))
            for c in validated_crossings:
                if c.direction == "IN":
                    self._total_entries_session += c.count_delta
                elif c.direction == "OUT":
                    self._total_exits_session += c.count_delta

                # Broadcast immediate real-time crossing event over WebSocket
                crossing_payload = {
                    "type": "line_crossing",
                    "event_type": "LINE_CROSSING",
                    "event_id": c.event_id,
                    "site_id": c.site_id,
                    "camera_id": c.camera_id,
                    "camera_code": c.camera_code,
                    "line_id": c.line_id,
                    "line_name": c.line_name,
                    "track_token": c.track_token,
                    "crossing_sequence": c.crossing_sequence,
                    "direction": c.direction,
                    "count_delta": c.count_delta,
                    "timestamp": c.timestamp,
                    "idempotency_key": c.idempotency_key,
                    "inflow_rate": metrics.inflow_rate,
                    "outflow_rate": metrics.outflow_rate,
                }
                try:
                    await event_bus.publish(channel="crowd", event_type="LINE_CROSSING", payload=crossing_payload)
                except Exception as ex:
                    logger.debug(f"[CrowdPipeline] Crossing publish error: {ex}")

        # Step 6: Health & Reliability Evaluation
        health_report = self.health_monitor.compute_health()
        rel_tier, rel_score = self._compute_count_reliability(health_report)

        # Step 7: Deterministic Risk Engine
        risk_score, risk_level, factors = self.risk_engine.calculate_risk(
            metrics,
            stream_health=health_report.health_status,
        )

        # Step 8: AI Event Generation & Cooldown Suppression
        events = await self.event_engine.evaluate_and_emit(
            metrics,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=factors,
            stream_health=health_report.health_status,
        )

        # Record health metrics
        t_total = (time.time() - t0) * 1000.0
        self.health_monitor.record_frame(
            timestamp=timestamp,
            detection_latency_ms=t_det,
            tracking_latency_ms=t_trk,
        )

        # Package Unified Metrics
        result_payload = {
            "camera_id": self.camera_id,
            "camera_code": self.camera_code,
            "camera_name": self.config.camera_name,
            "event_id": self.config.event_id,
            "site_id": self.config.site_id,
            "zone_id": self.config.zone_id,
            "zone_code": self.config.zone_code,
            "profile_id": self.profile_id,
            "purpose": self.config.camera_purpose,
            "timestamp": timestamp,
            "timestamp_iso": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
            "status": self.state.value,
            "health": health_report.health_status,
            "count_reliability": rel_tier,
            "count_confidence_score": rel_score,
            "count": metrics.current_count,
            "entry_count": self._total_entries_session,
            "exit_count": self._total_exits_session,
            "density": metrics.density,
            "density_type": metrics.density_type,
            "density_unit": metrics.density_unit,
            "density_level": metrics.density_level,
            "inflow": metrics.inflow_rate,
            "outflow": metrics.outflow_rate,
            "flow_delta": metrics.flow_delta,
            "session_entries": self._total_entries_session,
            "session_exits": self._total_exits_session,
            "queue": queue_metrics.to_dict(),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": factors,
            "events_fired": [e.event_type for e in events],
            "fps": health_report.processed_fps,
            "latencies": {
                "detection_ms": round(t_det, 1),
                "tracking_ms": round(t_trk, 1),
                "total_ms": round(t_total, 1),
            },
            "model_info": self.detector.get_model_info() if hasattr(self.detector, "get_model_info") else {
                "model_id": self.config.model.model_id,
                "name": self.config.model.name,
                "version": self.config.model.version,
            },
        }
        self._latest_metrics = result_payload

        # Broadcast WebSocket Telemetry (Throttled to max 2/sec)
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
        """Background stream processing loop."""
        interval = 1.0 / max(float(self.config.processing_fps), 1.0)
        frame_id = 0

        while not self._stop_requested:
            try:
                now = time.time()
                frame_id += 1
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
            "event_id": self.config.event_id,
            "site_id": self.config.site_id,
            "zone_id": self.config.zone_id,
            "zone_code": self.config.zone_code,
            "profile_id": self.profile_id,
            "timestamp": time.time(),
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "status": self.state.value,
            "health": self.health_monitor.compute_health().health_status,
            "count_reliability": "HIGH",
            "count_confidence_score": 95.0,
            "count": 0,
            "density": 0.0,
            "density_type": "RELATIVE_DENSITY",
            "density_unit": "RELATIVE_DENSITY",
            "density_level": "LOW",
            "inflow": None,
            "outflow": None,
            "flow_delta": None,
            "session_entries": 0,
            "session_exits": 0,
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
