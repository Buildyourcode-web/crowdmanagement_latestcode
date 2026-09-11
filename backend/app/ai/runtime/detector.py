"""
detector.py — Production-Safe Server Capability & Hardware Detection.

Inspects host computing architecture:
- CPU (physical/logical cores, usage %, frequency)
- RAM (total, available, used, percent)
- NVIDIA GPU & Accelerators (availability, count, names, UUIDs, VRAM total/free/used, utilization %, temp, driver)
- NVIDIA & AI Stacks (nvidia-smi, CUDA, TensorRT, DeepStream, NVIDIA Container Toolkit, Docker)
- Storage & System (disk total/free/used %, hostname, OS, uptime)
- Database & Cache Readiness (PostgreSQL, Redis)
- AI Runtime Readiness (AI_RUNTIME_READY, AI_RUNTIME_PARTIAL, AI_RUNTIME_NOT_READY)

Guaranteed safe on CPU-only machines, single-GPU edge boxes, and multi-GPU production servers.
"""

import os
import shutil
import socket
import platform
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
try:
    import psutil
except ImportError:
    psutil = None
from loguru import logger


# Module initialization timestamp for uptime calculation
_PROCESS_START_TIME = time.time()


class RuntimeDetector:
    """Detects system hardware, accelerators, runtimes, and core service readiness."""

    @staticmethod
    def detect_server() -> Dict[str, Any]:
        """Detects server identity, platform, and uptime."""
        try:
            boot_time = psutil.boot_time()
            uptime_sec = int(time.time() - boot_time)
        except Exception:
            uptime_sec = int(time.time() - _PROCESS_START_TIME)

        return {
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "platform_system": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "uptime_seconds": max(uptime_sec, 0),
        }

    @staticmethod
    def detect_cpu() -> Dict[str, Any]:
        """Detect host CPU specifications and current load."""
        if psutil is not None:
            try:
                freq = psutil.cpu_freq()
                freq_mhz = round(freq.current, 1) if freq and freq.current else None
            except Exception:
                freq_mhz = None
            physical_cores = psutil.cpu_count(logical=False) or 1
            logical_cores = psutil.cpu_count(logical=True) or physical_cores
            usage_pct = psutil.cpu_percent(interval=None)
        else:
            freq_mhz = None
            physical_cores = os.cpu_count() or 1
            logical_cores = physical_cores
            usage_pct = 10.0

        return {
            "processor": platform.processor() or platform.machine(),
            "physical_cores": physical_cores,
            "logical_cores": logical_cores,
            "usage_percent": usage_pct,
            "current_freq_mhz": freq_mhz,
        }

    @staticmethod
    def detect_ram() -> Dict[str, Any]:
        """Detect system physical memory (RAM)."""
        try:
            mem = psutil.virtual_memory()
            return {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "available_gb": round(mem.available / (1024 ** 3), 2),
                "used_gb": round(mem.used / (1024 ** 3), 2),
                "used_percent": round(mem.percent, 1),
                "total_bytes": mem.total,
                "available_bytes": mem.available,
                "used_bytes": mem.used,
            }
        except Exception as e:
            logger.debug(f"[RuntimeDetector] RAM error: {e}")
            return {
                "total_gb": 0.0,
                "available_gb": 0.0,
                "used_gb": 0.0,
                "used_percent": 0.0,
                "error": str(e),
            }

    @staticmethod
    def detect_storage() -> Dict[str, Any]:
        """Detect disk storage on current workspace drive."""
        try:
            cwd = os.getcwd()
            disk = shutil.disk_usage(cwd)
            total_gb = round(disk.total / (1024 ** 3), 2)
            free_gb = round(disk.free / (1024 ** 3), 2)
            used_gb = round(disk.used / (1024 ** 3), 2)
            used_pct = round((disk.used / disk.total) * 100, 1) if disk.total > 0 else 0.0

            return {
                "path": cwd,
                "total_gb": total_gb,
                "free_gb": free_gb,
                "used_gb": used_gb,
                "used_percent": used_pct,
                "total_bytes": disk.total,
                "free_bytes": disk.free,
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def detect_gpu() -> Dict[str, Any]:
        """
        Safely detects NVIDIA GPUs, driver, VRAM, and GPU UUIDs via nvidia-smi.
        Returns available=False if no GPU is present or query fails (safe for CPU machines).
        """
        nvidia_smi_path = shutil.which("nvidia-smi")
        if not nvidia_smi_path:
            return {
                "available": False,
                "count": 0,
                "devices": [],
                "driver_version": None,
                "cuda_version": None,
                "status": "NOT_AVAILABLE",
                "message": "nvidia-smi utility not found. Server operating in CPU mode.",
            }

        try:
            cmd = [
                nvidia_smi_path,
                "--query-gpu=index,name,uuid,memory.total,memory.free,memory.used,driver_version,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return {
                    "available": False,
                    "count": 0,
                    "devices": [],
                    "driver_version": None,
                    "cuda_version": None,
                    "status": "NOT_AVAILABLE",
                    "message": "NVIDIA GPU driver returned empty or error response.",
                }

            devices = []
            driver_ver = None
            lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]

            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 7:
                    idx = int(parts[0])
                    name = parts[1]
                    uuid_str = parts[2]
                    mem_total_mb = int(parts[3])
                    mem_free_mb = int(parts[4])
                    mem_used_mb = int(parts[5])
                    driver_ver = parts[6]
                    temp_c = int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else None
                    util_pct = int(parts[8]) if len(parts) > 8 and parts[8].isdigit() else None

                    devices.append({
                        "index": idx,
                        "name": name,
                        "uuid": uuid_str,
                        "total_vram_gb": round(mem_total_mb / 1024, 2),
                        "free_vram_gb": round(mem_free_mb / 1024, 2),
                        "used_vram_gb": round(mem_used_mb / 1024, 2),
                        "memory_total_mb": mem_total_mb,
                        "memory_free_mb": mem_free_mb,
                        "memory_used_mb": mem_used_mb,
                        "gpu_utilization_percent": util_pct or 0,
                        "temperature_c": temp_c,
                    })

            # Check CUDA version via nvcc or nvidia-smi header
            cuda_ver = RuntimeDetector._detect_cuda_version(nvidia_smi_path)

            has_gpu = len(devices) > 0
            return {
                "available": has_gpu,
                "count": len(devices),
                "devices": devices,
                "driver_version": driver_ver,
                "cuda_version": cuda_ver,
                "status": "AVAILABLE" if has_gpu else "NOT_AVAILABLE",
                "message": (
                    f"Found {len(devices)} NVIDIA GPU device(s)."
                    if has_gpu
                    else "No active NVIDIA GPUs found."
                ),
            }

        except Exception as e:
            logger.debug(f"[RuntimeDetector] GPU query exception: {e}")
            return {
                "available": False,
                "count": 0,
                "devices": [],
                "driver_version": None,
                "cuda_version": None,
                "status": "ERROR_QUERYING",
                "message": f"Query failed: {str(e)}",
            }

    @staticmethod
    def _detect_cuda_version(nvidia_smi_path: Optional[str] = None) -> Optional[str]:
        """Detect CUDA toolkit or runtime driver version."""
        # 1. Try nvcc
        nvcc_path = shutil.which("nvcc")
        if nvcc_path:
            try:
                nvcc_res = subprocess.run([nvcc_path, "--version"], capture_output=True, text=True, timeout=3)
                for l in nvcc_res.stdout.split("\n"):
                    if "release" in l:
                        return l.split("release")[-1].strip().split(",")[0].strip()
            except Exception:
                pass

        # 2. Try parsing nvidia-smi output header
        if nvidia_smi_path:
            try:
                res = subprocess.run([nvidia_smi_path], capture_output=True, text=True, timeout=3)
                for line in res.stdout.split("\n"):
                    if "CUDA Version:" in line:
                        parts = line.split("CUDA Version:")
                        if len(parts) > 1:
                            return parts[1].strip().split(" ")[0].strip()
            except Exception:
                pass

        return None

    @staticmethod
    def detect_runtime() -> Dict[str, Any]:
        """Detect container and AI software stacks."""
        # Docker
        docker_path = shutil.which("docker")
        docker_avail = bool(docker_path)
        docker_version = None
        if docker_avail:
            try:
                d_res = subprocess.run([docker_path, "--version"], capture_output=True, text=True, timeout=3)
                docker_version = d_res.stdout.strip()
            except Exception:
                pass

        # NVIDIA Container Toolkit
        nvidia_ctk = bool(shutil.which("nvidia-ctk") or shutil.which("nvidia-container-cli"))

        # TensorRT
        tensorrt_avail = False
        tensorrt_version = None
        try:
            import tensorrt  # noqa
            tensorrt_avail = True
            tensorrt_version = getattr(tensorrt, "__version__", "installed")
        except ImportError:
            pass

        # DeepStream
        deepstream_avail = False
        deepstream_path = os.environ.get("DEEPSTREAM_PATH", "/opt/nvidia/deepstream/deepstream")
        if os.path.exists(deepstream_path) or shutil.which("deepstream-app"):
            deepstream_avail = True

        # CUDA availability (from GPU check)
        cuda_avail = bool(RuntimeDetector._detect_cuda_version(shutil.which("nvidia-smi")))

        return {
            "docker": docker_avail,
            "docker_version": docker_version,
            "cuda": cuda_avail,
            "tensorrt": tensorrt_avail,
            "tensorrt_version": tensorrt_version,
            "deepstream": deepstream_avail,
            "nvidia_container_toolkit": nvidia_ctk,
        }

    @staticmethod
    async def check_database_readiness() -> Dict[str, Any]:
        """Check PostgreSQL database connection readiness and response time."""
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import text
        try:
            start = time.perf_counter()
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "postgresql": True,
                "latency_ms": latency_ms,
                "status": "READY",
            }
        except Exception as e:
            return {
                "postgresql": False,
                "latency_ms": None,
                "status": "UNAVAILABLE",
                "error": str(e),
            }

    @staticmethod
    async def check_redis_readiness() -> Dict[str, Any]:
        """Check Redis event bus connectivity."""
        from app.redis.client import get_redis_connection
        try:
            conn = await get_redis_connection()
            if conn:
                await conn.ping()
                return {
                    "available": True,
                    "mode": "CONNECTED",
                    "status": "READY",
                }
            return {
                "available": False,
                "mode": "STANDALONE_FALLBACK",
                "status": "FALLBACK_IN_MEMORY",
            }
        except Exception as e:
            return {
                "available": False,
                "mode": "ERROR",
                "status": "UNAVAILABLE",
                "error": str(e),
            }

    @classmethod
    def evaluate_readiness(
        cls,
        gpu_info: Dict[str, Any],
        runtime_info: Dict[str, Any],
        db_info: Dict[str, Any],
        redis_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluates overall AI runtime readiness:
        - AI_RUNTIME_READY: GPU, CUDA, Docker, DB ready.
        - AI_RUNTIME_PARTIAL: DB ready, but GPU, TensorRT, or DeepStream absent (CPU fallback mode).
        - AI_RUNTIME_NOT_READY: Core database or critical compute dependencies failed.
        """
        missing: List[str] = []
        notes: List[str] = []

        if not db_info.get("postgresql"):
            missing.append("PostgreSQL Database")
        if not gpu_info.get("available"):
            missing.append("NVIDIA GPU")
            notes.append("Server operates in CPU-only mode. GPU accelerated pipelines disabled.")
        if not runtime_info.get("cuda"):
            missing.append("CUDA Toolkit")
        if not runtime_info.get("tensorrt"):
            missing.append("TensorRT Runtime")
            notes.append("High-throughput INT8/FP16 TensorRT inference unavailable; ONNX fallback.")
        if not runtime_info.get("deepstream"):
            missing.append("DeepStream SDK")
            notes.append("Hardware-accelerated multi-stream NVDEC decode pipeline unavailable.")
        if not runtime_info.get("docker"):
            missing.append("Docker Engine")

        if not db_info.get("postgresql"):
            readiness = "AI_RUNTIME_NOT_READY"
            summary = "Core platform database is unreachable. AI pipelines cannot record events."
        elif (
            not gpu_info.get("available")
            or not runtime_info.get("cuda")
            or not runtime_info.get("tensorrt")
            or not runtime_info.get("deepstream")
        ):
            readiness = "AI_RUNTIME_PARTIAL"
            summary = (
                "Partial runtime available. One or more AI stack components are missing. "
                "Operating in CPU/ONNX fallback mode. GPU acceleration may not be fully active."
            )
        else:
            readiness = "AI_RUNTIME_READY"
            summary = "Full AI runtime environment ready for hardware-accelerated pipeline deployment."

        return {
            "readiness": readiness,
            "summary": summary,
            "missing_components": missing,
            "diagnostic_notes": notes,
        }

    @classmethod
    async def get_full_capabilities(cls) -> Dict[str, Any]:
        """
        Aggregate complete server capability inspection conforming to Section 3 specification.
        """
        server = cls.detect_server()
        cpu = cls.detect_cpu()
        memory = cls.detect_ram()
        storage = cls.detect_storage()
        gpu = cls.detect_gpu()
        runtime = cls.detect_runtime()
        db = await cls.check_database_readiness()
        redis = await cls.check_redis_readiness()
        readiness = cls.evaluate_readiness(gpu, runtime, db, redis)

        return {
            "server": server,
            "cpu": cpu,
            "memory": memory,
            "storage": storage,
            "gpu": gpu,
            "runtime": runtime,
            "database": db,
            "redis": redis,
            "readiness": readiness,
            "inspected_at": datetime.now(timezone.utc).isoformat(),
        }
