"""
Central models package __init__.py.
Ensures all SQLAlchemy model relationships are registered in memory.
"""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.gate import Gate
from app.models.zone import Zone
from app.models.camera import Camera
from app.models.user import User
from app.models.role import Role
from app.models.event import Event
from app.models.alert import Alert
from app.models.crowd import CrowdSnapshot
from app.models.incident import Incident
from app.models.missing_person import MissingPersonCase
from app.models.operation import PoliceUnit, MedicalUnit, EmergencyRoute
from app.models.queue import QueueSnapshot
from app.models.frs import FRSCandidate, FRSReferenceProfile, FRSReview, FRSAuditLog
from app.models.audit_log import AuditLog
from app.models.ai_capacity import AICapacitySnapshot
from app.models.ai_deployment import AIPipelineDeployment
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration
import app.models.settings

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "Gate",
    "Zone",
    "Camera",
    "CameraAIProfileAssignment",
    "CameraROIConfiguration",
    "AICapacitySnapshot",
    "AIPipelineDeployment",
    "User",
    "Role",
    "Event",
    "Alert",
    "CrowdSnapshot",
    "Incident",
    "MissingPersonCase",
    "PoliceUnit",
    "MedicalUnit",
    "EmergencyRoute",
    "QueueSnapshot",
    "FRSCandidate",
    "FRSReferenceProfile",
    "AuditLog",
]
