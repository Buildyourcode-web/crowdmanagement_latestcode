"""
FRS R&D — R0 RTSP Live Recognition Test

Purpose:
    Given ONE enrollment image and an RTSP CCTV stream,
    continuously detect faces and compare them against
    the enrollment embedding.

Usage:
    python scripts/benchmark_r0.py ^
        --enrollment data/enrollment/ram_1.jpg ^
        --rtsp "rtsp://username:password@IP:PORT/stream" ^
        --name "Satish" ^
        --threshold 0.50

Controls:
    Q / ESC  -> Exit
"""

import argparse
import os
import sys
import time
from typing import Optional

# Project root on path
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import cv2
import numpy as np

from app.models.face_model import FaceModel
from app.input.image_input import load_image
from app.recognition.embedding import cosine_similarity, validate_embedding
from app.config import MATCH_THRESHOLD


# ============================================================
# Enrollment
# ============================================================

def get_enrollment_embedding(
    model: FaceModel,
    image_path: str
):
    """
    Load enrollment image and extract one face embedding.
    """

    print(f"\n[RTSP-FRS] Loading enrollment image: {image_path}")

    rgb = load_image(image_path)

    if rgb is None:
        print("[RTSP-FRS] ERROR: Cannot read enrollment image.")
        sys.exit(1)

    faces = model.detect_faces(rgb)

    if len(faces) == 0:
        print("[RTSP-FRS] ERROR: No face detected in enrollment image.")
        print("           Use a clear frontal image.")
        sys.exit(1)

    if len(faces) > 1:
        print(
            f"[RTSP-FRS] WARNING: {len(faces)} faces found "
            "in enrollment image."
        )
        print("           Using highest-confidence face.")

        faces.sort(
            key=lambda f: f.det_score,
            reverse=True
        )

    face = faces[0]

    if not validate_embedding(face.embedding):
        print("[RTSP-FRS] ERROR: Invalid enrollment embedding.")
        sys.exit(1)

    print(
        f"[RTSP-FRS] Enrollment face detected "
        f"(det_score={face.det_score:.4f})"
    )

    print(
        f"[RTSP-FRS] Enrollment embedding dimension: "
        f"{len(face.embedding)}"
    )

    return face.embedding


# ============================================================
# RTSP connection
# ============================================================

def open_rtsp(rtsp_url: str):
    """
    Open RTSP stream using TCP transport.
    """

    print("\n[RTSP-FRS] Opening RTSP stream...")
    print(f"[RTSP-FRS] URL: {rtsp_url}")

    # Force FFmpeg TCP transport.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        "rtsp_transport;tcp"
    )

    cap = cv2.VideoCapture(
        rtsp_url,
        cv2.CAP_FFMPEG
    )

    # Reduce buffering where supported.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("[RTSP-FRS] ERROR: Cannot open RTSP stream.")
        return None

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print("[RTSP-FRS] RTSP connected successfully.")
    print(f"[RTSP-FRS] Resolution : {width} x {height}")
    print(f"[RTSP-FRS] FPS        : {fps}")

    return cap


# ============================================================
# Live RTSP recognition
# ============================================================

def run_rtsp(
    model: FaceModel,
    enrollment_embedding: np.ndarray,
    rtsp_url: str,
    name: str,
    threshold: float,
    display: bool = True,
    process_every: int = 1,
):
    """
    Read frames continuously from RTSP and perform face recognition.
    """

    cap = open_rtsp(rtsp_url)

    if cap is None:
        return

    frame_count = 0
    recognized_count = 0

    previous_results = []

    start_time = time.time()
    last_print_time = start_time

    print("\n" + "=" * 70)
    print("  LIVE RTSP FACE RECOGNITION STARTED")
    print("=" * 70)
    print(f"  Identity       : {name}")
    print(f"  Threshold      : {threshold}")
    print(f"  Process every  : {process_every} frame(s)")
    print("  Press Q or ESC to stop")
    print("=" * 70 + "\n")

    while True:

        ret, frame = cap.read()

        if not ret or frame is None:
            print(
                "[RTSP-FRS] WARNING: Failed to read frame. "
                "Trying to reconnect..."
            )

            cap.release()
            time.sleep(1)

            cap = open_rtsp(rtsp_url)

            if cap is None:
                time.sleep(2)
                continue

            continue

        frame_count += 1

        # ----------------------------------------------------
        # Process selected frames
        # ----------------------------------------------------

        if frame_count % process_every == 0:

            # OpenCV frame is BGR.
            # InsightFace pipeline expects RGB.
            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            faces = model.detect_faces(rgb)

            current_results = []

            # ------------------------------------------------
            # No faces
            # ------------------------------------------------

            if len(faces) == 0:
                current_results = []

            else:

                # ------------------------------------------------
                # Process every detected face
                # ------------------------------------------------

                for face in faces:

                    if not validate_embedding(face.embedding):
                        continue

                    similarity = cosine_similarity(
                        enrollment_embedding,
                        face.embedding
                    )

                    recognized = similarity >= threshold

                    current_results.append(
                        {
                            "bbox": face.bbox.astype(int),
                            "similarity": similarity,
                            "recognized": recognized,
                            "det_score": face.det_score,
                        }
                    )

                    if recognized:
                        recognized_count += 1

                    # Console output
                    status = "MATCH" if recognized else "UNKNOWN"

                    print(
                        f"[FRS] {status:<7} "
                        f"Similarity={similarity:.4f} "
                        f"Detection={face.det_score:.4f}"
                    )

            previous_results = current_results

        # ----------------------------------------------------
        # Draw results
        # ----------------------------------------------------

        if display:

            for result in previous_results:

                x1, y1, x2, y2 = result["bbox"]

                similarity = result["similarity"]
                recognized = result["recognized"]
                det_score = result["det_score"]

                if recognized:
                    label = (
                        f"{name} | "
                        f"SIM: {similarity:.3f}"
                    )
                else:
                    label = (
                        f"UNKNOWN | "
                        f"SIM: {similarity:.3f}"
                    )

                # OpenCV rectangle
                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0) if recognized else (0, 0, 255),
                    2
                )

                # Label background
                (text_w, text_h), baseline = cv2.getTextSize(
                    label,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    2
                )

                label_y = max(y1 - 10, text_h + 10)

                cv2.rectangle(
                    frame,
                    (x1, label_y - text_h - baseline - 5),
                    (x1 + text_w + 5, label_y + 5),
                    (0, 0, 0),
                    -1
                )

                cv2.putText(
                    frame,
                    label,
                    (x1 + 2, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0) if recognized else (0, 0, 255),
                    2,
                    cv2.LINE_AA
                )

                # Detection score
                det_text = f"DET: {det_score:.3f}"

                cv2.putText(
                    frame,
                    det_text,
                    (x1, y2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA
                )

            # ------------------------------------------------
            # Status information
            # ------------------------------------------------

            elapsed = time.time() - start_time

            actual_fps = (
                frame_count / elapsed
                if elapsed > 0
                else 0
            )

            status_text = (
                f"Camera FPS: {actual_fps:.1f} | "
                f"Faces: {len(previous_results)} | "
                f"Target: {name}"
            )

            cv2.rectangle(
                frame,
                (0, 0),
                (frame.shape[1], 35),
                (0, 0, 0),
                -1
            )

            cv2.putText(
                frame,
                status_text,
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA
            )

            cv2.imshow(
                "FRS - RTSP Live Recognition",
                frame
            )

        # ----------------------------------------------------
        # Exit
        # ----------------------------------------------------

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q") or key == 27:
            print("\n[RTSP-FRS] Stopping...")
            break

        # Print FPS periodically
        now = time.time()

        if now - last_print_time >= 10:

            elapsed = now - start_time

            actual_fps = (
                frame_count / elapsed
                if elapsed > 0
                else 0
            )

            print(
                f"\n[RTSP-FRS] Frames={frame_count} "
                f"FPS={actual_fps:.2f} "
                f"Recognized={recognized_count}\n"
            )

            last_print_time = now

    cap.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 70)
    print("  RTSP TEST FINISHED")
    print("=" * 70)
    print(f"Frames processed : {frame_count}")
    print(f"Matches          : {recognized_count}")
    print("=" * 70)


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="FRS R0 Live RTSP Face Recognition"
    )

    parser.add_argument(
        "--enrollment",
        required=True,
        help="Path to enrollment image."
    )

    parser.add_argument(
        "--rtsp",
        required=True,
        help="RTSP CCTV URL."
    )

    parser.add_argument(
        "--name",
        required=True,
        help='Identity name, e.g. "Satish".'
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=MATCH_THRESHOLD,
        help=f"Face match threshold. Default: {MATCH_THRESHOLD}"
    )

    parser.add_argument(
        "--process-every",
        type=int,
        default=1,
        help="Process every Nth frame. Default: 1"
    )

    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Run without OpenCV display window."
    )

    args = parser.parse_args()

    if args.process_every < 1:
        print("[RTSP-FRS] ERROR: --process-every must be >= 1")
        sys.exit(1)

    print("=" * 70)
    print("  FRS R&D — R0 RTSP LIVE TEST")
    print("=" * 70)

    print(f"  Identity       : {args.name}")
    print(f"  Enrollment     : {args.enrollment}")
    print(f"  RTSP           : {args.rtsp}")
    print(f"  Threshold      : {args.threshold}")
    print(f"  Process every  : {args.process_every}")
    print("=" * 70)

    # --------------------------------------------------------
    # Load InsightFace
    # --------------------------------------------------------

    print("\n[RTSP-FRS] Loading InsightFace buffalo_l...")

    model = FaceModel()

    # --------------------------------------------------------
    # Generate enrollment embedding
    # --------------------------------------------------------

    enrollment_embedding = get_enrollment_embedding(
        model,
        args.enrollment
    )

    # --------------------------------------------------------
    # Run RTSP
    # --------------------------------------------------------

    run_rtsp(
        model=model,
        enrollment_embedding=enrollment_embedding,
        rtsp_url=args.rtsp,
        name=args.name,
        threshold=args.threshold,
        display=not args.no_display,
        process_every=args.process_every,
    )


if __name__ == "__main__":
    main()