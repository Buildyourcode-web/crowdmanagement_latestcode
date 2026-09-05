"""
detector.py — Capacity Resource Detector.

Collects hardware measurements specifically needed by the Capacity Calculator.
"""

from typing import Any, Dict
from app.ai.runtime.detector import RuntimeDetector


class CapacityResourceDetector:
    """Collects hardware inventory metrics required for AI capacity modeling."""

    @staticmethod
    def get_available_compute_resources() -> Dict[str, Any]:
        """Returns verified hardware compute resources."""
        cpu = RuntimeDetector.detect_cpu()
        ram = RuntimeDetector.detect_ram()
        gpu = RuntimeDetector.detect_gpu()

        return {
            "cpu_cores": cpu.get("logical_cores", 1),
            "ram_available_mb": int(ram.get("available_bytes", 0) / (1024 * 1024)),
            "gpu_count": gpu.get("gpu_count", 0),
            "gpu_available": gpu.get("gpu_available", False),
            "gpu_devices": [
                {
                    "name": d.get("name"),
                    "vram_total_mb": d.get("memory_total_mb"),
                    "vram_free_mb": d.get("memory_free_mb"),
                }
                for d in gpu.get("devices", [])
            ],
        }
