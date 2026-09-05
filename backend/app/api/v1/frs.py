from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipelines.frs.registry import FRSPipelineRegistry
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.camera import CameraRead
from app.schemas.common import StandardResponse
from app.schemas.frs import (
    FRSCandidateRead,
    FRSConfigRead,
    FRSConfigUpdate,
    FRSDashboardKPIs,
    FRSReferencePersonCreate,
    FRSReferencePersonUpdate,
    FRSReferenceProfileRead,
    FRSRetentionCleanupResponse,
    FRSReviewRequest,
    FRSReviewResponse,
)
from app.repositories.frs_repository import FRSRepository
from app.security.permissions import Permissions
from app.services.camera_service import CameraService
from app.services.frs_service import FRSService
from app.utils.response import ResponseMeta, success_response

router = APIRouter(prefix="/frs", tags=["FRS (Facial Recognition System)"])


# ── Operational Status & Health ───────────────────────────────────────────────

@router.get("/status", response_model=StandardResponse[Dict[str, Any]])
async def get_frs_fleet_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve fleet status of all registered FRS pipelines."""
    pipelines = FRSPipelineRegistry.get_all()
    statuses = [p.get_status() for p in pipelines.values()]
    return success_response({
        "total_frs_pipelines": len(pipelines),
        "running_count": sum(1 for s in statuses if s.get("running")),
        "pipelines": statuses,
    })


@router.get("/health", response_model=StandardResponse[Dict[str, Any]])
async def get_frs_fleet_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve operational health metrics for active FRS pipelines."""
    pipelines = FRSPipelineRegistry.get_all()
    health_reports = {code: p.get_health() for code, p in pipelines.items()}
    return success_response({
        "pipelines": health_reports,
        "healthy_count": sum(1 for h in health_reports.values() if h.get("status") == "HEALTHY"),
        "degraded_count": sum(1 for h in health_reports.values() if h.get("status") == "DEGRADED"),
        "failed_count": sum(1 for h in health_reports.values() if h.get("status") == "FAILED"),
    })


@router.get("/dashboard", response_model=StandardResponse[FRSDashboardKPIs])
async def get_frs_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve FRS operational dashboard KPIs (authorized access only)."""
    service = FRSService(db)
    kpis = await service.get_dashboard_kpis()
    return success_response(kpis)


@router.get("/cameras", response_model=StandardResponse[List[CameraRead]])
async def get_frs_cameras(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve dedicated 16-channel FRS cameras."""
    cam_service = CameraService(db)
    cameras, total = await cam_service.get_cameras(is_frs=True, page_size=100)
    return success_response(cameras)


# ── Candidate Listing & Review ────────────────────────────────────────────────

@router.get("/candidates", response_model=StandardResponse[List[FRSCandidateRead]])
async def list_frs_candidates(
    status: Optional[str] = Query(None, description="REVIEW_REQUIRED, CONFIRMED_BY_REVIEWER, REJECTED_BY_REVIEWER, UNRESOLVED"),
    camera: Optional[str] = Query(None, description="Filter by camera code e.g. FRS-KHB-007"),
    zone: Optional[str] = Query(None, description="Filter by zone code"),
    min_score: Optional[float] = Query(None, description="Minimum match score threshold (e.g. 75.0)"),
    search: Optional[str] = Query(None, description="Search candidate code or location"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """List live candidate detections requiring human review."""
    service = FRSService(db)
    candidates, total = await service.get_candidates(
        status_filter=status,
        camera_id=camera,
        zone=zone,
        min_score=min_score,
        search=search,
        page=page,
        page_size=page_size,
    )
    meta = ResponseMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size if page_size > 0 else 1,
    )
    return success_response(candidates, meta=meta)


@router.get("/candidates/{id}", response_model=StandardResponse[FRSCandidateRead])
async def get_candidate_detail(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve full side-by-side details and audit trail for a candidate detection."""
    service = FRSService(db)
    candidate = await service.get_candidate_by_code(id)
    return success_response(candidate)


@router.post("/candidates/{id}/review", response_model=StandardResponse[FRSReviewResponse])
async def review_frs_candidate(
    id: str,
    review_data: FRSReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_REVIEW)),
):
    """
    Record an authorized human review decision for an FRS candidate detection.
    Enforces audit logging. Never confirms identity automatically.
    """
    service = FRSService(db)
    officer_name = current_user.full_name or current_user.username
    review_result = await service.review_candidate(id, review_data, officer_name=officer_name)
    return success_response(review_result)


@router.get("/history", response_model=StandardResponse[List[FRSCandidateRead]])
async def get_frs_history(
    status: Optional[str] = Query(None),
    camera: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Searchable historical audit log of all candidate detections and reviews."""
    service = FRSService(db)
    candidates, total = await service.get_candidates(
        status_filter=status,
        camera_id=camera,
        zone=zone,
        min_score=min_score,
        search=search,
        page=page,
        page_size=page_size,
    )
    meta = ResponseMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size if page_size > 0 else 1,
    )
    return success_response(candidates, meta=meta)


# ── Reference Persons Enrollment & Management ─────────────────────────────────

@router.post("/reference-persons", response_model=StandardResponse[FRSReferenceProfileRead], status_code=status.HTTP_201_CREATED)
async def enroll_reference_person(
    req: FRSReferencePersonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_MANAGE)),
):
    """
    Enroll an authorized reference person into the biometric gallery (FRS_MANAGE required).
    Validates face presence, enforces quality gate, and generates 512-D embedding.
    """
    service = FRSService(db)
    officer_name = current_user.full_name or current_user.username
    profile = await service.enroll_reference_person(req, officer_name=officer_name)
    return success_response(profile)


@router.get("/reference-persons", response_model=StandardResponse[List[FRSReferenceProfileRead]])
async def list_reference_persons(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve list of authorized reference profiles without exposing raw embeddings."""
    service = FRSService(db)
    profiles = await service.list_reference_profiles(active_only=active_only)
    return success_response(profiles)


@router.patch("/reference-persons/{id}", response_model=StandardResponse[FRSReferenceProfileRead])
async def update_reference_person(
    id: str,
    req: FRSReferencePersonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_MANAGE)),
):
    """Update reference person information or active status."""
    service = FRSService(db)
    officer_name = current_user.full_name or current_user.username
    updated = await service.update_reference_profile(id, req, officer_name=officer_name)
    return success_response(updated)


@router.delete("/reference-persons/{id}", response_model=StandardResponse[Dict[str, Any]])
async def deactivate_reference_person(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_MANAGE)),
):
    """Deactivate a reference person profile from active gallery search."""
    service = FRSService(db)
    officer_name = current_user.full_name or current_user.username
    res = await service.deactivate_reference_profile(id, officer_name=officer_name)
    return success_response(res)


# Backward compatibility alias
@router.get("/reference-profiles", response_model=StandardResponse[List[FRSReferenceProfileRead]])
async def list_reference_profiles_alias(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Alias for /reference-persons."""
    service = FRSService(db)
    profiles = await service.list_reference_profiles()
    return success_response(profiles)


# ── Retention & Threshold Configuration ───────────────────────────────────────

@router.post("/retention/cleanup", response_model=StandardResponse[FRSRetentionCleanupResponse])
async def cleanup_expired_retention(
    retention_days: Optional[int] = Query(None, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_MANAGE)),
):
    """Purge expired candidate records and face image crops older than retention policy."""
    service = FRSService(db)
    res = await service.cleanup_expired_candidates(retention_days=retention_days)
    return success_response(res)


@router.get("/config", response_model=StandardResponse[FRSConfigRead])
async def get_frs_config(
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve active central biometric, match, and retention thresholds."""
    config = FRSService.get_config()
    return success_response(config)


@router.put("/config", response_model=StandardResponse[FRSConfigRead])
async def update_frs_config(
    update_data: FRSConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_MANAGE)),
):
    """Update central biometric, match, and retention thresholds (FRS_MANAGE required)."""
    updated_cfg = FRSService.update_config(update_data)
    # Log configuration change
    repo = FRSRepository(db)
    await repo.create_audit_log(
        candidate_code="CONFIG",
        reference_id="CENTRAL_CONFIG",
        action="FRS_CONFIG_UPDATED",
        officer_name=current_user.full_name or current_user.username,
        details=f"Updated config: {update_data.model_dump(exclude_unset=True)}",
    )
    await db.commit()
    return success_response(updated_cfg)


@router.get("/cameras/{id}/events", response_model=StandardResponse[List[dict]])
async def get_frs_camera_events(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_READ)),
):
    """Retrieve candidate match events detected on a specific FRS camera."""
    service = FRSService(db)
    candidates, total = await service.get_candidates(camera_id=id, page_size=20)
    events = [
        {
            "id": c.id,
            "candidate_code": c.id,
            "match_score": c.match_score,
            "status": c.status,
            "timestamp": c.timestamp.isoformat(),
            "reference_name": c.reference_name,
        }
        for c in candidates
    ]
    return success_response(events)
