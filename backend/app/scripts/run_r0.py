"""
run_r0.py — Smooth low-latency RTSP Face Recognition

Architecture:

    RTSP camera
        |
        v
    RTSPReader (capture thread, latest frame only)
        |
        +--------------------------+
        |                          |
        v                          v
    Display loop              FRS GPU worker
    every camera frame        every Nth frame
        |                          |
        |                     buffalo_l
        |                          |
        |                     embedding
        |                          |
        |                     PostgreSQL gallery
        |                          |
        +-----------> tracker <----+
                         |
                         v
                  predicted bbox/name

Important:
    The display loop NEVER waits for buffalo_l.
    Bounding boxes are predicted between GPU detections so the
    visible CCTV feed stays smooth while recognition runs separately.
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ============================================================
# CUDA DLL PATH FIX
# ============================================================
# onnxruntime-gpu ships nvidia CUDA DLLs inside the venv under
# site-packages/nvidia/*/bin/.  Windows does NOT search there
# automatically, so CUDAExecutionProvider fails to load even
# though all the DLLs are present.
# os.add_dll_directory() tells Windows to search those folders
# BEFORE falling back to CPUExecutionProvider.
# This must run before any onnxruntime / insightface import.

def _register_cuda_dll_dirs() -> None:
    try:
        sp = next(
            p for p in sys.path
            if "site-packages" in p and os.path.isdir(p)
        )
    except StopIteration:
        return

    nvidia_root = os.path.join(sp, "nvidia")
    if not os.path.isdir(nvidia_root):
        return

    for pkg in os.listdir(nvidia_root):
        bin_dir = os.path.join(nvidia_root, pkg, "bin")
        if os.path.isdir(bin_dir):
            try:
                os.add_dll_directory(bin_dir)
            except (OSError, AttributeError):
                pass

_register_cuda_dll_dirs()


import cv2
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# APPLICATION IMPORTS
# ============================================================

from app.database import repository as db
from app.models.face_model import FaceModel
from app.recognition.matcher import IdentityMatcher
from app.input.rtsp_input import RTSPReader
from app.input.image_input import load_image
from app.input.video_input import iter_video_frames
from app.config import MATCH_THRESHOLD, FRAME_SKIP, RTSP_URL


# ============================================================
# PERFORMANCE CONFIGURATION
# ============================================================

WINDOW_NAME = "R0 - Smooth CCTV FRS"

# buffalo_l detection/embedding is expensive.
# Tracking runs on the frames between detections.
DETECTION_INTERVAL = 3

# Keep a recognized track alive for this many seconds if a
# detection temporarily disappears.
MAX_RESULT_AGE_SECONDS = 1.5

# Camera is approximately 30 FPS.
CAMERA_FPS_ASSUMED = 30.0

# Minimum IoU for matching a new detection to an existing track.
MIN_MATCH_IOU = 0.05

# Center-distance fallback, in pixels at the displayed 960x540 size.
MAX_CENTER_DISTANCE = 180.0

# Exponential smoothing for predicted motion.
VELOCITY_SMOOTHING = 0.60

# Camera/display resolution.
DISPLAY_WIDTH = 960
DISPLAY_HEIGHT = 540

# Do not wait for old frames.
RTSP_TIMEOUT = 0.01


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class FaceResult:
    bbox: np.ndarray
    name: str
    similarity: float
    det_score: float
    is_known: bool
    person_id: Optional[int]

    # Camera frame where this detection was produced.
    frame_id: int

    # Motion in pixels per camera frame.
    velocity: np.ndarray

    # Number of camera frames since the last detection.
    misses: int = 0

    # Wall-clock time when this track was last detected.
    updated_at: float = 0.0

    # --------------------------------------------------------
    # Pose angles from buffalo_l 1k3d68 model (degrees).
    # yaw   : left (-) / right (+)   head rotation
    # pitch : down (-) / up (+)      head tilt
    # roll  : counter (-) / clock(+) head tilt sideways
    # --------------------------------------------------------
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0

    # --------------------------------------------------------
    # Estimated distance from camera (cm).
    # Derived from bbox height and assumed average face height
    # of 23 cm with a typical focal length for 960x540 display.
    # Not calibrated — for relative comparison only.
    # --------------------------------------------------------
    est_distance_cm: float = 0.0


# ============================================================
# GEOMETRY HELPERS
# ============================================================


def _bbox_center(bbox: np.ndarray) -> np.ndarray:
    b = np.asarray(bbox, dtype=np.float32)
    return np.array(
        [
            (b[0] + b[2]) * 0.5,
            (b[1] + b[3]) * 0.5,
        ],
        dtype=np.float32,
    )


def _bbox_iou(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)

    union = area_a + area_b - inter

    if union <= 0.0:
        return 0.0

    return float(inter / union)


def _predict_bbox(
    result: FaceResult,
    target_frame_id: int,
) -> np.ndarray:
    delta = max(
        0,
        target_frame_id - result.frame_id,
    )

    shift = result.velocity * float(delta)

    bbox = (
        np.asarray(result.bbox, dtype=np.float32)
        + np.array(
            [
                shift[0],
                shift[1],
                shift[0],
                shift[1],
            ],
            dtype=np.float32,
        )
    )

    return bbox




def _clamp_bbox(
    bbox: np.ndarray,
    width: int,
    height: int,
) -> np.ndarray:
    b = np.asarray(
        bbox,
        dtype=np.float32,
    ).copy()

    b[0] = np.clip(b[0], 0, width - 1)
    b[1] = np.clip(b[1], 0, height - 1)
    b[2] = np.clip(b[2], 0, width - 1)
    b[3] = np.clip(b[3], 0, height - 1)

    if b[2] <= b[0]:
        b[2] = min(
            width - 1,
            b[0] + 2,
        )

    if b[3] <= b[1]:
        b[3] = min(
            height - 1,
            b[1] + 2,
        )

    return b


# ============================================================
# EXCEL LOGGING  (Press P during live feed)
# ============================================================

# Output path — one file, one sheet per enrolled person.
# Absolute path so it always saves here regardless of cwd.
EXCEL_PATH   = os.path.join(PROJECT_ROOT, "data", "r0_evaluation.xlsx")
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "data", "snapshots")

# Match threshold (same as matcher).
EVAL_THRESHOLD = 0.5

# Assumed average face height in cm (pinhole distance estimate).
ASSUMED_FACE_HEIGHT_CM = 23.0
FOCAL_LENGTH_PX = 700.0


def _estimate_distance_cm(bbox: np.ndarray) -> float:
    """
    Estimate face-to-camera distance using the pinhole model.
    NOT calibrated — for relative comparison only.
    """
    h = float(bbox[3] - bbox[1])
    if h <= 0:
        return 0.0
    return round(
        (ASSUMED_FACE_HEIGHT_CM * FOCAL_LENGTH_PX) / h,
        1,
    )


# ── Exact column order requested by user ─────────────────────
# (image, ground_truth, similarity, recognized, correct,
#  det_score, note, threshold, identity, experiment)
_COLUMNS = [
    ("image",          28),   # snapshot filename
    ("ground_truth",   16),   # actual person (fill manually)
    ("similarity",     13),   # cosine match score
    ("recognized",     12),   # Yes / No  (>= threshold)
    ("correct",        10),   # Yes / No / ? (fill after review)
    ("det_score",      13),   # buffalo_l detection confidence
    ("note",           38),   # yaw/pitch/roll/distance summary
    ("threshold",      12),   # match threshold used
    ("identity",       16),   # model's predicted name
    ("experiment",     18),   # experiment tag (fill manually)
]

# Style constants
_HDR_FONT  = Font(bold=True, color="FFFFFF")
_HDR_FILL  = PatternFill(fill_type="solid", fgColor="1F4E79")
_HDR_ALIGN = Alignment(horizontal="center", wrap_text=True)
_ALT_FILL  = PatternFill(fill_type="solid", fgColor="D6E4F0")


def _sheet_name_for(person_name: str) -> str:
    """Sheet tab name = person name, trimmed to 31 chars."""
    return person_name.strip()[:31]


def _build_sheet(
    wb: openpyxl.Workbook,
    sheet_title: str,
) -> "openpyxl.worksheet.worksheet.Worksheet":
    """
    Create a new sheet with styled headers and frozen row.
    Returns the worksheet.
    """
    ws = wb.create_sheet(title=sheet_title)

    for ci, (hdr, width) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=1, column=ci, value=hdr)
        cell.font      = _HDR_FONT
        cell.fill      = _HDR_FILL
        cell.alignment = _HDR_ALIGN
        ws.column_dimensions[
            openpyxl.utils.get_column_letter(ci)
        ].width = width

    ws.freeze_panes = "A2"
    return ws


def _get_or_build_sheet(
    wb: openpyxl.Workbook,
    sheet_title: str,
) -> "openpyxl.worksheet.worksheet.Worksheet":
    """Return existing sheet or create it with headers."""
    if sheet_title in wb.sheetnames:
        return wb[sheet_title]
    return _build_sheet(wb, sheet_title)


def _append_data_row(
    ws: "openpyxl.worksheet.worksheet.Worksheet",
    values: list,
) -> None:
    """Append a row; shade every even data row light blue."""
    ws.append(values)
    row_idx = ws.max_row
    if row_idx % 2 == 0:
        for cell in ws[row_idx]:
            cell.fill = _ALT_FILL


def _init_evaluation_excel() -> None:
    """
    Create the evaluation Excel file with a single 'Evaluation' sheet
    and styled headers if it does not already exist.
    Called once at startup.
    """
    import os
    os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)

    if os.path.exists(EXCEL_PATH):
        return

    wb = openpyxl.Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Single sheet for all logs
    _build_sheet(wb, "Evaluation")

    wb.save(EXCEL_PATH)
    print(f"[Excel] Initialized {EXCEL_PATH} (single sheet: 'Evaluation')")


def _save_to_excel(
    results: List[FaceResult],
    frame_id: int,
    snapshot_path: str,
) -> None:
    """
    Append detection rows to the single 'Evaluation' sheet chronologically.

    Columns (exact):
        image         — snapshot filename
        ground_truth  — left blank (user fills after test)
        similarity    — cosine score from matcher
        recognized    — Yes / No  (similarity >= threshold)
        correct       — left blank (user fills after review)
        det_score     — buffalo_l detection confidence
        note          — yaw/pitch/roll + distance summary
        threshold     — threshold used for this run
        identity      — model's predicted name
        experiment    — left blank (user fills experiment tag)
    """
    import os
    from datetime import datetime

    os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)
    snap_name = os.path.basename(snapshot_path)

    if os.path.exists(EXCEL_PATH):
        wb = openpyxl.load_workbook(EXCEL_PATH)
        # Use first sheet or 'Evaluation'
        ws = wb.active if wb.sheetnames else _build_sheet(wb, "Evaluation")
    else:
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]
        ws = _build_sheet(wb, "Evaluation")

    logged = 0

    if not results:
        # ── No face detected ──────────────────────────────────
        row_data = [
            snap_name,          # image
            "",                 # ground_truth
            "",                 # similarity
            "No",               # recognized
            "",                 # correct
            "",                 # det_score
            "No face detected", # note
            EVAL_THRESHOLD,     # threshold
            "—",                # identity
            "",                 # experiment
        ]
        _append_data_row(ws, row_data)
        logged = 1

    else:
        for r in results:
            bbox = np.asarray(r.bbox, dtype=int)
            x1, y1, x2, y2 = (
                int(bbox[0]), int(bbox[1]),
                int(bbox[2]), int(bbox[3]),
            )
            dist_cm = _estimate_distance_cm(bbox)

            # ── Note: Clean angle (degrees + direction) & distance ─
            abs_yaw = abs(r.yaw)
            if abs_yaw < 5.0:
                direction = "Frontal"
            elif r.yaw < 0:
                direction = "Left"
            else:
                direction = "Right"

            dist_str = f"{dist_cm / 100.0:.1f}m" if dist_cm > 0 else "unknown"
            note = f"angle: {abs_yaw:.1f}° ({direction}) | dist: {dist_str}"

            row_data = [
                snap_name,                              # image
                "",                                     # ground_truth
                round(float(r.similarity),  4),         # similarity
                "Yes" if r.is_known else "No",          # recognized
                "",                                     # correct
                round(float(r.det_score),   4),         # det_score
                note,                                   # note
                EVAL_THRESHOLD,                         # threshold
                r.name,                                 # identity
                "",                                     # experiment
            ]

            _append_data_row(ws, row_data)
            logged += 1

    try:
        wb.save(EXCEL_PATH)
        print(f"[Excel] {logged} row(s) saved -> {EXCEL_PATH}")
    except PermissionError:
        print(
            "\n[WARNING] Could not save to " + EXCEL_PATH + " because it is OPEN in Microsoft Excel!"
        )
        print("[WARNING] Please CLOSE Excel so new logs can be written directly.\n")
    except Exception as exc:
        print(f"[ERROR] Failed to save Excel: {exc}")


# ============================================================
# SHARED STATE
# ============================================================

class SharedState:

    def __init__(self) -> None:
        self.lock = threading.Lock()

        self.latest_frame: Optional[np.ndarray] = None
        self.frame_id = 0

        self.results: List[FaceResult] = []

        self.running = True

        self.frs_fps = 0.0
        self.last_detection_ms = 0.0

    def update_frame(
        self,
        frame: np.ndarray,
    ) -> int:

        with self.lock:
            self.frame_id += 1
            self.latest_frame = frame
            return self.frame_id

    def get_frame(
        self,
    ) -> Tuple[Optional[np.ndarray], int]:

        with self.lock:

            if self.latest_frame is None:
                return None, self.frame_id

            return (
                self.latest_frame.copy(),
                self.frame_id,
            )

    def update_results(
        self,
        results: List[FaceResult],
        detection_ms: float,
    ) -> None:

        with self.lock:

            self.results = results
            self.last_detection_ms = detection_ms

    def get_results(
        self,
        current_frame_id: int,
    ) -> List[FaceResult]:

        now = time.monotonic()

        with self.lock:

            output: List[FaceResult] = []

            for result in self.results:

                # ------------------------------------------------
                # Time since this face was ACTUALLY detected.
                # ------------------------------------------------

                age_seconds = (
                    now - result.updated_at
                )

                # ------------------------------------------------
                # Remove track after person has disappeared.
                # ------------------------------------------------

                if age_seconds > MAX_RESULT_AGE_SECONDS:
                    continue

                # ------------------------------------------------
                # Predict bbox for the current camera frame.
                # ------------------------------------------------

                predicted = _predict_bbox(
                    result,
                    current_frame_id,
                )

                delta = (
                    current_frame_id
                    - result.frame_id
                )

                if delta < 0:
                    delta = 0

                # ------------------------------------------------
                # Create display copy.
                # ------------------------------------------------

                output.append(
                    FaceResult(
                        bbox=predicted,
                        name=result.name,
                        similarity=result.similarity,
                        det_score=result.det_score,
                        is_known=result.is_known,
                        person_id=result.person_id,
                        frame_id=result.frame_id,
                        velocity=result.velocity.copy(),
                        misses=delta,
                        updated_at=result.updated_at,
                        yaw=result.yaw,
                        pitch=result.pitch,
                        roll=result.roll,
                        est_distance_cm=result.est_distance_cm,
                    )
                )

            # IMPORTANT:
            # This return MUST be inside get_results().
            return output

    def stop(self) -> None:

        with self.lock:
            self.running = False

    def is_running(self) -> bool:

        with self.lock:
            return self.running




# ============================================================
# FRS GPU WORKER
# ============================================================

class FRSWorker:

    def __init__(
        self,
        state: SharedState,
        model: FaceModel,
        matcher: IdentityMatcher,
        log_events: bool = True,
        every: int = DETECTION_INTERVAL,
    ) -> None:

        self.state = state
        self.model = model
        self.matcher = matcher
        self.log_events = log_events
        self.every = max(1, every)

        self.thread: Optional[
            threading.Thread
        ] = None

        self.last_processed_frame = -1

        # Tracks from the previous detection cycle.
        self.tracks: List[FaceResult] = []

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="FRS-GPU-Worker",
        )
        self.thread.start()

        print(
            "[FRS Worker] Started "
            f"(detection every {self.every} frames)."
        )

    def stop(self) -> None:
        if self.thread:
            self.thread.join(timeout=3.0)

    def _run(self) -> None:

        while self.state.is_running():

            frame, frame_id = (
                self.state.get_frame()
            )

            if frame is None:
                time.sleep(0.002)
                continue

            if frame_id == self.last_processed_frame:
                time.sleep(0.001)
                continue

            # We only submit selected frames to buffalo_l.
            if frame_id % self.every != 0:
                self.last_processed_frame = frame_id
                time.sleep(0.001)
                continue

            self.last_processed_frame = frame_id

            start = time.perf_counter()

            try:
                self._recognize(
                    frame,
                    frame_id,
                )

            except Exception as exc:
                print(
                    f"[FRS ERROR] {type(exc).__name__}: {exc}"
                )

            elapsed = (
                time.perf_counter() - start
            )

            if elapsed > 0:
                current_fps = 1.0 / elapsed

                if self.state.frs_fps == 0:
                    self.state.frs_fps = current_fps
                else:
                    self.state.frs_fps = (
                        self.state.frs_fps * 0.8
                        + current_fps * 0.2
                    )

    def _recognize(
        self,
        rgb_frame: np.ndarray,
        frame_id: int,
    ) -> None:

        # --------------------------------------------------------
        # GPU face detection + embedding
        # --------------------------------------------------------

        faces = self.model.detect_faces(
            rgb_frame
        )           
        print(
            f"[DEBUG] frame={frame_id} "
            f"faces_detected={len(faces)}"
        )

        for i, face in enumerate(faces):
            print(
                 f"[DEBUG] face={i} "
                 f"bbox={face.bbox} "
                 f"det={face.det_score:.3f}"
            )

        new_detections: List[FaceResult] = []

        for face in faces:

            embedding = face.embedding

            if embedding is None:
                continue

            embedding = np.asarray(
                embedding,
                dtype=np.float32,
            ).flatten()

            if embedding.shape != (512,):
                continue

            norm = np.linalg.norm(
                embedding
            )

            if norm <= 0:
                continue

            embedding = embedding / norm

            # ----------------------------------------------------
            # PostgreSQL gallery matching
            # ----------------------------------------------------

            match = (
                self.matcher.find_best_match(
                    embedding
                )
            )

            new_detections.append(
                FaceResult(
                    bbox=np.asarray(
                        face.bbox,
                        dtype=np.float32,
                    ).copy(),
                    name=match.name,
                    similarity=float(
                        match.similarity
                    ),
                    det_score=float(
                        face.det_score
                    ),
                    is_known=bool(
                        match.is_known
                    ),
                    person_id=match.person_id,
                    frame_id=frame_id,
                    velocity=np.zeros(
                        2,
                        dtype=np.float32,
                    ),
                    misses=0,
                    updated_at=time.monotonic(),
                    yaw=float(face.pose[1]) if face.pose is not None and len(face.pose) >= 3 else 0.0,
                    pitch=float(face.pose[0]) if face.pose is not None and len(face.pose) >= 3 else 0.0,
                    roll=float(face.pose[2]) if face.pose is not None and len(face.pose) >= 3 else 0.0,
                    est_distance_cm=_estimate_distance_cm(face.bbox),
                )
            )
            # ----------------------------------------------------
            # Database logging happens only in the worker.
            # It NEVER blocks the display loop.
            # ----------------------------------------------------

            if self.log_events:
                try:
                    db.log_recognition_event(
                        source="rtsp",
                        predicted_name=match.name,
                        similarity=match.similarity,
                        threshold=match.threshold,
                        is_known=match.is_known,
                        person_id=match.person_id,
                        frame_id=f"rtsp_{frame_id}",
                    )
                except Exception as exc:
                    print(
                        f"[DB LOG ERROR] {exc}"
                    )

        # --------------------------------------------------------
        # Update tracker
        # --------------------------------------------------------

        updated_tracks = (
            self._update_tracks(
                new_detections,
                frame_id,
            )
        )

        self.tracks = updated_tracks

        detection_ms = (
            time.perf_counter()
            - (
                time.perf_counter()
                - 0
            )
        )

        # The exact worker elapsed time is calculated by _run().
        # This value is not used for recognition.
        self.state.update_results(
            self.tracks,
            detection_ms=0.0,
        )

    def _update_tracks(
        self,
        detections: List[FaceResult],
        frame_id: int,
    ) -> List[FaceResult]:

        now = time.monotonic()

        # ------------------------------------------------------------
        # First detection
        # ------------------------------------------------------------

        if not self.tracks:
            return detections

        used_tracks = set()
        updated: List[FaceResult] = []

        # ------------------------------------------------------------
        # Match new detections against existing tracks
        # ------------------------------------------------------------

        for detection in detections:

            best_index = -1
            best_score = -1.0

            detection_center = _bbox_center(
                detection.bbox
            )

            for index, old in enumerate(self.tracks):

                if index in used_tracks:
                    continue

                # Predict where old track should currently be.
                predicted_old = _predict_bbox(
                    old,
                    frame_id,
                )

                iou = _bbox_iou(
                    detection.bbox,
                    predicted_old,
                )

                old_center = _bbox_center(
                    predicted_old
                )

                distance = float(
                    np.linalg.norm(
                        detection_center
                        - old_center
                    )
                )

                # ----------------------------------------------------
                # Distance score
                # ----------------------------------------------------

                distance_score = max(
                    0.0,
                    1.0
                    - (
                        distance
                        / MAX_CENTER_DISTANCE
                    ),
                )

                # ----------------------------------------------------
                # Combined matching score
                # ----------------------------------------------------

                score = (
                    iou * 0.65
                    + distance_score * 0.35
                )

                # ----------------------------------------------------
                # Accept this old track as a match
                # ----------------------------------------------------

                if (
                    iou >= MIN_MATCH_IOU
                    or distance <= MAX_CENTER_DISTANCE
                ):

                    if score > best_score:

                        best_score = score
                        best_index = index

            # --------------------------------------------------------
            # Existing track matched
            # --------------------------------------------------------

            if best_index >= 0:

                old = self.tracks[
                    best_index
                ]

                used_tracks.add(
                    best_index
                )

                old_predicted = _predict_bbox(
                    old,
                    frame_id,
                )

                old_center = _bbox_center(
                    old_predicted
                )

                new_center = _bbox_center(
                    detection.bbox
                )

                gap = max(
                    1,
                    frame_id - old.frame_id,
                )

                measured_velocity = (
                    new_center
                    - old_center
                ) / float(gap)

                velocity = (
                    old.velocity
                    * VELOCITY_SMOOTHING
                    +
                    measured_velocity
                    * (
                        1.0
                        - VELOCITY_SMOOTHING
                    )
                )

                detection.velocity = (
                    velocity.astype(
                        np.float32
                    )
                )

                # ----------------------------------------------------
                # This is a REAL fresh detection.
                # Reset disappearance timer.
                # ----------------------------------------------------

                detection.updated_at = now
                detection.misses = 0

                updated.append(
                    detection
                )

            # --------------------------------------------------------
            # Completely new person
            # --------------------------------------------------------

            else:

                detection.updated_at = now
                detection.misses = 0

                updated.append(
                    detection
                )

        # ------------------------------------------------------------
        # Keep old tracks when detector temporarily misses them
        # ------------------------------------------------------------

        for index, old in enumerate(self.tracks):

            if index in used_tracks:
                continue

            # How long since this person was last actually detected?
            age_seconds = (
                now - old.updated_at
            )

            # --------------------------------------------------------
            # Person has disappeared for too long.
            # Remove track.
            # --------------------------------------------------------

            if age_seconds > MAX_RESULT_AGE_SECONDS:
                continue

            # --------------------------------------------------------
            # Person is temporarily missed.
            # Keep tracking/predicting.
            # --------------------------------------------------------

            predicted_bbox = _predict_bbox(
                old,
                frame_id,
            )

            misses = (
                frame_id - old.frame_id
            )

            old_copy = FaceResult(
                bbox=predicted_bbox,
                name=old.name,
                similarity=old.similarity,
                det_score=old.det_score,
                is_known=old.is_known,
                person_id=old.person_id,
                frame_id=old.frame_id,
                velocity=old.velocity.copy(),
                misses=misses,
                updated_at=old.updated_at,
            )

            updated.append(
                old_copy
            )

        return updated


# ============================================================
# DRAWING
# ============================================================

def draw_results(
    bgr: np.ndarray,
    results: List[FaceResult],
    current_frame_id: int,
) -> np.ndarray:

    height, width = bgr.shape[:2]

    for result in results:

        bbox = _predict_bbox(
            result,
            current_frame_id,
        )

        bbox = _clamp_bbox(
            bbox,
            width,
            height,
        )

        x1, y1, x2, y2 = (
            int(bbox[0]),
            int(bbox[1]),
            int(bbox[2]),
            int(bbox[3]),
        )

        if result.is_known:
            color = (
                0,
                255,
                0,
            )
        else:
            color = (
                0,
                165,
                255,
            )

        # --------------------------------------------------------
        # Bounding box
        # --------------------------------------------------------

        cv2.rectangle(
            bgr,
            (x1, y1),
            (x2, y2),
            color,
            2,
            cv2.LINE_AA,
        )

        # --------------------------------------------------------
        # Name + similarity
        # --------------------------------------------------------

        label = (
            f"{result.name} "
            f"{result.similarity:.2f}"
        )

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.60
        thickness = 2

        text_size, baseline = (
            cv2.getTextSize(
                label,
                font,
                scale,
                thickness,
            )
        )

        text_width = text_size[0]
        text_height = text_size[1]

        label_top = max(
            0,
            y1 - text_height - 12,
        )

        label_bottom = (
            label_top
            + text_height
            + baseline
            + 6
        )

        cv2.rectangle(
            bgr,
            (
                x1,
                label_top,
            ),
            (
                min(
                    width - 1,
                    x1 + text_width + 8,
                ),
                min(
                    height - 1,
                    label_bottom,
                ),
            ),
            color,
            -1,
        )

        cv2.putText(
            bgr,
            label,
            (
                x1 + 4,
                label_bottom - baseline - 3,
            ),
            font,
            scale,
            (
                0,
                0,
                0,
            ),
            thickness,
            cv2.LINE_AA,
        )

        # --------------------------------------------------------
        # Detection confidence
        # --------------------------------------------------------

        cv2.putText(
            bgr,
            f"det:{result.det_score:.2f}",
            (
                x1,
                min(
                    height - 5,
                    y2 + 18,
                ),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (
                220,
                220,
                220,
            ),
            1,
            cv2.LINE_AA,
        )

    return bgr


# ============================================================
# IMAGE MODE
# ============================================================

def _run_image(
    path: str,
    model: FaceModel,
    matcher: IdentityMatcher,
) -> None:

    if not path:
        print(
            "[R0] --path is required."
        )
        sys.exit(1)

    rgb = load_image(path)

    if rgb is None:
        sys.exit(1)

    faces = model.detect_faces(rgb)

    bgr = cv2.cvtColor(
        rgb,
        cv2.COLOR_RGB2BGR,
    )

    results: List[FaceResult] = []

    for face in faces:

        match = (
            matcher.find_best_match(
                face.embedding
            )
        )

        results.append(
            FaceResult(
                bbox=np.asarray(
                    face.bbox,
                    dtype=np.float32,
                ),
                name=match.name,
                similarity=float(
                    match.similarity
                ),
                det_score=float(
                    face.det_score
                ),
                is_known=bool(
                    match.is_known
                ),
                person_id=match.person_id,
                frame_id=0,
                velocity=np.zeros(
                    2,
                    dtype=np.float32,
                ),
            )
        )

    bgr = draw_results(
        bgr,
        results,
        0,
    )

    cv2.imshow(
        "R0 - Image",
        bgr,
    )

    print(
        "[R0] Press any key to close."
    )

    cv2.waitKey(0)
    cv2.destroyAllWindows()


# ============================================================
# VIDEO MODE
# ============================================================

def _run_video(
    path: str,
    model: FaceModel,
    matcher: IdentityMatcher,
) -> None:

    if not path:
        print(
            "[R0] --path is required."
        )
        sys.exit(1)

    print(
        f"[R0] Processing video: {path}"
    )

    tracker = []
    frame_count = 0

    for frame_idx, rgb in iter_video_frames(
        path,
        skip=FRAME_SKIP,
    ):

        frame_count += 1

        if frame_count % DETECTION_INTERVAL == 0:

            faces = model.detect_faces(
                rgb
            )

            detections = []

            for face in faces:

                match = (
                    matcher.find_best_match(
                        face.embedding
                    )
                )

                detections.append(
                    FaceResult(
                        bbox=np.asarray(
                            face.bbox,
                            dtype=np.float32,
                        ),
                        name=match.name,
                        similarity=float(
                            match.similarity
                        ),
                        det_score=float(
                            face.det_score
                        ),
                        is_known=bool(
                            match.is_known
                        ),
                        person_id=match.person_id,
                        frame_id=frame_idx,
                        velocity=np.zeros(
                            2,
                            dtype=np.float32,
                        ),
                    )
                )

            # Simple track update for video mode.
            tracker = detections

        bgr = cv2.cvtColor(
            rgb,
            cv2.COLOR_RGB2BGR,
        )

        bgr = draw_results(
            bgr,
            tracker,
            frame_idx,
        )

        cv2.imshow(
            "R0 - Video",
            bgr,
        )

        if (
            cv2.waitKey(1) & 0xFF
            == ord("q")
        ):
            break

    cv2.destroyAllWindows()


# ============================================================
# RTSP MODE
# ============================================================

def _run_rtsp(
    model: FaceModel,
    matcher: IdentityMatcher,
    log_events: bool,
) -> None:

    if not RTSP_URL:
        print(
            "[R0] RTSP_URL is not set."
        )
        print(
            "Add RTSP_URL to your environment."
        )
        sys.exit(1)

    print()
    print("=" * 70)
    print(
        "          R0 LOW-LATENCY LIVE CCTV FRS"
    )
    print("=" * 70)
    print(
        f"RTSP URL           : {RTSP_URL}"
    )
    print(
        f"Display size       : "
        f"{DISPLAY_WIDTH}x{DISPLAY_HEIGHT}"
    )
    print(
        f"GPU detection      : every "
        f"{DETECTION_INTERVAL} frames"
    )
    print(
        f"Tracker hold       : "
        f"{MAX_RESULT_AGE_SECONDS:.1f} seconds"
    )
    print(
        "Press Q to quit.  Press P to log reading to Excel."
    )
    print("=" * 70)

    # ── Initialize single-sheet evaluation Excel ────────────────
    try:
        _init_evaluation_excel()
    except Exception as _exc:
        print(
            f"[Excel] Could not init Excel file: {_exc}"
        )

    state = SharedState()

    reader = RTSPReader(
        url=RTSP_URL,
        resize=(
            DISPLAY_WIDTH,
            DISPLAY_HEIGHT,
        ),
    )

    worker = FRSWorker(
        state=state,
        model=model,
        matcher=matcher,
        log_events=log_events,
        every=DETECTION_INTERVAL,
    )

    reader.start()
    worker.start()

    display_count = 0
    fps_start = time.perf_counter()
    display_fps = 0.0

    last_frame: Optional[
        np.ndarray
    ] = None

    last_camera_frame_id = 0

    # Snapshot counter for P-key logging
    snapshot_count = 0
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    try:

        while state.is_running():

            # ----------------------------------------------------
            # Get newest camera frame.
            # This operation never waits for FRS.
            # ----------------------------------------------------

            rgb = reader.get_frame(
                timeout=RTSP_TIMEOUT
            )

            if rgb is not None:

                last_camera_frame_id = (
                    state.update_frame(
                        rgb
                    )
                )

                last_frame = cv2.cvtColor(
                    rgb,
                    cv2.COLOR_RGB2BGR,
                )

            if last_frame is None:

                time.sleep(0.001)
                continue

            # ----------------------------------------------------
            # Get latest tracked results.
            # ----------------------------------------------------

            results = state.get_results(
                last_camera_frame_id
            )

            # ----------------------------------------------------
            # Display latest frame immediately.
            # ----------------------------------------------------

            display_frame = (
                last_frame.copy()
            )

            display_frame = draw_results(
                display_frame,
                results,
                last_camera_frame_id,
            )

            # ----------------------------------------------------
            # FPS
            # ----------------------------------------------------

            display_count += 1

            elapsed = (
                time.perf_counter()
                - fps_start
            )

            if elapsed >= 1.0:

                display_fps = (
                    display_count / elapsed
                )

                display_count = 0
                fps_start = time.perf_counter()

            # ----------------------------------------------------
            # Status HUD
            # ----------------------------------------------------

            cv2.putText(
                display_frame,
                f"CCTV: {display_fps:.1f} FPS",
                (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                display_frame,
                f"FRS: {state.frs_fps:.1f} FPS",
                (15, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                display_frame,
                f"Faces: {len(results)}",
                (15, 84),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                display_frame,
                "[P] Press P to Log to Excel",
                (15, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow(
                WINDOW_NAME,
                display_frame,
            )

            key = cv2.waitKey(1) & 0xFF

            # ------------------------------------------------
            # Q — quit
            # ------------------------------------------------
            if key == ord("q"):
                break

            # ------------------------------------------------
            # P — snapshot + log data to Excel on demand
            # ------------------------------------------------
            if key == ord("p") or key == ord("P"):

                snapshot_count += 1
                from datetime import datetime
                ts = datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )
                snap_name = (
                    f"snap_{ts}_{snapshot_count:04d}.jpg"
                )
                snap_path = os.path.join(
                    SNAPSHOT_DIR,
                    snap_name,
                )

                # Save the annotated frame as-is
                cv2.imwrite(
                    snap_path,
                    display_frame,
                )

                # Log to Excel in a background thread
                import threading as _thr
                _thr.Thread(
                    target=_save_to_excel,
                    args=(
                        results,
                        last_camera_frame_id,
                        snap_path,
                    ),
                    daemon=True,
                ).start()

                # Brief on-screen confirmation banner
                confirm = display_frame.copy()
                cv2.putText(
                    confirm,
                    f"CAPTURED & LOGGED: {snap_name}",
                    (15, DISPLAY_HEIGHT - 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow(WINDOW_NAME, confirm)
                cv2.waitKey(300)

                print(
                    f"[P] Snapshot captured and logged to Excel: {snap_path} ({len(results)} face(s))"
                )

    except KeyboardInterrupt:

        print(
            "\n[R0] Ctrl+C - stopping."
        )

    finally:

        state.stop()
        worker.stop()
        reader.stop()
        cv2.destroyAllWindows()

        print(
            "[R0] Done."
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Run R0 smooth live "
            "face recognition."
        )
    )

    parser.add_argument(
        "--source",
        choices=[
            "rtsp",
            "image",
            "video",
        ],
        default="rtsp",
        help=(
            "Input source. "
            "Default: rtsp"
        ),
    )

    parser.add_argument(
        "--path",
        default="",
        help=(
            "Image/video path. "
            "Not required for RTSP."
        ),
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=MATCH_THRESHOLD,
        help=(
            "Recognition threshold. "
            f"Default: {MATCH_THRESHOLD}"
        ),
    )

    parser.add_argument(
        "--no-log",
        action="store_true",
        help=(
            "Disable R&D recognition "
            "logging."
        ),
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    print(
        "[R0] Initializing database..."
    )

    try:
        db.init_db()
    except Exception as exc:
        print(
            f"[R0] Database error: {exc}"
        )
        sys.exit(1)

    # --------------------------------------------------------
    # FACE MODEL
    # --------------------------------------------------------

    print(
        "[R0] Loading face model..."
    )

    try:
        model = FaceModel()
    except Exception as exc:
        print(
            "[R0] Face model error:"
        )
        print(exc)
        sys.exit(1)

    # --------------------------------------------------------
    # GALLERY
    # --------------------------------------------------------

    print(
        "[R0] Loading gallery..."
    )

    try:
        embeddings, ids, names = (
            db.load_all_embeddings()
        )
    except Exception as exc:
        print(
            "[R0] Gallery loading error:"
        )
        print(exc)
        sys.exit(1)

    print(
        f"[R0] Gallery embeddings: "
        f"{len(embeddings)}"
    )

    print(
        f"[R0] Gallery names: "
        f"{names}"
    )

    matcher = IdentityMatcher(
        threshold=args.threshold
    )

    matcher.load_gallery(
        embeddings,
        ids,
        names,
    )

    if matcher.gallery_size == 0:
        print(
            "[R0] WARNING: No face "
            "embeddings were found."
        )

    print()
    print(
        "[R0] Starting..."
    )
    print(
        f"[R0] Source: {args.source}"
    )
    print(
        f"[R0] Threshold: "
        f"{args.threshold}"
    )

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    if args.source == "image":

        _run_image(
            path=args.path,
            model=model,
            matcher=matcher,
        )

    elif args.source == "video":

        _run_video(
            path=args.path,
            model=model,
            matcher=matcher,
        )

    else:

        _run_rtsp(
            model=model,
            matcher=matcher,
            log_events=(
                not args.no_log
            ),
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()