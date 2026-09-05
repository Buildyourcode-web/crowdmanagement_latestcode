"""
state.py — Central AI Pipeline State Model.

Unified lifecycle states for Crowd, Queue, and FRS AI inference pipelines.
"""

from enum import Enum


class PipelineState(str, Enum):
    """
    Standard state machine for all AI inference pipelines in BYC AI C&C Platform.
    Shared across Crowd AI, Queue AI, and FRS AI pipelines.
    """
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    RESTARTING = "RESTARTING"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def is_active(cls, state: "PipelineState") -> bool:
        """Returns True if the state indicates an active or transitioning pipeline."""
        return state in {cls.STARTING, cls.RUNNING, cls.DEGRADED, cls.RESTARTING}

    @classmethod
    def is_terminal(cls, state: "PipelineState") -> bool:
        """Returns True if the pipeline has reached an inactive or faulted terminal state."""
        return state in {cls.STOPPED, cls.FAILED}
