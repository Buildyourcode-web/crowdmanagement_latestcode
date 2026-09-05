"""
__init__.py — Face tracking package.
"""
try:
    from app.frs_engine.tracking.tracker import FaceTracker, TrackState
except ImportError:
    from app.tracking.tracker import FaceTracker, TrackState

__all__ = ["FaceTracker", "TrackState"]
