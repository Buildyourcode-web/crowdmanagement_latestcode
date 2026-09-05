"""
pipeline.py — R0 recognition pipeline.

Flow:

    Input (image / video / RTSP)
        ↓
    FaceModel.detect_faces()
        ↓
    Check detected faces
        ↓
    Face embedding
        ↓
    IdentityMatcher.find_best_match()
        ↓
    Draw bounding box + name
        ↓
    Optional PostgreSQL R&D event log
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from app.models.face_model import FaceModel, DetectedFace
from app.recognition.matcher import IdentityMatcher, MatchResult
from app.config import (
    LOG_RECOGNITION_EVENTS,
    SHOW_SIMILARITY,
)
from app.database import repository as db


# ============================================================
# COLORS
# ============================================================

COLOR_KNOWN = (0, 255, 0)       # Green
COLOR_UNKNOWN = (0, 165, 255)   # Orange


class R0Pipeline:
    """
    Standard R0 face-recognition pipeline.

    The pipeline itself does not load the model or database
    gallery. Those are supplied during initialization.
    """

    def __init__(
        self,
        model: FaceModel,
        matcher: IdentityMatcher,
        source: str = "rtsp",
        log_events: bool = LOG_RECOGNITION_EVENTS,
        show_similarity: bool = SHOW_SIMILARITY,
    ) -> None:

        self._model = model
        self._matcher = matcher
        self._source = source
        self._log = log_events
        self._show_sim = show_similarity
        self._frame_counter = 0

        print(
            f"[Pipeline] Initialized "
            f"source={self._source} "
            f"log_events={self._log}"
        )

    # ============================================================
    # MAIN FRAME PROCESSING
    # ============================================================

    def process_frame(
        self,
        rgb_frame: np.ndarray,
        frame_id: Optional[str] = None,
    ) -> np.ndarray:
        """
        Process one RGB frame.

        Steps:

            1. Receive RTSP/image frame.
            2. Detect faces.
            3. Generate 512-D embedding.
            4. Match against PostgreSQL gallery.
            5. Draw bounding box.
            6. Log recognition event.
        """

        # --------------------------------------------------------
        # Frame counter
        # --------------------------------------------------------

        self._frame_counter += 1

        fid = frame_id or str(self._frame_counter)

        # --------------------------------------------------------
        # Validate input frame
        # --------------------------------------------------------

        if rgb_frame is None:

            print(
                f"[PIPELINE ERROR] frame={fid} "
                f"received None frame"
            )

            return np.zeros(
                (540, 960, 3),
                dtype=np.uint8,
            )

        if not isinstance(rgb_frame, np.ndarray):

            print(
                f"[PIPELINE ERROR] frame={fid} "
                f"invalid frame type={type(rgb_frame)}"
            )

            return np.zeros(
                (540, 960, 3),
                dtype=np.uint8,
            )

        # --------------------------------------------------------
        # Frame information
        # --------------------------------------------------------

        if self._frame_counter <= 5 or self._frame_counter % 30 == 0:

            print(
                f"[FRAME] frame={fid} "
                f"shape={rgb_frame.shape} "
                f"dtype={rgb_frame.dtype}"
            )

        # --------------------------------------------------------
        # Face detection + embedding
        # --------------------------------------------------------

        try:

            faces = self._model.detect_faces(
                rgb_frame
            )

        except Exception as e:

            print(
                f"[DETECTION ERROR] frame={fid}: {e}"
            )

            bgr_error = cv2.cvtColor(
                rgb_frame,
                cv2.COLOR_RGB2BGR,
            )

            cv2.putText(
                bgr_error,
                "FACE DETECTION ERROR",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )

            return bgr_error

        # --------------------------------------------------------
        # DEBUG: FACE DETECTION RESULT
        # --------------------------------------------------------

        print(
            f"[PIPELINE] frame={fid} "
            f"shape={rgb_frame.shape} "
            f"dtype={rgb_frame.dtype} "
            f"faces_detected={len(faces)}"
        )

        # --------------------------------------------------------
        # Convert RGB → BGR for OpenCV display
        # --------------------------------------------------------

        bgr = cv2.cvtColor(
            rgb_frame,
            cv2.COLOR_RGB2BGR,
        )

        # --------------------------------------------------------
        # No faces detected
        # --------------------------------------------------------

        if len(faces) == 0:

            # Display useful status on CCTV window
            cv2.putText(
                bgr,
                "No face detected",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                COLOR_UNKNOWN,
                2,
            )

            return bgr

        # --------------------------------------------------------
        # Process every detected face
        # --------------------------------------------------------

        for face_index, face in enumerate(faces):

            print(
                f"[FACE] frame={fid} "
                f"face_index={face_index} "
                f"bbox={face.bbox.tolist()} "
                f"det_score={face.det_score:.4f}"
            )

            # ====================================================
            # CHECK LIVE EMBEDDING
            # ====================================================

            embedding = face.embedding

            if embedding is None:

                print(
                    f"[EMBEDDING ERROR] frame={fid} "
                    f"face_index={face_index}: embedding=None"
                )

                continue

            embedding = np.asarray(
                embedding,
                dtype=np.float32,
            )

            print(
                f"[EMBEDDING] frame={fid} "
                f"face_index={face_index} "
                f"shape={embedding.shape} "
                f"dtype={embedding.dtype} "
                f"size={embedding.size} "
                f"norm={np.linalg.norm(embedding):.6f}"
            )

            # ----------------------------------------------------
            # Validate embedding
            # ----------------------------------------------------

            if embedding.shape != (512,):

                print(
                    f"[EMBEDDING ERROR] frame={fid} "
                    f"expected=(512,) "
                    f"actual={embedding.shape}"
                )

                continue

            if not np.isfinite(embedding).all():

                print(
                    f"[EMBEDDING ERROR] frame={fid} "
                    f"embedding contains NaN/Inf"
                )

                continue

            embedding_norm = np.linalg.norm(
                embedding
            )

            if embedding_norm == 0:

                print(
                    f"[EMBEDDING ERROR] frame={fid} "
                    f"embedding norm is zero"
                )

                continue

            # ----------------------------------------------------
            # Normalize live embedding
            # ----------------------------------------------------

            embedding = (
                embedding / embedding_norm
            )

            # ====================================================
            # MATCH AGAINST DATABASE GALLERY
            # ====================================================

            try:

                result = self._matcher.find_best_match(
                    embedding
                )

            except Exception as e:

                print(
                    f"[MATCH ERROR] frame={fid} "
                    f"face_index={face_index}: {e}"
                )

                continue

            # ----------------------------------------------------
            # Recognition result
            # ----------------------------------------------------

            print(
                f"[RECOGNITION] frame={fid} "
                f"face_index={face_index} "
                f"name={result.name} "
                f"person_id={result.person_id} "
                f"similarity={result.similarity:.4f} "
                f"threshold={result.threshold:.4f} "
                f"known={result.is_known}"
            )

            # ====================================================
            # DRAW BOUNDING BOX + NAME
            # ====================================================

            self._annotate(
                bgr,
                face,
                result,
            )

            # ====================================================
            # DATABASE EVENT LOG
            # ====================================================

            if self._log:

                try:

                    db.log_recognition_event(
                        source=self._source,
                        predicted_name=result.name,
                        similarity=result.similarity,
                        threshold=result.threshold,
                        is_known=result.is_known,
                        person_id=result.person_id,
                        frame_id=fid,
                    )

                except Exception as e:

                    print(
                        f"[DB LOG ERROR] frame={fid}: {e}"
                    )

        # --------------------------------------------------------
        # Return annotated BGR frame
        # --------------------------------------------------------

        return bgr

    # ============================================================
    # DRAW RECOGNITION RESULT
    # ============================================================

    def _annotate(
        self,
        bgr: np.ndarray,
        face: DetectedFace,
        result: MatchResult,
    ) -> None:

        # --------------------------------------------------------
        # Bounding box
        # --------------------------------------------------------

        bbox = np.asarray(
            face.bbox,
            dtype=np.int32,
        ).flatten()

        if bbox.shape[0] != 4:

            print(
                f"[ANNOTATION ERROR] Invalid bbox: {bbox}"
            )

            return

        x1, y1, x2, y2 = (
            int(bbox[0]),
            int(bbox[1]),
            int(bbox[2]),
            int(bbox[3]),
        )

        # --------------------------------------------------------
        # Keep coordinates inside image
        # --------------------------------------------------------

        height, width = bgr.shape[:2]

        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(0, min(x2, width - 1))
        y2 = max(0, min(y2, height - 1))

        # --------------------------------------------------------
        # Color
        # --------------------------------------------------------

        color = (
            COLOR_KNOWN
            if result.is_known
            else COLOR_UNKNOWN
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
        )

        # --------------------------------------------------------
        # Name
        # --------------------------------------------------------

        label = str(result.name)

        if self._show_sim:

            label = (
                f"{result.name} "
                f"{result.similarity:.2f}"
            )

        # --------------------------------------------------------
        # Label background
        # --------------------------------------------------------

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2

        (
            text_width,
            text_height,
        ), baseline = cv2.getTextSize(
            label,
            font,
            font_scale,
            thickness,
        )

        label_y = max(
            y1 - 10,
            text_height + 5,
        )

        # Background rectangle
        cv2.rectangle(
            bgr,
            (
                x1,
                label_y - text_height - baseline - 5,
            ),
            (
                x1 + text_width + 8,
                label_y + 3,
            ),
            color,
            -1,
        )

        # Text
        cv2.putText(
            bgr,
            label,
            (x1 + 4, label_y - 2),
            font,
            font_scale,
            (0, 0, 0),
            thickness,
            cv2.LINE_AA,
        )

        # --------------------------------------------------------
        # Detection confidence
        # --------------------------------------------------------

        if face.det_score > 0:

            conf_label = (
                f"det:{face.det_score:.2f}"
            )

            cv2.putText(
                bgr,
                conf_label,
                (
                    x1,
                    min(
                        y2 + 20,
                        height - 5,
                    ),
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )