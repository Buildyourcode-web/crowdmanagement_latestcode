"""
camera_ai.py — Pydantic Schemas for Camera AI Profile Assignments and Capacity Preview.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CameraAIAssignmentRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    camera_id: str
    camera_code: str
    profile_id: str
    profile_name: str
    enabled: bool
    validation_status: str
    validation_message: Optional[str] = None
    workload_estimate: Optional[Dict[str, Any]] = None
    assigned_at: datetime
    assigned_by: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class CameraAIAssignRequest(BaseModel):
    profile_id: str = Field(..., example="CROWD_STANDARD")
    enabled: bool = Field(default=True)
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CameraAIValidateRequest(BaseModel):
    profile_id: str = Field(..., example="CROWD_STANDARD")
    enabled: bool = Field(default=True)


class AvailableProfileItem(BaseModel):
    profile_id: str
    name: str
    type: str
    pipeline_type: str
    compatible: bool
    compatibility_reason: Optional[str] = None
    assigned: bool
    workload: Dict[str, Any]
    gpu_requirements: Dict[str, Any]
    description: Optional[str] = None


class CameraAIConfigResponse(BaseModel):
    camera_id: str
    camera_name: str
    camera_purpose: str
    available_profiles: List[AvailableProfileItem]
    assignments: List[CameraAIAssignmentRead]
    deployment_projection: Dict[str, Any]


class CameraAIValidateResponse(BaseModel):
    camera_id: str
    profile_id: str
    compatible: bool
    compatibility_reason: Optional[str] = None
    verdict: str  # ALLOWED, WARNING, BLOCKED
    status: str   # HEALTHY, WARNING, LIMIT_REACHED, OVER_CAPACITY, GPU_UNAVAILABLE, RUNTIME_NOT_READY
    reason: str
    current_workload: Dict[str, int]
    projected_workload: Dict[str, int]
    current_utilization: Dict[str, Any]
    requested_utilization: Dict[str, Any]
    projected_utilization: Dict[str, Any]
    safe_budget: Dict[str, Any]
    hard_max_budget: Dict[str, Any]
    remaining_capacity: Dict[str, Any]
    exceeded_resources: List[str] = Field(default_factory=list)
