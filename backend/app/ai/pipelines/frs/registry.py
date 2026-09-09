"""
registry.py — FRS Pipeline Session Registry.

Central thread-safe registry tracking active FRS pipeline instances.
"""

from typing import Dict, List, Optional

from app.ai.pipelines.frs.pipeline import FRSPipeline


class FRSPipelineRegistry:
    """Registry maintaining active FRS pipelines by camera_code."""

    _pipelines: Dict[str, FRSPipeline] = {}

    @classmethod
    def register(cls, camera_code: str, pipeline: FRSPipeline) -> None:
        cls._pipelines[camera_code] = pipeline

    @classmethod
    def unregister(cls, camera_code: str) -> Optional[FRSPipeline]:
        return cls._pipelines.pop(camera_code, None)

    @classmethod
    def get(cls, camera_code: str) -> Optional[FRSPipeline]:
        return cls._pipelines.get(camera_code)

    @classmethod
    async def stop_pipeline(cls, camera_code: str) -> bool:
        pipeline = cls.get(camera_code)
        if not pipeline:
            return False
        await pipeline.stop()
        cls.unregister(camera_code)
        return True

    @classmethod
    def get_all(cls) -> Dict[str, FRSPipeline]:
        return dict(cls._pipelines)

    @classmethod
    def clear(cls) -> None:
        cls._pipelines.clear()
