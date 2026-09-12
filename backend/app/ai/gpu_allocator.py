"""
gpu_allocator.py — Multi-GPU ONNX Session Pool & Load Balancer.

Provides true parallel inference across all available NVIDIA GPUs for:
- YOLO11x crowd / queue detection (per-camera detector instances)
- InsightFace FRS (shared per-GPU sessions)

Architecture
------------
- On first use, detects all available CUDA GPUs (nvidia-smi or onnxruntime).
- Creates ONE ONNX InferenceSession per GPU device, each pinned to its own
  CUDAExecutionProvider with device_id=N.
- Each session has its OWN threading.Lock — cameras on GPU-0 never block
  cameras on GPU-1, GPU-2 … GPU-7.
- Assigns new camera pipelines to the GPU with the fewest active assignments
  (least-loaded round-robin). Falls back to GPU-0 if CUDA is not available.

Usage
-----
    from app.ai.gpu_allocator import gpu_pool

    # Get the ONNX session + its dedicated lock for a camera
    session, lock, device_id = gpu_pool.acquire(camera_code="CAM-01")

    with lock:
        outputs = session.run(...)

    # On pipeline stop
    gpu_pool.release(camera_code="CAM-01")

    # Convenience — get session+lock for a given GPU index directly
    session, lock = gpu_pool.get_session_for_gpu(gpu_id=2)
"""

from __future__ import annotations

import os
import threading
from typing import Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# GPU count detection (safe — never raises)
# ---------------------------------------------------------------------------

def _detect_gpu_count() -> int:
    """Returns number of NVIDIA CUDA GPUs available to this process."""
    # 1. Env override (useful in Docker with NVIDIA_VISIBLE_DEVICES)
    override = os.getenv("GPU_WORKER_COUNT", "0").strip()
    try:
        n = int(override)
        if n > 0:
            logger.info(f"[GPU-Allocator] GPU_WORKER_COUNT override = {n}")
            return n
    except ValueError:
        pass

    # 2. onnxruntime provider list
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" not in providers:
            return 0
    except Exception:
        return 0

    # 3. Ask nvidia-smi
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        count = len([l for l in result.stdout.strip().splitlines() if l.strip()])
        if count > 0:
            logger.info(f"[GPU-Allocator] Detected {count} GPU(s) via nvidia-smi")
            return count
    except Exception:
        pass

    # 4. torch fallback
    try:
        import torch
        count = torch.cuda.device_count()
        if count > 0:
            logger.info(f"[GPU-Allocator] Detected {count} GPU(s) via torch.cuda")
            return count
    except Exception:
        pass

    # 5. Assume 1 GPU if CUDA provider is present but count unknown
    return 1


# ---------------------------------------------------------------------------
# Per-GPU ONNX Session Entry
# ---------------------------------------------------------------------------

class GPUSessionEntry:
    """Holds one ONNX InferenceSession pinned to a specific CUDA device."""

    def __init__(self, gpu_id: int, model_path: str):
        self.gpu_id = gpu_id
        self.model_path = model_path
        self.session: Optional[object] = None
        self.lock = threading.Lock()           # per-GPU inference lock
        self._active_cameras: List[str] = []  # cameras currently using this GPU
        self._load_session()

    def _load_session(self):
        """Creates the ONNX session pinned to self.gpu_id."""
        try:
            import onnxruntime as ort

            # CUDA provider options: pin to specific device
            cuda_opts: dict = {
                "device_id": self.gpu_id,
                "arena_extend_strategy": "kNextPowerOfTwo",
                "cudnn_conv_algo_search": "EXHAUSTIVE",
                "do_copy_in_default_stream": True,
            }

            # Dynamically query GPU VRAM and reserve 80% for YOLO inference.
            # The remaining 20% stays available for InsightFace FRS sessions
            # sharing the same physical GPU.
            vram_bytes = self._query_vram_bytes(self.gpu_id)
            if vram_bytes and vram_bytes > 0:
                cuda_opts["gpu_mem_limit"] = int(vram_bytes * 0.80)
                logger.info(
                    f"[GPU-Allocator] GPU-{self.gpu_id}: {vram_bytes // (1024**3):.1f} GB VRAM detected, "
                    f"reserving {cuda_opts['gpu_mem_limit'] // (1024**3):.1f} GB (80%) for YOLO"
                )
            # If VRAM cannot be queried, omit gpu_mem_limit — ONNX manages memory naturally.

            providers = [("CUDAExecutionProvider", cuda_opts), "CPUExecutionProvider"]
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 2  # don't over-subscribe CPU per session
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self.session = ort.InferenceSession(
                self.model_path, sess_options=sess_opts, providers=providers
            )
            logger.info(
                f"[GPU-Allocator] ONNX session created on GPU-{self.gpu_id} "
                f"from {self.model_path}"
            )
        except Exception as e:
            logger.warning(
                f"[GPU-Allocator] Failed to create ONNX session on GPU-{self.gpu_id}: {e}"
            )
            self.session = None

    @staticmethod
    def _query_vram_bytes(gpu_id: int) -> Optional[int]:
        """Queries total VRAM in bytes for the given GPU index via nvidia-smi."""
        try:
            import subprocess
            result = subprocess.run(
                [
                    "nvidia-smi",
                    f"--id={gpu_id}",
                    "--query-gpu=memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True, text=True, timeout=5,
            )
            mib = int(result.stdout.strip().splitlines()[0].strip())
            return mib * 1024 * 1024  # MiB → bytes
        except Exception:
            return None

    @property
    def active_count(self) -> int:
        return len(self._active_cameras)

    def assign(self, camera_code: str):
        if camera_code not in self._active_cameras:
            self._active_cameras.append(camera_code)

    def unassign(self, camera_code: str):
        if camera_code in self._active_cameras:
            self._active_cameras.remove(camera_code)


# ---------------------------------------------------------------------------
# GPU Pool — singleton, thread-safe
# ---------------------------------------------------------------------------

class GPUSessionPool:
    """
    Multi-GPU ONNX session pool.

    Creates one ONNX session per available GPU and routes new camera pipelines
    to the least-loaded GPU (fewest active camera assignments).
    """

    def __init__(self):
        self._pool: List[GPUSessionEntry] = []
        self._camera_to_gpu: Dict[str, int] = {}   # camera_code → gpu_id
        self._pool_lock = threading.Lock()
        self._initialized = False
        self._model_path: Optional[str] = None

    # ── Initialization ────────────────────────────────────────────────────

    def initialize(self, model_path: str) -> bool:
        """
        Initializes one ONNX session per detected GPU.
        Safe to call multiple times — idempotent if model_path unchanged.
        """
        with self._pool_lock:
            if self._initialized and self._model_path == model_path:
                return len(self._pool) > 0

            self._model_path = model_path
            self._pool.clear()
            self._camera_to_gpu.clear()

            gpu_count = _detect_gpu_count()
            if gpu_count == 0:
                logger.warning(
                    "[GPU-Allocator] No CUDA GPUs detected — "
                    "will create a single CPU ONNX session as fallback."
                )
                self._pool.append(self._make_cpu_session(model_path))
            else:
                for gpu_id in range(gpu_count):
                    entry = GPUSessionEntry(gpu_id=gpu_id, model_path=model_path)
                    if entry.session is not None:
                        self._pool.append(entry)
                    else:
                        logger.warning(
                            f"[GPU-Allocator] GPU-{gpu_id} session failed — "
                            "skipping this device."
                        )

            if not self._pool:
                logger.error("[GPU-Allocator] No ONNX sessions could be created!")
                self._initialized = False
                return False

            active_gpus = [e.gpu_id for e in self._pool]
            logger.info(
                f"[GPU-Allocator] Initialized {len(self._pool)} ONNX session(s) "
                f"across GPU(s): {active_gpus}"
            )
            self._initialized = True
            return True

    def _make_cpu_session(self, model_path: str) -> "GPUSessionEntry":
        """Creates a CPU-only ONNX session as fallback."""
        entry = GPUSessionEntry.__new__(GPUSessionEntry)
        entry.gpu_id = -1
        entry.model_path = model_path
        entry.lock = threading.Lock()
        entry._active_cameras = []
        try:
            import onnxruntime as ort
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 4
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            entry.session = ort.InferenceSession(
                model_path, sess_options=sess_opts, providers=["CPUExecutionProvider"]
            )
            logger.info(f"[GPU-Allocator] CPU fallback ONNX session created from {model_path}")
        except Exception as e:
            logger.error(f"[GPU-Allocator] CPU fallback session failed: {e}")
            entry.session = None
        return entry

    # ── Public API ────────────────────────────────────────────────────────

    def acquire(self, camera_code: str) -> Tuple[Optional[object], threading.Lock, int]:
        """
        Assigns camera_code to the least-loaded GPU.

        Returns:
            (onnx_session, per_gpu_lock, gpu_id)
            gpu_id = -1 if CPU-only fallback.

        Idempotent: calling acquire() twice for the same camera_code
        returns the same GPU assignment.
        """
        with self._pool_lock:
            if not self._pool:
                return None, threading.Lock(), -1

            # Already assigned → return existing
            if camera_code in self._camera_to_gpu:
                gpu_id = self._camera_to_gpu[camera_code]
                entry = self._pool[gpu_id] if gpu_id < len(self._pool) else self._pool[0]
                return entry.session, entry.lock, entry.gpu_id

            # Pick least-loaded GPU (fewest assigned cameras)
            best_entry = min(self._pool, key=lambda e: e.active_count)
            best_entry.assign(camera_code)
            self._camera_to_gpu[camera_code] = self._pool.index(best_entry)
            logger.info(
                f"[GPU-Allocator] Assigned camera '{camera_code}' → GPU-{best_entry.gpu_id} "
                f"(now {best_entry.active_count} cameras on this GPU)"
            )
            return best_entry.session, best_entry.lock, best_entry.gpu_id

    def release(self, camera_code: str):
        """Releases the GPU assignment for a stopped camera pipeline."""
        with self._pool_lock:
            if camera_code not in self._camera_to_gpu:
                return
            pool_idx = self._camera_to_gpu.pop(camera_code)
            if pool_idx < len(self._pool):
                entry = self._pool[pool_idx]
                entry.unassign(camera_code)
                logger.info(
                    f"[GPU-Allocator] Released camera '{camera_code}' from GPU-{entry.gpu_id} "
                    f"({entry.active_count} cameras remaining)"
                )

    def get_session_for_gpu(self, gpu_id: int) -> Tuple[Optional[object], threading.Lock]:
        """
        Direct access to a specific GPU's session + lock.
        Use for FRS InsightFace sessions that are GPU-pinned separately.
        """
        with self._pool_lock:
            for entry in self._pool:
                if entry.gpu_id == gpu_id:
                    return entry.session, entry.lock
            # Fallback: first available
            if self._pool:
                return self._pool[0].session, self._pool[0].lock
        return None, threading.Lock()

    def get_status(self) -> List[dict]:
        """Returns per-GPU allocation status for health/dashboard endpoints."""
        with self._pool_lock:
            return [
                {
                    "gpu_id": e.gpu_id,
                    "model_path": e.model_path,
                    "active_cameras": list(e._active_cameras),
                    "active_count": e.active_count,
                    "session_ready": e.session is not None,
                }
                for e in self._pool
            ]

    @property
    def is_ready(self) -> bool:
        return self._initialized and bool(self._pool)

    @property
    def gpu_count(self) -> int:
        return len(self._pool)


# ---------------------------------------------------------------------------
# Global singleton — imported by detector.py and frs_service.py
# ---------------------------------------------------------------------------

gpu_pool = GPUSessionPool()


def initialize_gpu_pool(model_path: str) -> bool:
    """
    Call once at startup (e.g. from lifespan or first pipeline start).
    Safe to call from multiple threads — internally serialized.
    """
    return gpu_pool.initialize(model_path)
