# Base metadata collector for Alembic migrations
from app.models.base import Base
from app.models.role import Role, Permission, role_permissions
from app.models.user import User
from app.models.event import Event
from app.models.zone import Zone
from app.models.camera import Camera
from app.models.gate import Gate
from app.models.crowd import CrowdSnapshot
from app.models.queue import QueueSnapshot
from app.models.frs import FRSReferenceProfile, FRSCandidate, FRSReview, FRSAuditLog
from app.models.missing_person import MissingPersonCase
from app.models.alert import Alert
from app.models.incident import Incident, IncidentNote
from app.models.operation import PoliceUnit, MedicalUnit, EmergencyRoute
from app.models.audit_log import AuditLog
from app.models.ai_capacity import AICapacitySnapshot
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration
from app.models.ai_deployment import AIPipelineDeployment
from app.models.settings import (
    AlertThresholdConfig,
    AIConfigSettings,
    FRSConfigSettings,
    NotificationConfig,
    SystemConfig,
)

__all__ = [
    "Base",
    "Role",
    "Permission",
    "role_permissions",
    "User",
    "Event",
    "Zone",
    "Camera",
    "Gate",
    "CrowdSnapshot",
    "QueueSnapshot",
    "FRSReferenceProfile",
    "FRSCandidate",
    "FRSReview",
    "FRSAuditLog",
    "MissingPersonCase",
    "Alert",
    "Incident",
    "IncidentNote",
    "PoliceUnit",
    "MedicalUnit",
    "EmergencyRoute",
    "AuditLog",
    "AICapacitySnapshot",
    "CameraAIProfileAssignment",
    "CameraROIConfiguration",
    "AIPipelineDeployment",
    # Settings
    "AlertThresholdConfig",
    "AIConfigSettings",
    "FRSConfigSettings",
    "NotificationConfig",
    "SystemConfig",
]
