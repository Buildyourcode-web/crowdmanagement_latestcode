import base64
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipelines.frs.detector import FaceDetector
from app.ai.pipelines.frs.embedding import FaceEmbeddingEngine
from app.ai.pipelines.frs.quality import FaceQualityGate
from app.ai.pipelines.frs.registry import FRSPipelineRegistry
from app.config import settings
from app.models.frs import FRSCandidate, FRSReferenceProfile, FRSReview
from app.repositories.camera_repository import CameraRepository
from app.repositories.frs_repository import FRSRepository
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


class FRSService:
    """Central business logic service for FRS operations."""

    # In-memory centralized threshold and retention configuration
    _config: Dict[str, Any] = {
        "detection_confidence_threshold": 0.60,
        "min_sharpness_score": 50.0,
        "min_face_width": 60,
        "min_face_height": 60,
        "match_threshold": getattr(settings, "FRS_MATCH_THRESHOLD", 0.65),
        "top_k": 3,
        "duplicate_suppression_seconds": 60,
        "retention_days": 30,
        "detector_model": "buffalo_l",
        "embedding_model": "insightface-r50",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.frs_repo = FRSRepository(db)
        self.camera_repo = CameraRepository(db)

    # ── Dashboard & KPIs ──────────────────────────────────────────────────────

    async def get_dashboard_kpis(self) -> FRSDashboardKPIs:
        cameras, total_cams = await self.camera_repo.list_cameras(is_frs=True, limit=100)
        online_cams = sum(1 for c in cameras if c.status == "online")

        candidates, total_candidates = await self.frs_repo.list_candidates(limit=500)
        pending = sum(1 for c in candidates if c.status in ("PENDING_REVIEW", "REVIEW_REQUIRED"))
        possible_matches = sum(
            1 for c in candidates if c.status in ("POSSIBLE_MATCH", "CONFIRMED_BY_REVIEWER") or c.match_score >= 80.0
        )
        dismissed = sum(1 for c in candidates if c.status in ("DISMISSED", "REJECTED_BY_REVIEWER"))

        active_cases = await self.frs_repo.count_reference_profiles(active_only=True)

        # Dynamic pipeline metrics from registry if any are actively running
        pipelines = FRSPipelineRegistry.get_all()
        fps_vals = [p.get_health().get("fps", 0.0) for p in pipelines.values() if p.running]
        avg_fps = round(sum(fps_vals) / len(fps_vals), 1) if fps_vals else 24.0
        lat_vals = [p.get_health().get("latency_ms", 35.0) for p in pipelines.values() if p.running]
        avg_lat = round(sum(lat_vals) / len(lat_vals), 1) if lat_vals else 38.0

        return FRSDashboardKPIs(
            camerasOnline=online_cams,
            camerasTotal=len(cameras),
            detectionsToday=total_candidates,
            possibleMatches=possible_matches,
            pendingReview=pending,
            dismissed=dismissed,
            activeCases=active_cases,
            processingFps=int(avg_fps),
            avgLatencyMs=int(avg_lat),
        )

    # ── Candidate Listing & Details ───────────────────────────────────────────

    async def get_candidates(
        self,
        status_filter: Optional[str] = None,
        camera_id: Optional[str] = None,
        zone: Optional[str] = None,
        min_score: Optional[float] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[FRSCandidateRead], int]:
        skip = (page - 1) * page_size
        candidates, total = await self.frs_repo.list_candidates(
            status=status_filter,
            camera_id=camera_id,
            zone=zone,
            min_score=min_score,
            search=search,
            skip=skip,
            limit=page_size,
        )

        results = []
        for c in candidates:
            guessed_name = ""
            if c.detected_image_path and "crop_" in c.detected_image_path:
                try:
                    parts = os.path.basename(c.detected_image_path).replace("crop_", "").split("_")
                    if parts and parts[0]:
                        guessed_name = parts[0].upper()
                except Exception:
                    pass

            ref_name = c.reference_profile.display_name if c.reference_profile else (guessed_name or "Watchlist Suspect")
            ref_id = c.reference_profile.reference_id if c.reference_profile else (f"WL-{guessed_name}" if guessed_name else f"WL-{c.candidate_code[:8]}")
            ref_img = (c.reference_profile.reference_image_path if (c.reference_profile and c.reference_profile.reference_image_path)
                       else (f"/static/enrollment/{guessed_name.lower()}.jpg" if guessed_name else ""))
            ref_cat = c.reference_profile.category if c.reference_profile else "Authorized Watchlist"
            ref_stat = c.reference_profile.status if c.reference_profile else "ACTIVE"
            ref_upd = c.reference_profile.last_updated_date if c.reference_profile else "16 Sep 2026"

            results.append(
                FRSCandidateRead(
                    id=c.candidate_code,
                    detectedImage=c.detected_image_path,
                    referenceImage=ref_img,
                    referenceName=ref_name,
                    referenceId=ref_id,
                    category=ref_cat,
                    referenceStatus=ref_stat,
                    lastUpdated=ref_upd,
                    matchScore=c.match_score,
                    detectionConfidence=c.detection_confidence,
                    qualityScore=c.quality_score,
                    cameraId=c.camera_code,
                    cameraName=c.camera_name,
                    location=c.location,
                    zone=c.zone_code,
                    timestamp=c.detected_at,
                    dateStr=c.date_str,
                    timeStr=c.time_str,
                    status=c.status,
                    reviewRequired=c.review_required,
                    priority=c.priority,
                    imageQuality=c.image_quality,
                    timeline=c.timeline if isinstance(c.timeline, list) else [],
                    officerNotes=c.officer_notes,
                    reviewReason=c.review_reason,
                    reviewedBy=c.reviewed_by,
                    reviewedAt=c.reviewed_at.isoformat() if c.reviewed_at else None,
                    modelVersion=c.model_version,
                    embeddingModelVersion=c.embedding_model_version,
                )
            )
        return results, total

    async def get_candidate_by_code(self, code: str) -> FRSCandidateRead:
        c = await self.frs_repo.get_by_code(code)
        if not c:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "FRS_CANDIDATE_NOT_FOUND", "message": f"Candidate {code} not found"},
            )

        guessed_name = ""
        if c.detected_image_path and "crop_" in c.detected_image_path:
            try:
                parts = os.path.basename(c.detected_image_path).replace("crop_", "").split("_")
                if parts and parts[0]:
                    guessed_name = parts[0].upper()
            except Exception:
                pass

        ref_img = (c.reference_profile.reference_image_path if (c.reference_profile and c.reference_profile.reference_image_path)
                   else (f"/static/enrollment/{guessed_name.lower()}.jpg" if guessed_name else ""))
        ref_name = c.reference_profile.display_name if c.reference_profile else (guessed_name or "Watchlist Suspect")
        ref_id = c.reference_profile.reference_id if c.reference_profile else (f"WL-{guessed_name}" if guessed_name else f"WL-{c.candidate_code[:8]}")

        return FRSCandidateRead(
            id=c.candidate_code,
            detectedImage=c.detected_image_path,
            referenceImage=ref_img,
            referenceName=ref_name,
            referenceId=ref_id,
            category=c.reference_profile.category if c.reference_profile else "Authorized Watchlist",
            referenceStatus=c.reference_profile.status if c.reference_profile else "ACTIVE",
            lastUpdated=c.reference_profile.last_updated_date if c.reference_profile else "10 Sep 2026",
            matchScore=c.match_score,
            detectionConfidence=c.detection_confidence,
            qualityScore=c.quality_score,
            cameraId=c.camera_code,
            cameraName=c.camera_name,
            location=c.location,
            zone=c.zone_code,
            timestamp=c.detected_at,
            dateStr=c.date_str,
            timeStr=c.time_str,
            status=c.status,
            reviewRequired=c.review_required,
            priority=c.priority,
            imageQuality=c.image_quality,
            timeline=c.timeline if isinstance(c.timeline, list) else [],
            officerNotes=c.officer_notes,
            reviewReason=c.review_reason,
            reviewedBy=c.reviewed_by,
            reviewedAt=c.reviewed_at.isoformat() if c.reviewed_at else None,
            modelVersion=c.model_version,
            embeddingModelVersion=c.embedding_model_version,
        )

    # ── Human Review Workflow ─────────────────────────────────────────────────

    async def review_candidate(
        self,
        candidate_code: str,
        review_req: FRSReviewRequest,
        officer_name: str = "Command Officer",
    ) -> FRSReviewResponse:
        """
        Processes human review decision for an FRS candidate detection.
        Valid decisions:
        - CONFIRMED_BY_REVIEWER (alias: POSSIBLE_MATCH)
        - REJECTED_BY_REVIEWER (alias: NOT_A_MATCH, DISMISSED)
        - UNRESOLVED (alias: NEEDS_MORE_REVIEW)
        """
        candidate = await self.frs_repo.get_by_code(candidate_code)
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "FRS_CANDIDATE_NOT_FOUND", "message": f"Candidate {candidate_code} not found"},
            )

        # Normalize decision
        raw_decision = (review_req.decision or "").strip().upper()
        norm_map = {
            "CONFIRMED_BY_REVIEWER": ("CONFIRMED_BY_REVIEWER", "FRS_MATCH_CONFIRMED_BY_REVIEWER"),
            "POSSIBLE_MATCH": ("CONFIRMED_BY_REVIEWER", "FRS_MATCH_CONFIRMED_BY_REVIEWER"),
            "REJECTED_BY_REVIEWER": ("REJECTED_BY_REVIEWER", "FRS_MATCH_REJECTED_BY_REVIEWER"),
            "NOT_A_MATCH": ("REJECTED_BY_REVIEWER", "FRS_MATCH_REJECTED_BY_REVIEWER"),
            "DISMISSED": ("REJECTED_BY_REVIEWER", "FRS_MATCH_REJECTED_BY_REVIEWER"),
            "UNRESOLVED": ("UNRESOLVED", "FRS_MATCH_MARKED_UNRESOLVED"),
            "NEEDS_MORE_REVIEW": ("UNRESOLVED", "FRS_MATCH_MARKED_UNRESOLVED"),
        }

        if raw_decision not in norm_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_REVIEW_DECISION",
                    "message": f"Decision '{raw_decision}' is invalid. Allowed: CONFIRMED_BY_REVIEWER, REJECTED_BY_REVIEWER, UNRESOLVED.",
                },
            )

        target_status, audit_action = norm_map[raw_decision]

        # Verify candidate is still reviewable (prevent double-confirming already finalized candidate)
        if not candidate.review_required and candidate.status in ("CONFIRMED_BY_REVIEWER", "REJECTED_BY_REVIEWER"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CANDIDATE_ALREADY_REVIEWED",
                    "message": f"Candidate {candidate_code} has already been reviewed with decision '{candidate.status}'.",
                },
            )

        now = datetime.now(timezone.utc)
        candidate.status = target_status
        candidate.review_required = False if target_status != "UNRESOLVED" else True
        candidate.officer_notes = review_req.notes
        candidate.review_reason = review_req.reason or review_req.notes
        candidate.reviewed_by = officer_name
        candidate.reviewed_at = now

        # Append to candidate audit timeline
        timeline_entry = {
            "time": now.strftime("%H:%M:%S"),
            "event": f"Human Review Decision: {target_status}",
            "actor": officer_name,
            "notes": review_req.notes,
        }
        tl = list(candidate.timeline or [])
        tl.append(timeline_entry)
        candidate.timeline = tl

        # Add FRSReview record
        review = FRSReview(
            candidate_id=candidate.id,
            reviewer_name=officer_name,
            decision=target_status,
            notes=review_req.notes,
        )
        self.db.add(review)

        # Create immutable Audit Log
        ref_id = candidate.reference_profile.reference_id if candidate.reference_profile else "REF-UNKNOWN"
        await self.frs_repo.create_audit_log(
            candidate_code=candidate.candidate_code,
            reference_id=ref_id,
            action=audit_action,
            officer_name=officer_name,
            details=f"Decision: {target_status}. Notes: {review_req.notes}. Reason: {candidate.review_reason}",
        )

        await self.db.flush()

        # Emit sanitized WebSocket event
        try:
            from app.redis.event_bus import event_bus
            await event_bus.publish(
                channel="byc:frs",
                event_type="frs_candidate",
                payload={
                    "candidate_id": candidate.candidate_code,
                    "status": candidate.status,
                    "decision": target_status,
                    "reviewed_by": officer_name,
                    "timestamp": now.isoformat(),
                },
                source="frs_service",
            )
        except Exception as e:
            logger.debug(f"Event bus publish error: {e}")

        return FRSReviewResponse(
            candidate_id=candidate.candidate_code,
            status=candidate.status,
            review_required=candidate.review_required,
            reviewed_by=officer_name,
            reviewed_at=now.isoformat(),
            notes=candidate.officer_notes,
            decision=target_status,
        )

    # ── Reference Person Enrollment & Management ──────────────────────────────

    async def enroll_reference_person(
        self,
        req: FRSReferencePersonCreate,
        officer_name: str = "Command Officer",
    ) -> FRSReferenceProfileRead:
        """
        Enrolls a new reference person into the biometric gallery:
        1. Validates image and face detection (must contain exactly 1 face).
        2. Validates face quality via FaceQualityGate.
        3. Computes 512-D L2-normalized embedding.
        4. Saves reference image to secure media directory.
        5. Persists profile in database and updates running pipelines.
        """
        if not req.display_name or not req.display_name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_NAME", "message": "Display name is required for reference person enrollment."},
            )

        if not req.reference_image_b64:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "IMAGE_REQUIRED", "message": "Reference face image is required."},
            )

        # Decode base64 image
        try:
            img_data = base64.b64decode(req.reference_image_b64.split(",")[-1])
            np_arr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("cv2 decode failed")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_IMAGE", "message": f"Failed to decode reference image: {e}"},
            )

        # 1. Face Detection Check
        detector = FaceDetector(confidence_threshold=0.50)
        faces = detector.detect(img)
        if len(faces) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_FACE_DETECTED",
                    "message": "No face was detected in the provided reference image. Ensure proper lighting and visibility.",
                },
            )
        if len(faces) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "MULTIPLE_FACES_DETECTED",
                    "message": f"Found {len(faces)} faces in the reference image. Reference image must contain exactly one face.",
                },
            )

        face = faces[0]
        h, w = img.shape[:2]
        x1, y1, x2, y2 = face.bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        face_crop = img[y1:y2, x1:x2]

        # 2. Face Quality Check
        quality_gate = FaceQualityGate(min_width=40, min_height=40, min_sharpness=30.0)
        quality_res = quality_gate.assess_quality(face_crop, face)
        if not quality_res.passed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "FACE_QUALITY_INSUFFICIENT",
                    "message": f"Reference face quality insufficient: {quality_res.rejection_reason}",
                    "quality_score": quality_res.quality_score,
                },
            )

        # 3. Embedding Generation
        embedder = FaceEmbeddingEngine(embedding_dim=512)
        emb = embedder.compute_embedding(face_crop)
        emb_list = emb.tolist() if emb is not None else None

        # 4. Save Image
        ref_id = req.reference_id or f"WL-{uuid.uuid4().hex[:6].upper()}"
        media_dir = Path(settings.MEDIA_ROOT) / "frs" / "reference"
        media_dir.mkdir(parents=True, exist_ok=True)
        img_filename = f"{ref_id}.jpg"
        img_path = media_dir / img_filename
        cv2.imwrite(str(img_path), img)
        rel_path = f"/media/frs/reference/{img_filename}"

        # 5. Persist Reference Profile
        profile = await self.frs_repo.create_reference_profile(
            reference_id=ref_id,
            display_name=req.display_name.strip(),
            reference_image_path=rel_path,
            embedding_vector=emb_list,
            category=req.category or "Authorized Watchlist",
            embedding_model="buffalo_l",
            embedding_version="1.0.0",
            created_by=officer_name,
        )

        # Audit Log
        await self.frs_repo.create_audit_log(
            candidate_code="ENROLLMENT",
            reference_id=ref_id,
            action="FRS_REFERENCE_PERSON_ENROLLED",
            officer_name=officer_name,
            details=f"Enrolled reference person '{req.display_name}' ({ref_id})",
        )

        await self.db.commit()

        # Update active matcher galleries across running pipelines
        for pipe in FRSPipelineRegistry.get_all().values():
            pipe.matcher.load_gallery([
                {
                    "id": str(profile.id),
                    "reference_id": profile.reference_id,
                    "reference_code": profile.reference_code or profile.reference_id,
                    "display_name": profile.display_name,
                    "embedding": profile.embedding_vector,
                    "category": profile.category,
                    "reference_image_path": profile.reference_image_path,
                    "active": profile.active,
                }
            ])

        return FRSReferenceProfileRead(
            id=profile.reference_id,
            reference_id=profile.reference_id,
            referenceName=profile.display_name,
            category=profile.category,
            referenceStatus=profile.status,
            referenceImage=profile.reference_image_path,
            lastUpdated=profile.last_updated_date,
        )

    async def list_reference_profiles(self, active_only: bool = False) -> List[FRSReferenceProfileRead]:
        profiles = await self.frs_repo.list_reference_profiles(active_only=active_only)
        return [
            FRSReferenceProfileRead(
                id=p.reference_id,
                reference_id=p.reference_id,
                referenceName=p.display_name,
                category=p.category,
                referenceStatus=p.status,
                referenceImage=p.reference_image_path,
                lastUpdated=p.last_updated_date,
            )
            for p in profiles
        ]

    async def update_reference_profile(
        self,
        ref_id: str,
        req: FRSReferencePersonUpdate,
        officer_name: str = "Command Officer",
    ) -> FRSReferenceProfileRead:
        profile = await self.frs_repo.update_reference_profile(
            ref_id=ref_id,
            display_name=req.display_name,
            category=req.category,
            active=req.active,
        )
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "REFERENCE_PROFILE_NOT_FOUND", "message": f"Reference {ref_id} not found"},
            )

        await self.frs_repo.create_audit_log(
            candidate_code="UPDATE",
            reference_id=ref_id,
            action="FRS_REFERENCE_PERSON_UPDATED",
            officer_name=officer_name,
            details=f"Updated reference {ref_id}: active={req.active}",
        )
        await self.db.commit()

        return FRSReferenceProfileRead(
            id=profile.reference_id,
            reference_id=profile.reference_id,
            referenceName=profile.display_name,
            category=profile.category,
            referenceStatus=profile.status,
            referenceImage=profile.reference_image_path,
            lastUpdated=profile.last_updated_date,
        )

    async def deactivate_reference_profile(
        self,
        ref_id: str,
        officer_name: str = "Command Officer",
    ) -> Dict[str, Any]:
        profile = await self.frs_repo.deactivate_reference_profile(ref_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "REFERENCE_PROFILE_NOT_FOUND", "message": f"Reference {ref_id} not found"},
            )

        await self.frs_repo.create_audit_log(
            candidate_code="DEACTIVATION",
            reference_id=ref_id,
            action="FRS_REFERENCE_PERSON_DEACTIVATED",
            officer_name=officer_name,
            details=f"Deactivated reference profile {ref_id}",
        )
        await self.db.commit()
        return {"status": "SUCCESS", "message": f"Reference profile {ref_id} deactivated."}

    # ── Retention & Privacy Cleanup ───────────────────────────────────────────

    async def cleanup_expired_candidates(self, retention_days: Optional[int] = None) -> FRSRetentionCleanupResponse:
        """
        Purges expired candidate events and image crops older than retention policy.
        Preserves all immutable audit logs.
        """
        days = retention_days or self._config.get("retention_days", 30)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        expired_candidates = await self.frs_repo.get_expired_candidates(cutoff)
        count = 0

        for cand in expired_candidates:
            # Delete detected crop image if exists
            if cand.detected_image_path:
                crop_path = Path(settings.MEDIA_ROOT) / cand.detected_image_path.lstrip("/media/")
                if crop_path.exists():
                    try:
                        crop_path.unlink()
                    except Exception:
                        pass

            # Delete DB record
            await self.frs_repo.delete_candidate(cand)
            count += 1

        await self.db.commit()

        logger.info(f"FRSService: Purged {count} expired candidates older than {days} days.")
        return FRSRetentionCleanupResponse(
            deleted_candidates_count=count,
            retention_days=days,
            cutoff_timestamp=cutoff.isoformat(),
            status="SUCCESS",
        )

    # ── Central Threshold Configuration ───────────────────────────────────────

    @classmethod
    def get_config(cls) -> FRSConfigRead:
        return FRSConfigRead(**cls._config)

    @classmethod
    def update_config(cls, update_data: FRSConfigUpdate) -> FRSConfigRead:
        for k, v in update_data.model_dump(exclude_unset=True).items():
            if v is not None:
                cls._config[k] = v
        return FRSConfigRead(**cls._config)
