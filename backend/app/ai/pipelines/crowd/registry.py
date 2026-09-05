"""
registry.py — Crowd Pipeline Instance Registry & Multi-Camera Manager.

Maintains running CrowdPipeline instances, provides lifecycle hooks,
and aggregates metrics across camera and zone hierarchies.
"""

from typing import Any, Dict, List, Optional
from loguru import logger
from app.ai.pipelines.crowd.pipeline import CrowdPipeline


class CrowdPipelineRegistry:
    """Singleton registry tracking active Crowd AI pipelines across all cameras."""

    _pipelines_by_id: Dict[str, CrowdPipeline] = {}
    _pipelines_by_code: Dict[str, CrowdPipeline] = {}

    @classmethod
    def register(cls, pipeline: CrowdPipeline) -> None:
        """Registers an active or instantiated pipeline."""
        cls._pipelines_by_id[pipeline.camera_id] = pipeline
        cls._pipelines_by_code[pipeline.camera_code] = pipeline
        logger.info(f"[PipelineRegistry] Registered pipeline for camera {pipeline.camera_code} ({pipeline.camera_id})")

    @classmethod
    def get(cls, camera_id_or_code: str) -> Optional[CrowdPipeline]:
        """Retrieves pipeline by either camera UUID or camera_code."""
        return cls._pipelines_by_id.get(camera_id_or_code) or cls._pipelines_by_code.get(camera_id_or_code)

    @classmethod
    async def stop_pipeline(cls, camera_id_or_code: str) -> bool:
        """Stops and unregisters an active pipeline."""
        pipeline = cls.get(camera_id_or_code)
        if not pipeline:
            return False

        await pipeline.stop()
        cls._pipelines_by_id.pop(pipeline.camera_id, None)
        cls._pipelines_by_code.pop(pipeline.camera_code, None)
        logger.info(f"[PipelineRegistry] Unregistered pipeline for camera {pipeline.camera_code}")
        return True

    @classmethod
    def list_pipelines(cls) -> List[CrowdPipeline]:
        """Returns list of all active pipeline instances."""
        return list(cls._pipelines_by_id.values())

    @classmethod
    def get_all_metrics(cls) -> List[Dict[str, Any]]:
        """Returns latest metrics from all active pipelines."""
        return [p.get_metrics() for p in cls._pipelines_by_id.values()]

    @classmethod
    def get_zone_aggregated_metrics(cls, zone_id_or_code: str) -> Dict[str, Any]:
        """Aggregates crowd metrics across all cameras assigned to a zone."""
        matching_pipelines = [
            p for p in cls._pipelines_by_id.values()
            if p.config.zone_id == zone_id_or_code or p.config.zone_code == zone_id_or_code
        ]

        total_count = sum(p.get_metrics().get("count", 0) for p in matching_pipelines)
        densities = [p.get_metrics().get("density", 0.0) for p in matching_pipelines]
        avg_density = round(sum(densities) / len(densities), 2) if densities else 0.0

        # Flow rates
        inflows = [p.get_metrics().get("inflow") for p in matching_pipelines if p.get_metrics().get("inflow") is not None]
        outflows = [p.get_metrics().get("outflow") for p in matching_pipelines if p.get_metrics().get("outflow") is not None]
        total_inflow = sum(inflows) if inflows else None
        total_outflow = sum(outflows) if outflows else None

        # Maximum risk level in the zone
        risk_scores = [p.get_metrics().get("risk_score", 0.0) for p in matching_pipelines]
        max_risk_score = max(risk_scores) if risk_scores else 0.0
        if max_risk_score >= 85.0:
            zone_risk_level = "CRITICAL"
        elif max_risk_score >= 65.0:
            zone_risk_level = "HIGH"
        elif max_risk_score >= 35.0:
            zone_risk_level = "MEDIUM"
        else:
            zone_risk_level = "LOW"

        return {
            "zone_id": zone_id_or_code,
            "active_cameras": len(matching_pipelines),
            "camera_codes": [p.camera_code for p in matching_pipelines],
            "total_count": total_count,
            "average_density": avg_density,
            "total_inflow": total_inflow,
            "total_outflow": total_outflow,
            "max_risk_score": max_risk_score,
            "risk_level": zone_risk_level,
        }

    @classmethod
    async def stop_all(cls) -> None:
        """Stops all active pipelines cleanly."""
        for p in list(cls._pipelines_by_id.values()):
            try:
                await p.stop()
            except Exception as e:
                logger.warning(f"[PipelineRegistry] Error stopping pipeline {p.camera_code}: {e}")
        cls._pipelines_by_id.clear()
        cls._pipelines_by_code.clear()

    @classmethod
    def reset_for_testing(cls) -> None:
        """Resets registry state for test suites."""
        cls._pipelines_by_id.clear()
        cls._pipelines_by_code.clear()
