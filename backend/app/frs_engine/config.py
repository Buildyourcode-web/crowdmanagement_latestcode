"""
config.py — Central configuration loader for FRS R&D.
All settings come from .env or environment variables.
No hardcoded secrets or credentials.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes")


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── Model ─────────────────────────────────────────────────────────────────────
MODEL_NAME: str = os.getenv("MODEL_NAME", "buffalo_l")
DET_SIZE: int = _int(os.getenv("DET_SIZE"), 960)
USE_CUDA: bool = _bool(os.getenv("USE_CUDA"), True)

# ── Matching ───────────────────────────────────────────────────────────────────
# Calibrated 65% threshold: matches enrolled identities reliably while rejecting background crowd.
MATCH_THRESHOLD: float = _float(os.getenv("FRS_MATCH_THRESHOLD") or os.getenv("MATCH_THRESHOLD"), 0.65)
MATCHING_STRATEGY: str = os.getenv("MATCHING_STRATEGY", "max_similarity")
AMBIGUITY_MARGIN: float = _float(os.getenv("AMBIGUITY_MARGIN"), 0.05)

# ── Face Quality & Size Thresholds ─────────────────────────────────────────────
MIN_SHARPNESS_SCORE: float = _float(os.getenv("MIN_SHARPNESS_SCORE"), 45.0)
MIN_FACE_WIDTH: int = _int(os.getenv("MIN_FACE_WIDTH"), 60)
MAX_POSE_YAW_DEG: float = _float(os.getenv("MAX_POSE_YAW_DEG"), 35.0)
MAX_POSE_PITCH_DEG: float = _float(os.getenv("MAX_POSE_PITCH_DEG"), 30.0)
MIN_DET_CONFIDENCE: float = _float(os.getenv("MIN_DET_CONFIDENCE"), 0.50)

# ── Face Tracking & Temporal Evidence ──────────────────────────────────────────
MAX_MISSED_FRAMES: int = _int(os.getenv("MAX_MISSED_FRAMES"), 15)
TEMPORAL_WINDOW_SIZE: int = _int(os.getenv("TEMPORAL_WINDOW_SIZE"), 5)

# ── Database ───────────────────────────────────────────────────────────────────
# Local SQLite database — completely separate from any production database.
RND_DB_PATH: str = os.getenv("RND_DB_PATH", "data/frs_rnd.db")

# ── Input ──────────────────────────────────────────────────────────────────────
# RTSP URL must be set in .env — never hardcoded.
RTSP_URL: str = os.getenv("RTSP_URL", "")

# ── R&D Logging ────────────────────────────────────────────────────────────────
RESULTS_DIR: str = os.getenv("RESULTS_DIR", "data/results")
LOG_RECOGNITION_EVENTS: bool = _bool(os.getenv("LOG_RECOGNITION_EVENTS"), True)

# ── Display ────────────────────────────────────────────────────────────────────
SHOW_SIMILARITY: bool = _bool(os.getenv("SHOW_SIMILARITY"), True)
FRAME_SKIP: int = _int(os.getenv("FRAME_SKIP"), 1)

