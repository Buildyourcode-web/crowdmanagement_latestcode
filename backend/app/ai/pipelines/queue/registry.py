"""
registry.py — Queue AI Active Pipeline Registry.

Tracks active Queue AI pipelines in memory, coordinates lifecycle teardown,
and provides multi-camera zone aggregations.
"""

from typing import Any, Dict, List, Optional
from loguru import logger

from app.ai.pipelines.crowd.pipeline import PipelineState
from app.ai.pipelines.queue.pipeline import QueuePipeline


class QueuePipelineRegistry:
    """Thread-safe singleton registry for active Queue AI pipelines."""

    _pipelines: Dict[str, QueuePipeline] = {}

    @classmethod
    def register(cls, pipeline: QueuePipeline) -> None:
        """Registers an active queue pipeline."""
        cam_code = pipeline.config.camera_code
        if cam_code in cls._pipelines:
            logger.warning(f"Overwriting existing Queue pipeline for camera '{cam_code}'")
        cls._pipelines[cam_code] = pipeline
        logger.info(f"Registered Queue AI pipeline for camera '{cam_code}'. Total active: {len(cls._pipelines)}")

    @classmethod
    def unregister(cls, camera_code: str) -> Optional[QueuePipeline]:
        """Removes a pipeline from the registry."""
        pipe = cls._pipelines.pop(camera_code, None)
        if pipe:
            logger.info(f"Unregistered Queue AI pipeline for '{camera_code}'. Remaining: {len(cls._pipelines)}")
        return pipe

    @classmethod
    def get(cls, camera_code: str) -> Optional[QueuePipeline]:
        """Retrieves a running queue pipeline by camera code."""
        return cls._pipelines.get(camera_code)

    @classmethod
    def list_all(cls) -> List[QueuePipeline]:
        """Returns all registered queue pipelines."""
        return list(cls._pipelines.values())

    @classmethod
    def count(cls) -> int:
        return len(cls._pipelines)

    @classmethod
    def reset_for_testing(cls) -> None:
        """Resets the pipeline registry for testing isolation."""
        cls._pipelines.clear()

    @classmethod
    async def stop_pipeline(cls, camera_code: str) -> bool:
        """Stops and unregisters a specific queue pipeline."""
        pipe = cls.get(camera_code)
        if not pipe:
            return False
        await pipe.stop()
        cls.unregister(camera_code)
        return True

    @classmethod
    async def stop_all(cls) -> None:
        """Stops all active queue pipelines during server shutdown."""
        logger.info(f"Stopping all {len(cls._pipelines)} active Queue AI pipelines...")
        for cam_code, pipe in list(cls._pipelines.items()):
            try:
                await pipe.stop()
            except Exception as e:
                logger.error(f"Error stopping Queue pipeline '{cam_code}': {e}")
        cls._pipelines.clear()

    @classmethod
    def get_zone_summary(cls, zone_id_or_code: str) -> Dict[str, Any]:
        """Aggregates queue metrics across all active cameras in a specific zone."""
        sector_pipelines = [
            p for p in cls._pipelines.values()
            if (p.config.zone_id == zone_id_or_code or p.config.zone_code == zone_id_or_code)
            and p.state == PipelineState.RUNNING
        ]

        if not sector_pipelines:
            return {
                "zone": zone_id_or_code,
                "active_queues_count": 0,
                "total_people_in_queues": 0,
                "total_inflow": 0,
                "total_outflow": 0,
                "average_wait_seconds": None,
                "max_risk_score": 0.0,
                "max_risk_level": "LOW",
                "cameras": [],
            }

        total_q_count = 0
        total_inflow = 0
        total_outflow = 0
        max_risk = 0.0
        max_level = "LOW"
        wait_times: List[int] = []
        cam_summaries = []

        risk_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

        for pipe in sector_pipelines:
            m = pipe.get_metrics()
            total_q_count += m.get("queue_count", 0)
            total_inflow += (m.get("inflow") or 0)
            total_outflow += (m.get("outflow") or 0)

            w = m.get("average_wait_seconds")
            if w is not None:
                wait_times.append(w)

            r_score = m.get("risk_score", 0.0)
            r_level = m.get("risk_level", "LOW")
            if r_score > max_risk:
                max_risk = r_score
            if risk_rank.get(r_level, 1) > risk_rank.get(max_level, 1):
                max_level = r_level

            cam_summaries.append({
                "camera_code": pipe.config.camera_code,
                "queue_name": pipe.config.queue_roi_name,
                "queue_count": m.get("queue_count", 0),
                "occupancy_percentage": m.get("occupancy_percentage"),
                "average_wait_seconds": m.get("average_wait_seconds"),
                "risk_score": r_score,
                "risk_level": r_level,
            })

        avg_wait = int(round(sum(wait_times) / len(wait_times))) if wait_times else None

        return {
            "zone": zone_id_or_code,
            "active_queues_count": len(sector_pipelines),
            "total_people_in_queues": total_q_count,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "average_wait_seconds": avg_wait,
            "max_risk_score": max_risk,
            "max_risk_level": max_level,
            "cameras": cam_summaries,
        }
