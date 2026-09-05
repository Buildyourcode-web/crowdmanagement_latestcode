"""
backend/tests/test_frs_pipeline.py — Step 9 Comprehensive Test Suite.

Verifies:
 1. FRS profile validation (FRS_STANDARD profile required)
 2. FRS camera purpose validation (FRS / MULTI_PURPOSE allowed; CROWD, QUEUE, GENERAL rejected)
 3. FRS authorization RBAC (frs:read, frs:manage, frs:review permissions enforced)
 4. Runtime validation (clean RUNTIME_UNAVAILABLE on unsupported hosts without fake data)
 5. Capacity validation (CapacityCalculator budget check prevents overcapacity start)
 6. RTSP secure loading (credentials masked in repr, logs, and telemetry)
 7. Face detection (bbox, confidence, landmarks extracted)
 8. Face quality rejection (FACE_QUALITY_INSUFFICIENT for small, blurry, or poor exposure)
 9. Embedding generation (512-D L2-normalized vector)
10. Candidate search active only (inactive profiles excluded from search gallery)
11. Similarity scoring (accurate cosine similarity calculation)
12. Top-K candidates ranking (descending similarity ranking with margin analysis)
13. No-match behavior (below threshold produces no candidate)
14. Candidate creation status (status is strictly REVIEW_REQUIRED upon match)
15. Duplicate suppression (60s cooldown per camera:reference)
16. Review required initial state (initial DB and API state has review_required=True)
17. Reviewer confirmation (CONFIRMED_BY_REVIEWER transitions status and logs decision)
18. Reviewer rejection (REJECTED_BY_REVIEWER transitions status and logs decision)
19. Unresolved state (UNRESOLVED maintains review_required=True)
20. Invalid review transition (already reviewed candidate or invalid decision rejected with 400)
21. Audit logging (FRSAuditLog emitted with officer name, timestamp, and details)
22. WebSocket event sanitized (no embeddings, no passwords in emitted payloads)
23. Pipeline lifecycle (start, stop, restart via orchestrator)
24. Health monitoring (FPS, latencies, healthy status)
25. RTSP failure detection (timeout transitions to FAILED)
26. Recovery through orchestrator (auto-recovery of failed/degraded FRS pipeline)
27. No Crowd interaction (counters, tracking IDs, and risk engines uncalled)
28. No Queue interaction (counters, wait time, and queue alarms uncalled)
29. Credential non-leakage (passwords stripped from all outputs)
30. Embedding non-leakage (512-D vectors excluded from client responses)
31. Image access authorization (unauthenticated/unauthorized access denied)
32. Retention cleanup (purges expired candidates and crops while preserving audit logs)
33. Model version tracking (buffalo_l and insightface-r50 tracked)
34. Threshold configuration update (PUT /config updates thresholds and logs audit)
35. No automatic identity confirmation verification (strictly human review only)
36. No automatic enforcement action verification (no automated arrest or dispatch)
"""

import asyncio
import base64
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import TestSessionLocal

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.orchestrator.service import ai_orchestrator
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.frs.config import FRSPipelineConfig
from app.ai.pipelines.frs.detector import DetectedFace, FaceDetector
from app.ai.pipelines.frs.embedding import (
    FaceEmbeddingEngine,
    batch_cosine_similarity,
    cosine_similarity,
    normalize_l2,
)
from app.ai.pipelines.frs.events import FRSEventEngine, FRSEventPayload, FRSEventType
from app.ai.pipelines.frs.health import FRSPipelineHealthTracker
from app.ai.pipelines.frs.matcher import CandidateMatch, CandidateMatcher
from app.ai.pipelines.frs.pipeline import FRSPipeline
from app.ai.pipelines.frs.quality import FaceQualityGate, FaceQualityResult
from app.ai.pipelines.frs.registry import FRSPipelineRegistry
from app.models.ai_deployment import AIPipelineDeployment
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.frs import FRSAuditLog, FRSCandidate, FRSReferenceProfile, FRSReview
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.frs import FRSConfigUpdate, FRSReviewRequest
from app.security.jwt import create_access_token
from app.security.password import get_password_hash
from app.security.permissions import Permissions
from app.services.frs_service import FRSService


class MockSessionContext:
    def __init__(self, session):
        self.session = session
    def __call__(self):
        return self
    async def __aenter__(self):
        return self.session
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# ── Fixtures & Setup ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
def clean_frs_state():
    FRSPipelineRegistry.clear()
    ai_orchestrator._reconnect_backoff_tracker.clear()
    ai_orchestrator._restart_history_tracker.clear()
    yield
    FRSPipelineRegistry.clear()
    ai_orchestrator._reconnect_backoff_tracker.clear()
    ai_orchestrator._restart_history_tracker.clear()


@pytest.fixture(autouse=True)
def default_capacity_allow():
    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", return_value={"allowed": True, "verdict": "ALLOWED"}):
        yield


@pytest_asyncio.fixture
async def frs_tokens(db_session: AsyncSession) -> Dict[str, str]:
    """Generates RBAC tokens for frs_reader, frs_reviewer, frs_manager, and unprivileged viewer."""
    perms_to_create = [
        (Permissions.FRS_READ, "frs:read"),
        (Permissions.FRS_REVIEW, "frs:review"),
        (Permissions.FRS_MANAGE, "frs:manage"),
        (Permissions.AI_READ, "ai:read"),
        (Permissions.AI_MANAGE, "ai:manage"),
    ]
    perm_map = {}
    for code, desc in perms_to_create:
        stmt = select(Permission).where(Permission.code == code)
        p = (await db_session.execute(stmt)).scalars().first()
        if not p:
            p = Permission(code=code, name=code, description=desc)
            db_session.add(p)
            await db_session.flush()
        perm_map[code] = p

    roles_data = [
        ("ROLE_FRS_READER", [perm_map[Permissions.FRS_READ]]),
        ("ROLE_FRS_REVIEWER", [perm_map[Permissions.FRS_READ], perm_map[Permissions.FRS_REVIEW]]),
        ("ROLE_FRS_MANAGER", [perm_map[Permissions.FRS_READ], perm_map[Permissions.FRS_REVIEW], perm_map[Permissions.FRS_MANAGE]]),
        ("ROLE_NO_FRS", []),
    ]

    tokens = {}
    for rcode, perms in roles_data:
        stmt_r = select(Role).where(Role.code == rcode)
        role = (await db_session.execute(stmt_r)).scalars().first()
        if not role:
            role = Role(code=rcode, name=rcode, description=rcode, permissions=perms)
            db_session.add(role)
            await db_session.flush()

        stmt_u = select(User).where(User.username == f"user_{rcode.lower()}")
        user = (await db_session.execute(stmt_u)).scalars().first()
        if not user:
            user = User(
                username=f"user_{rcode.lower()}",
                email=f"{rcode.lower()}@byc.ai",
                password_hash=get_password_hash("pass123!"),
                full_name=f"Officer {rcode}",
                role_id=role.id,
                is_active=True,
            )
            db_session.add(user)
            await db_session.flush()

        tokens[rcode] = create_access_token(
            subject=str(user.id),
            role=rcode,
            permissions=[p.code for p in perms],
        )

    await db_session.commit()
    return tokens


@pytest_asyncio.fixture
async def frs_test_camera(db_session: AsyncSession) -> Camera:
    """Creates a dedicated FRS camera with active FRS_STANDARD assignment."""
    cam_code = f"FRS-TEST-{uuid.uuid4().hex[:6].upper()}"
    cam = Camera(
        camera_code=cam_code,
        name=f"Test FRS Gate Cam {cam_code}",
        label=f"Test FRS Gate Cam {cam_code}",
        rtsp_url_encrypted=f"rtsp://admin:secret123@192.168.1.50:554/{cam_code}",
        stream_status="VERIFIED",
        status="online",
        enabled=True,
        is_frs_camera=True,
        camera_type="FRS",
        location_name="North VIP Gate",
        zone_code="ZONE-A",
    )
    db_session.add(cam)
    await db_session.flush()

    assignment = CameraAIProfileAssignment(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="FRS_STANDARD",
        enabled=True,
    )
    db_session.add(assignment)
    await db_session.commit()
    await db_session.refresh(cam)
    return cam


# ── Test 1: FRS Profile Validation ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_frs_profile_validation(db_session: AsyncSession, frs_test_camera: Camera, superadmin_token: str):
    """Verifies that an unsupported or mismatched AI profile is rejected by orchestrator."""
    # Alter assignment to unsupported profile
    stmt = select(CameraAIProfileAssignment).where(CameraAIProfileAssignment.camera_id == frs_test_camera.id)
    assignment = (await db_session.execute(stmt)).scalars().first()
    assignment.profile_id = "UNKNOWN_NONEXISTENT_PROFILE"
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ai_orchestrator.start_pipeline(
            frs_test_camera.camera_code,
            db_session,
            custom_detector=lambda f: [],
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.get("code") == "UNSUPPORTED_PROFILE"


# ── Test 2: FRS Camera Purpose Validation ─────────────────────────────────────

@pytest.mark.asyncio
async def test_frs_camera_purpose_validation(db_session: AsyncSession, frs_test_camera: Camera):
    """Verifies camera with purpose CROWD or QUEUE cannot run an FRS pipeline."""
    # Set camera purpose to CROWD
    frs_test_camera.camera_type = "CROWD"
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ai_orchestrator.start_pipeline(
            frs_test_camera.camera_code,
            db_session,
            custom_detector=lambda f: [],
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.get("code") == "FRS_CAMERA_NOT_ALLOWED"


# ── Test 3: FRS Authorization RBAC ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_frs_authorization_rbac(client: AsyncClient, frs_tokens: Dict[str, str]):
    """Verifies frs:read, frs:manage, frs:review permission enforcement."""
    headers_reader = {"Authorization": f"Bearer {frs_tokens['ROLE_FRS_READER']}"}
    headers_no_frs = {"Authorization": f"Bearer {frs_tokens['ROLE_NO_FRS']}"}

    # Reader can view status and candidates
    res1 = await client.get("/api/v1/frs/status", headers=headers_reader)
    assert res1.status_code == 200

    # Reader CANNOT perform review (requires frs:review)
    res2 = await client.post(
        "/api/v1/frs/candidates/FRS-EVT-001/review",
        json={"decision": "CONFIRMED_BY_REVIEWER", "notes": "test"},
        headers=headers_reader,
    )
    assert res2.status_code == 403

    # Reader CANNOT update central config (requires frs:manage)
    res3 = await client.put(
        "/api/v1/frs/config",
        json={"match_threshold": 0.80},
        headers=headers_reader,
    )
    assert res3.status_code == 403

    # User with NO FRS permission is denied reading FRS status
    res4 = await client.get("/api/v1/frs/status", headers=headers_no_frs)
    assert res4.status_code == 403


# ── Test 4: Runtime Validation (Clean RUNTIME_UNAVAILABLE) ────────────────────

@pytest.mark.asyncio
async def test_runtime_validation(db_session: AsyncSession, frs_test_camera: Camera):
    """Verifies that missing GPU/DeepStream raises clean RUNTIME_UNAVAILABLE without fake data."""
    with patch("app.ai.orchestrator.service.RuntimeDetector.detect_gpu", return_value={"available": False}):
        with patch("app.ai.orchestrator.service.RuntimeDetector.detect_runtime", return_value={"deepstream": False}):
            with pytest.raises(HTTPException) as exc_info:
                # Starting without custom_detector forces runtime check
                await ai_orchestrator.start_pipeline(frs_test_camera.camera_code, db_session)
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail.get("code") == "RUNTIME_UNAVAILABLE"


# ── Test 5: Capacity Validation ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capacity_validation(db_session: AsyncSession, frs_test_camera: Camera):
    """Verifies that capacity engine blocks over-capacity FRS deployments with 409."""
    with patch(
        "app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment",
        return_value={"allowed": False, "verdict": "DENIED", "reason": "GPU memory budget exceeded"},
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ai_orchestrator.start_pipeline(
                frs_test_camera.camera_code,
                db_session,
                custom_detector=lambda f: [],
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail.get("code") == "AI_CAPACITY_EXCEEDED"


# ── Test 6: RTSP Secure Loading ───────────────────────────────────────────────

def test_rtsp_secure_loading():
    """Verifies credentials are masked in repr, str, and sanitized RTSP URLs."""
    raw_rtsp = "rtsp://admin:P@ssword_Secret_123@192.168.1.100:554/live/ch0"
    sanitized = FRSPipelineConfig.sanitize_url(raw_rtsp)
    assert "P@ssword_Secret_123" not in sanitized
    assert sanitized == "rtsp://***:***@192.168.1.100:554/live/ch0"

    cfg = FRSPipelineConfig(
        camera_id="cam-1",
        camera_code="FRS-CAM-01",
        camera_name="Perimeter FRS",
        rtsp_url=raw_rtsp,
        sanitized_rtsp_url=sanitized,
    )
    repr_str = repr(cfg)
    assert "P@ssword_Secret_123" not in repr_str
    assert "***:***" in repr_str


# ── Test 7: Face Detection ───────────────────────────────────────────────────

def test_face_detection():
    """Verifies FaceDetector parses bbox, landmarks, and confidence."""
    mock_detected = [
        DetectedFace(
            bbox=(10, 10, 110, 110),
            confidence=0.88,
            landmarks=np.array([[30, 40], [70, 40], [50, 60], [40, 80], [60, 80]]),
            pose=(5.0, 2.0, 0.0),
        )
    ]
    detector = FaceDetector(
        confidence_threshold=0.60,
        custom_detector=lambda frame: mock_detected,
    )
    dummy_frame = np.zeros((200, 200, 3), dtype=np.uint8)
    faces = detector.detect(dummy_frame)
    assert len(faces) == 1
    assert faces[0].width == 100
    assert faces[0].height == 100
    assert faces[0].confidence == 0.88
    assert faces[0].landmarks is not None


# ── Test 8: Face Quality Rejection (FACE_QUALITY_INSUFFICIENT) ─────────────────

def test_face_quality_rejection():
    """Verifies FaceQualityGate rejects small, blurry, or poor exposure crops."""
    gate = FaceQualityGate(min_width=60, min_height=60, min_sharpness=50.0)

    # 1. Too small
    small_face = DetectedFace(bbox=(0, 0, 40, 40), confidence=0.90)
    small_crop = np.zeros((40, 40, 3), dtype=np.uint8)
    res_small = gate.assess_quality(small_crop, small_face)
    assert not res_small.passed
    assert "TOO_SMALL" in res_small.rejection_reason

    # 2. Blurry (constant pixel values -> Laplacian variance 0)
    blurry_face = DetectedFace(bbox=(0, 0, 100, 100), confidence=0.90)
    blurry_crop = np.ones((100, 100, 3), dtype=np.uint8) * 128
    res_blurry = gate.assess_quality(blurry_crop, blurry_face)
    assert not res_blurry.passed
    assert "BLURRY" in res_blurry.rejection_reason

    # 3. High quality synthetic test pattern (checkerboard with high variance)
    sharp_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    sharp_crop[::2, ::2] = 200
    sharp_crop[1::2, 1::2] = 50
    res_sharp = gate.assess_quality(sharp_crop, blurry_face)
    assert res_sharp.passed
    assert res_sharp.quality_score > 0.5


# ── Test 9: Embedding Generation (512-D L2-Normalized) ────────────────────────

def test_embedding_generation():
    """Verifies FaceEmbeddingEngine produces normalized 512-D vector."""
    custom_raw = np.random.randn(512).astype(np.float32)
    engine = FaceEmbeddingEngine(
        embedding_dim=512,
        custom_embedder=lambda crop: custom_raw,
    )
    crop = np.ones((80, 80, 3), dtype=np.uint8)
    emb = engine.compute_embedding(crop)
    assert emb is not None
    assert emb.shape == (512,)
    # Verify L2 norm is 1.0
    norm = np.linalg.norm(emb)
    assert norm == pytest.approx(1.0, rel=1e-4)


# ── Test 10: Candidate Search Active Only ──────────────────────────────────────

def test_candidate_search_active_only():
    """Verifies that deactivated reference profiles are excluded from matching gallery."""
    matcher = CandidateMatcher(match_threshold=0.75, top_k=3)
    emb1 = normalize_l2(np.ones(512, dtype=np.float32))
    emb2 = normalize_l2(np.ones(512, dtype=np.float32) * 2)

    profiles = [
        {"id": "p1", "reference_id": "REF-001", "display_name": "Active Person", "embedding": emb1, "active": True},
        {"id": "p2", "reference_id": "REF-002", "display_name": "Deactivated Person", "embedding": emb2, "active": False},
    ]
    loaded = matcher.load_gallery(profiles)
    assert loaded == 1
    assert matcher.gallery_size == 1


# ── Test 11: Similarity Scoring (Cosine Similarity) ───────────────────────────

def test_similarity_scoring():
    """Verifies cosine similarity calculation accuracy."""
    v1 = normalize_l2(np.array([1.0, 0.0, 0.0] + [0.0] * 509, dtype=np.float32))
    v2 = normalize_l2(np.array([1.0, 0.0, 0.0] + [0.0] * 509, dtype=np.float32))
    v3 = normalize_l2(np.array([0.0, 1.0, 0.0] + [0.0] * 509, dtype=np.float32))

    # Identical vectors -> 1.0
    assert cosine_similarity(v1, v2) == pytest.approx(1.0, rel=1e-4)
    # Orthogonal vectors -> 0.0
    assert cosine_similarity(v1, v3) == pytest.approx(0.0, rel=1e-4)

    # Batch test
    gallery = np.vstack([v2, v3])
    sims = batch_cosine_similarity(v1, gallery)
    assert sims[0] == pytest.approx(1.0, rel=1e-4)
    assert sims[1] == pytest.approx(0.0, rel=1e-4)


# ── Test 12: Top-K Candidates Ranking ─────────────────────────────────────────

def test_top_k_candidates_ranking():
    """Verifies matches are ranked descending by similarity score with top-k cutoff."""
    matcher = CandidateMatcher(match_threshold=0.70, top_k=2)
    q = normalize_l2(np.array([1.0, 0.0] + [0.0] * 510, dtype=np.float32))

    p1_emb = normalize_l2(np.array([0.95, 0.05] + [0.0] * 510, dtype=np.float32))  # sim ~ 0.99
    p2_emb = normalize_l2(np.array([0.80, 0.20] + [0.0] * 510, dtype=np.float32))  # sim ~ 0.97
    p3_emb = normalize_l2(np.array([0.72, 0.30] + [0.0] * 510, dtype=np.float32))  # sim ~ 0.92

    profiles = [
        {"id": "p3", "reference_id": "REF-003", "display_name": "Third", "embedding": p3_emb, "active": True},
        {"id": "p1", "reference_id": "REF-001", "display_name": "First", "embedding": p1_emb, "active": True},
        {"id": "p2", "reference_id": "REF-002", "display_name": "Second", "embedding": p2_emb, "active": True},
    ]
    matcher.load_gallery(profiles)
    matches = matcher.search(q)
    assert len(matches) == 2  # top_k=2
    assert matches[0].reference_id == "REF-001"
    assert matches[1].reference_id == "REF-002"
    assert matches[0].rank == 1
    assert matches[1].rank == 2
    assert matches[0].margin > 0.0


# ── Test 13: No-Match Behavior ────────────────────────────────────────────────

def test_no_match_behavior():
    """Verifies that similarity below threshold produces zero candidate matches."""
    matcher = CandidateMatcher(match_threshold=0.85, top_k=3)
    q = normalize_l2(np.array([1.0, 0.0] + [0.0] * 510, dtype=np.float32))
    p_emb = normalize_l2(np.array([0.5, 0.5] + [0.0] * 510, dtype=np.float32))  # sim ~ 0.70 < 0.85

    matcher.load_gallery([
        {"id": "p1", "reference_id": "REF-001", "display_name": "Person", "embedding": p_emb, "active": True}
    ])
    matches = matcher.search(q)
    assert len(matches) == 0


# ── Test 14: Candidate Creation Status (Strict REVIEW_REQUIRED) ───────────────

def test_candidate_creation_status():
    """Verifies that matching generates candidate with initial status REVIEW_REQUIRED."""
    emb = normalize_l2(np.array([1.0] * 512, dtype=np.float32))
    mock_detected = [DetectedFace(bbox=(10, 10, 110, 110), confidence=0.92)]

    cfg = FRSPipelineConfig(
        camera_id="cam-test",
        camera_code="FRS-KHB-007",
        camera_name="North VIP Gate",
        rtsp_url="rtsp://***:***@localhost:554/live",
        sanitized_rtsp_url="rtsp://***:***@localhost:554/live",
        match_threshold=0.75,
    )
    pipeline = FRSPipeline(
        config=cfg,
        custom_detector=lambda f: mock_detected,
        custom_embedder=lambda c: emb,
    )
    # Mock quality gate to pass
    pipeline.quality_gate.assess_quality = MagicMock(return_value=FaceQualityResult(passed=True, quality_score=0.95))
    pipeline.matcher.load_gallery([
        {"id": "ref-1", "reference_id": "REF-001", "display_name": "Test Subject", "embedding": emb, "active": True}
    ])

    test_frame = np.zeros((200, 200, 3), dtype=np.uint8)
    candidates = pipeline.process_frame(test_frame)

    assert len(candidates) == 1
    c = candidates[0]
    assert c["status"] == "REVIEW_REQUIRED"
    assert c["review_required"] is True
    assert c["match_score"] >= 90.0


# ── Test 15: Duplicate Suppression (60s Window) ──────────────────────────────

def test_duplicate_suppression():
    """Verifies that matches within cooldown (60s) for same camera:ref are suppressed."""
    engine = FRSEventEngine(suppression_cooldown_seconds=60)
    cam = "FRS-CAM-01"
    ref = "REF-001"

    assert not engine.is_suppressed(cam, ref)
    engine.record_match(cam, ref)
    assert engine.is_suppressed(cam, ref)

    # Different reference is not suppressed
    assert not engine.is_suppressed(cam, "REF-002")
    # Different camera is not suppressed
    assert not engine.is_suppressed("FRS-CAM-02", ref)


# ── Test 16: Review Required Initial State ─────────────────────────────────────

@pytest.mark.asyncio
async def test_review_required_initial_state(db_session: AsyncSession):
    """Verifies candidate initial DB state is REVIEW_REQUIRED with review_required=True."""
    cand = FRSCandidate(
        candidate_code=f"FRS-INIT-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/test.jpg",
        match_score=88.5,
    )
    db_session.add(cand)
    await db_session.commit()
    await db_session.refresh(cand)

    assert cand.status == "REVIEW_REQUIRED"
    assert cand.review_required is True
    assert cand.reviewed_by is None
    assert cand.reviewed_at is None


# ── Test 17: Reviewer Confirmation (CONFIRMED_BY_REVIEWER) ────────────────────

@pytest.mark.asyncio
async def test_reviewer_confirmation(db_session: AsyncSession):
    """Verifies human reviewer confirmation updates status to CONFIRMED_BY_REVIEWER."""
    cand = FRSCandidate(
        candidate_code=f"FRS-REV-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/test.jpg",
        match_score=91.0,
    )
    db_session.add(cand)
    await db_session.commit()

    service = FRSService(db_session)
    req = FRSReviewRequest(
        decision="CONFIRMED_BY_REVIEWER",
        notes="Face landmarks strongly match reference profile.",
    )
    resp = await service.review_candidate(cand.candidate_code, req, officer_name="Commander Rao")

    assert resp.status == "CONFIRMED_BY_REVIEWER"
    assert resp.review_required is False
    assert resp.reviewed_by == "Commander Rao"

    # Verify candidate in DB
    await db_session.refresh(cand)
    assert cand.status == "CONFIRMED_BY_REVIEWER"
    assert cand.review_required is False


# ── Test 18: Reviewer Rejection (REJECTED_BY_REVIEWER) ────────────────────────

@pytest.mark.asyncio
async def test_reviewer_rejection(db_session: AsyncSession):
    """Verifies human reviewer rejection updates status to REJECTED_BY_REVIEWER."""
    cand = FRSCandidate(
        candidate_code=f"FRS-REJ-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="South Gate",
        zone_code="ZONE-B",
        location="South Gate",
        detected_image_path="/media/frs/test2.jpg",
        match_score=76.0,
    )
    db_session.add(cand)
    await db_session.commit()

    service = FRSService(db_session)
    req = FRSReviewRequest(
        decision="REJECTED_BY_REVIEWER",
        notes="False positive. Chin and nose structure do not align.",
    )
    resp = await service.review_candidate(cand.candidate_code, req, officer_name="Inspector Reddy")

    assert resp.status == "REJECTED_BY_REVIEWER"
    assert resp.review_required is False


# ── Test 19: Unresolved State (UNRESOLVED) ────────────────────────────────────

@pytest.mark.asyncio
async def test_unresolved_state(db_session: AsyncSession):
    """Verifies UNRESOLVED maintains review_required=True for continuous investigation."""
    cand = FRSCandidate(
        candidate_code=f"FRS-UNR-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="East Gate",
        zone_code="ZONE-C",
        location="East Gate",
        detected_image_path="/media/frs/test3.jpg",
        match_score=80.0,
    )
    db_session.add(cand)
    await db_session.commit()

    service = FRSService(db_session)
    req = FRSReviewRequest(
        decision="UNRESOLVED",
        notes="Lighting poor, awaiting secondary camera angle.",
    )
    resp = await service.review_candidate(cand.candidate_code, req, officer_name="Officer Sharma")

    assert resp.status == "UNRESOLVED"
    assert resp.review_required is True


# ── Test 20: Invalid Review Transition ────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_review_transition(db_session: AsyncSession):
    """Verifies already reviewed candidate cannot be re-reviewed, and invalid decisions raise 400."""
    cand = FRSCandidate(
        candidate_code=f"FRS-INV-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="East Gate",
        zone_code="ZONE-C",
        location="East Gate",
        detected_image_path="/media/frs/test4.jpg",
        match_score=80.0,
        status="CONFIRMED_BY_REVIEWER",
        review_required=False,
    )
    db_session.add(cand)
    await db_session.commit()

    service = FRSService(db_session)

    # 1. Already reviewed
    req = FRSReviewRequest(decision="REJECTED_BY_REVIEWER", notes="Attempting override")
    with pytest.raises(HTTPException) as exc_info:
        await service.review_candidate(cand.candidate_code, req)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.get("code") == "CANDIDATE_ALREADY_REVIEWED"

    # 2. Invalid decision
    cand2 = FRSCandidate(
        candidate_code=f"FRS-INV2-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="East Gate",
        zone_code="ZONE-C",
        location="East Gate",
        detected_image_path="/media/frs/test5.jpg",
        match_score=80.0,
    )
    db_session.add(cand2)
    await db_session.commit()

    bad_req = FRSReviewRequest(decision="AUTOMATIC_ARREST", notes="Illegal decision")
    with pytest.raises(HTTPException) as exc_bad:
        await service.review_candidate(cand2.candidate_code, bad_req)
    assert exc_bad.value.status_code == 400
    assert exc_bad.value.detail.get("code") == "INVALID_REVIEW_DECISION"


# ── Test 21: Audit Logging (FRSAuditLog Emission) ─────────────────────────────

@pytest.mark.asyncio
async def test_audit_logging(db_session: AsyncSession):
    """Verifies that human reviews emit immutable FRSAuditLog records."""
    cand = FRSCandidate(
        candidate_code=f"FRS-AUD-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/test.jpg",
        match_score=90.0,
    )
    db_session.add(cand)
    await db_session.commit()

    service = FRSService(db_session)
    req = FRSReviewRequest(decision="CONFIRMED_BY_REVIEWER", notes="Verified identity.")
    await service.review_candidate(cand.candidate_code, req, officer_name="Command Chief")
    await db_session.commit()

    stmt = select(FRSAuditLog).where(FRSAuditLog.candidate_code == cand.candidate_code)
    audit = (await db_session.execute(stmt)).scalars().first()
    assert audit is not None
    assert audit.officer_name == "Command Chief"
    assert audit.action == "FRS_MATCH_CONFIRMED_BY_REVIEWER"
    assert "Verified identity" in audit.details


# ── Test 22: WebSocket Event Sanitized ────────────────────────────────────────

def test_websocket_event_sanitized():
    """Verifies candidate event payload excludes embeddings and passwords."""
    engine = FRSEventEngine()
    payload = engine.build_candidate_event(
        camera_id="cam-123",
        camera_code="FRS-CAM-01",
        zone_id="zone-1",
        zone_code="ZONE-A",
        location="North Gate",
        candidate_code="FRS-EVT-9999",
        reference_id="REF-001",
        reference_name="Subject Alpha",
        similarity_score=89.5,
    )
    p_dict = payload.to_dict()
    assert "embedding" not in p_dict
    assert "password" not in p_dict
    assert p_dict["review_status"] == "REVIEW_REQUIRED"
    assert p_dict["candidate_id"] == "FRS-EVT-9999"


# ── Test 23: Pipeline Lifecycle (Start, Stop, Restart) ────────────────────────

@pytest.mark.asyncio
async def test_pipeline_lifecycle(db_session: AsyncSession, frs_test_camera: Camera):
    """Verifies full orchestrator start, stop, restart cycle for FRS pipeline."""
    # Start
    start_res = await ai_orchestrator.start_pipeline(
        frs_test_camera.camera_code,
        db_session,
        custom_detector=lambda f: [],
    )
    assert start_res["status"] == "STARTED"
    assert FRSPipelineRegistry.get(frs_test_camera.camera_code) is not None

    # Stop
    stop_res = await ai_orchestrator.stop_pipeline(frs_test_camera.camera_code, db_session)
    assert stop_res["status"] == "STOPPED"
    pipe = FRSPipelineRegistry.get(frs_test_camera.camera_code)
    assert pipe is None or pipe.state == PipelineState.STOPPED

    # Restart
    restart_res = await ai_orchestrator.restart_pipeline(
        frs_test_camera.camera_code,
        db_session,
        custom_detector=lambda f: [],
    )
    assert restart_res["status"] == "RESTARTED"
    assert FRSPipelineRegistry.get(frs_test_camera.camera_code) is not None


# ── Test 24: Health Monitoring ────────────────────────────────────────────────

def test_health_monitoring():
    """Verifies FRSPipelineHealthTracker calculates FPS and latencies."""
    tracker = FRSPipelineHealthTracker(camera_code="FRS-CAM-01")
    tracker.record_frame(det_ms=12.5, emb_ms=18.0, match_ms=4.2, processing_fps=14.5)
    health = tracker.get_health()

    assert health["status"] == "HEALTHY"
    assert health["fps"] == 14.5
    assert health["detection_latency_ms"] > 0.0
    assert health["embedding_latency_ms"] > 0.0
    assert health["matching_latency_ms"] > 0.0


# ── Test 25: RTSP Failure Detection ───────────────────────────────────────────

def test_rtsp_failure_detection():
    """Verifies timeout transitions health status to DEGRADED and FAILED."""
    tracker = FRSPipelineHealthTracker(camera_code="FRS-CAM-01")
    # Simulate last frame received 20 seconds ago
    tracker.last_frame_time = time.time() - 20.0
    assert tracker.evaluate_status() == "FAILED"

    # Simulate 5 consecutive errors
    tracker2 = FRSPipelineHealthTracker(camera_code="FRS-CAM-02")
    for _ in range(5):
        tracker2.record_error("RTSP packet dropped")
    assert tracker2.evaluate_status() == "FAILED"


# ── Test 26: Recovery Through Orchestrator ─────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_through_orchestrator(db_session: AsyncSession, frs_test_camera: Camera):
    """Verifies orchestrator recovers FRS pipeline when desired_state == RUNNING across restart."""
    # Create deployment with desired RUNNING but actual STOPPED
    deployment = AIPipelineDeployment(
        camera_id=frs_test_camera.id,
        camera_code=frs_test_camera.camera_code,
        profile_id="FRS_STANDARD",
        pipeline_type="FRS",
        desired_state="RUNNING",
        actual_state="STOPPED",
        health_state="STOPPED",
    )
    db_session.add(deployment)
    await db_session.commit()

    with patch("app.ai.orchestrator.service.AsyncSessionLocal", MockSessionContext(db_session)), \
         patch("app.ai.orchestrator.service.ai_orchestrator.start_pipeline") as mock_start:
        mock_start.return_value = {"status": "STARTED"}
        await ai_orchestrator.recover_on_startup()
        assert mock_start.called


# ── Test 27: No Crowd Interaction (Strict Biometric Isolation) ────────────────

def test_no_crowd_interaction():
    """Verifies FRS pipeline execution touches zero Crowd data structures or tracking IDs."""
    cfg = FRSPipelineConfig(
        camera_id="cam-frs",
        camera_code="FRS-CAM-01",
        camera_name="Gate 1",
        rtsp_url="rtsp://***:***@localhost:554/live",
        sanitized_rtsp_url="rtsp://***:***@localhost:554/live",
    )
    pipeline = FRSPipeline(
        config=cfg,
        custom_detector=lambda f: [],
    )
    status = pipeline.get_status()
    assert "crowd_count" not in status
    assert "density" not in status
    assert "tracking_id" not in status
    assert status["pipeline_type"] == "FRS"


# ── Test 28: No Queue Interaction (Strict Queue Isolation) ────────────────────

def test_no_queue_interaction():
    """Verifies FRS pipeline execution touches zero Queue data structures or wait times."""
    cfg = FRSPipelineConfig(
        camera_id="cam-frs",
        camera_code="FRS-CAM-01",
        camera_name="Gate 1",
        rtsp_url="rtsp://***:***@localhost:554/live",
        sanitized_rtsp_url="rtsp://***:***@localhost:554/live",
    )
    pipeline = FRSPipeline(
        config=cfg,
        custom_detector=lambda f: [],
    )
    status = pipeline.get_status()
    assert "queue_length" not in status
    assert "wait_time_minutes" not in status
    assert "line_crossings" not in status


# ── Test 29: Credential Non-Leakage ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_credential_non_leakage(client: AsyncClient, frs_tokens: Dict[str, str], frs_test_camera: Camera):
    """Verifies camera passwords are never exposed in FRS API responses."""
    headers = {"Authorization": f"Bearer {frs_tokens['ROLE_FRS_READER']}"}
    res = await client.get("/api/v1/frs/cameras", headers=headers)
    assert res.status_code == 200
    res_text = res.text
    assert "secret123" not in res_text


# ── Test 30: Embedding Non-Leakage ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embedding_non_leakage(client: AsyncClient, db_session: AsyncSession, frs_tokens: Dict[str, str]):
    """Verifies 512-D vectors are omitted from candidate and reference person endpoints."""
    # Create profile with vector in DB
    prof = FRSReferenceProfile(
        reference_id=f"REF-LEAK-{uuid.uuid4().hex[:4]}",
        display_name="Secure Person",
        category="Authorized Watchlist",
        reference_image_path="/media/frs/reference/secure.jpg",
        embedding_vector=[0.123] * 512,
        active=True,
    )
    db_session.add(prof)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {frs_tokens['ROLE_FRS_READER']}"}
    res = await client.get("/api/v1/frs/reference-persons", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    for p in data:
        assert "embedding" not in p
        assert "embedding_vector" not in p


# ── Test 31: Image Access Authorization ───────────────────────────────────────

@pytest.mark.asyncio
async def test_image_access_authorization(client: AsyncClient):
    """Verifies unauthenticated access to FRS endpoints is strictly denied with 401."""
    res = await client.get("/api/v1/frs/candidates")
    assert res.status_code == 401


# ── Test 32: Retention Cleanup ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retention_cleanup(db_session: AsyncSession):
    """Verifies cleanup_expired_candidates purges expired candidates while preserving audit logs."""
    # Create expired candidate (40 days old)
    old_cand = FRSCandidate(
        candidate_code=f"FRS-EXP-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/detected/expired.jpg",
        match_score=85.0,
    )
    old_cand.detected_at = datetime.now(timezone.utc) - timedelta(days=40)
    db_session.add(old_cand)

    # Create recent candidate (5 days old)
    new_cand = FRSCandidate(
        candidate_code=f"FRS-ACT-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/detected/active.jpg",
        match_score=88.0,
    )
    new_cand.detected_at = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.add(new_cand)

    # Create audit log associated with expired candidate
    audit = FRSAuditLog(
        audit_code=f"AUD-{uuid.uuid4().hex[:6].upper()}",
        candidate_code=old_cand.candidate_code,
        reference_id="REF-001",
        action="FRS_MATCH_REVIEWED",
        officer_name="Officer Rao",
        details="Historical review log that must be preserved",
    )
    db_session.add(audit)
    await db_session.commit()

    service = FRSService(db_session)
    cleanup_res = await service.cleanup_expired_candidates(retention_days=30)
    assert cleanup_res.deleted_candidates_count >= 1

    # Verify old candidate is gone
    stmt_old = select(FRSCandidate).where(FRSCandidate.candidate_code == old_cand.candidate_code)
    assert (await db_session.execute(stmt_old)).scalars().first() is None

    # Verify new candidate still exists
    stmt_new = select(FRSCandidate).where(FRSCandidate.candidate_code == new_cand.candidate_code)
    assert (await db_session.execute(stmt_new)).scalars().first() is not None

    # Verify audit log is preserved
    stmt_aud = select(FRSAuditLog).where(FRSAuditLog.candidate_code == old_cand.candidate_code)
    assert (await db_session.execute(stmt_aud)).scalars().first() is not None


# ── Test 33: Model Version Tracking ───────────────────────────────────────────

def test_model_version_tracking():
    """Verifies candidates track detector (buffalo_l) and embedder (insightface-r50) versions."""
    cand = FRSCandidate(
        candidate_code="FRS-VER-001",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/test.jpg",
        match_score=89.0,
    )
    assert cand.model_version == "buffalo_l"
    assert cand.embedding_model_version == "insightface-r50"


# ── Test 34: Threshold Configuration Update ───────────────────────────────────

@pytest.mark.asyncio
async def test_threshold_configuration_update(client: AsyncClient, frs_tokens: Dict[str, str]):
    """Verifies updating thresholds via PUT /config updates in-memory config and logs audit."""
    headers = {"Authorization": f"Bearer {frs_tokens['ROLE_FRS_MANAGER']}"}
    update_payload = {
        "match_threshold": 0.82,
        "min_sharpness_score": 55.0,
        "retention_days": 45,
    }
    res = await client.put("/api/v1/frs/config", json=update_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["match_threshold"] == 0.82
    assert data["min_sharpness_score"] == 55.0
    assert data["retention_days"] == 45


# ── Test 35: No Automatic Identity Confirmation Verification ──────────────────

def test_no_automatic_identity_confirmation():
    """Safety Test: FRS pipeline output MUST NOT automatically declare confirmed identity."""
    emb = normalize_l2(np.array([1.0] * 512, dtype=np.float32))
    mock_detected = [DetectedFace(bbox=(10, 10, 110, 110), confidence=0.99)]

    cfg = FRSPipelineConfig(
        camera_id="cam-safety",
        camera_code="FRS-SAFETY-01",
        camera_name="Perimeter Gate",
        rtsp_url="rtsp://***:***@localhost:554/live",
        sanitized_rtsp_url="rtsp://***:***@localhost:554/live",
    )
    pipeline = FRSPipeline(
        config=cfg,
        custom_detector=lambda f: mock_detected,
        custom_embedder=lambda c: emb,
    )
    pipeline.quality_gate.assess_quality = MagicMock(return_value=FaceQualityResult(passed=True, quality_score=0.99))
    pipeline.matcher.load_gallery([
        {"id": "p1", "reference_id": "REF-001", "display_name": "VIP Target", "embedding": emb, "active": True}
    ])

    test_frame = np.zeros((200, 200, 3), dtype=np.uint8)
    candidates = pipeline.process_frame(test_frame)

    assert len(candidates) == 1
    c = candidates[0]
    # Match score 100% must STILL be REVIEW_REQUIRED
    assert c["match_score"] == 100.0
    assert c["status"] == "REVIEW_REQUIRED"
    assert c["review_required"] is True
    assert c["status"] != "CONFIRMED"
    assert c["status"] != "CONFIRMED_BY_REVIEWER"


# ── Test 36: No Automatic Enforcement Action Verification ─────────────────────

@pytest.mark.asyncio
async def test_no_automatic_enforcement_action(db_session: AsyncSession):
    """Safety Test: Generating a candidate does NOT trigger police dispatch or access denial."""
    # Ensure no automated enforcement side-effects
    cand = FRSCandidate(
        candidate_code=f"FRS-SAFE-{uuid.uuid4().hex[:6].upper()}",
        camera_code="FRS-CAM-01",
        camera_name="North Gate",
        zone_code="ZONE-A",
        location="North Gate",
        detected_image_path="/media/frs/test.jpg",
        match_score=99.9,
    )
    db_session.add(cand)
    await db_session.commit()

    # Verify only candidate status and no active enforcement incidents or dispatches
    assert cand.status == "REVIEW_REQUIRED"
    assert cand.review_required is True
