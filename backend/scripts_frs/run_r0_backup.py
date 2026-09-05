"""
run_r0.py — Execute the R0 baseline recognition pipeline.

Modes:
    --source rtsp       Live RTSP camera (URL from .env)
    --source image      Single image file
    --source video      Video file

Usage examples:
    python scripts/run_r0.py --source rtsp
    python scripts/run_r0.py --source image --path data/test/front.jpg
    python scripts/run_r0.py --source video --path data/test/clip.mp4

R0 is the baseline experiment:
    No pose augmentation.
    No 3D reconstruction.
    Standard buffalo_l embedding + cosine similarity.

Results are displayed on screen and optionally logged to the R&D SQLite database.
The logged events can later be used to compute:
    - Genuine/impostor score distributions
    - FAR / FRR curves
    - TAR @ FAR
    - Rank-1 accuracy per pose angle
"""

import argparse
import sys
import os
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import repository as db
from app.models.face_model import FaceModel
from app.recognition.matcher import IdentityMatcher
from app.pipeline import R0Pipeline
from app.input.rtsp_input import RTSPReader
from app.input.image_input import load_image
from app.input.video_input import iter_video_frames
from app.config import MATCH_THRESHOLD, FRAME_SKIP, RTSP_URL


def main() -> None:
    parser = argparse.ArgumentParser(description="Run R0 FRS baseline.")
    parser.add_argument(
        "--source",
        choices=["rtsp", "image", "video"],
        default="rtsp",
        help="Input source type.",
    )
    parser.add_argument(
        "--path",
        default="",
        help="Path to image or video file (required for --source image/video).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=MATCH_THRESHOLD,
        help=f"Match threshold (default: {MATCH_THRESHOLD}). Will be tuned experimentally.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Disable R&D event logging to SQLite.",
    )
    args = parser.parse_args()

    # ── Init ───────────────────────────────────────────────────────────────────
    db.init_db()

    print("[R0] Loading face model...")
    model = FaceModel()

    print("[R0] Loading gallery from R&D database...")
    embeddings, ids, names = db.load_all_embeddings()

    matcher = IdentityMatcher(threshold=args.threshold)
    matcher.load_gallery(embeddings, ids, names)

    if matcher.gallery_size == 0:
        print("[R0] WARNING: No enrolled people found.")
        print("     Enroll someone first:")
        print("     python scripts/enroll_person.py --name Person_001 --image path/to/face.jpg")

    pipeline = R0Pipeline(
        model=model,
        matcher=matcher,
        source=args.source,
        log_events=not args.no_log,
    )

    print(f"[R0] Starting — source={args.source}  threshold={args.threshold}")
    print("     Press Q to quit.\n")

    # ── Run ────────────────────────────────────────────────────────────────────
    if args.source == "image":
        _run_image(args.path, pipeline)

    elif args.source == "video":
        _run_video(args.path, pipeline)

    else:
        _run_rtsp(pipeline)


# ── Source handlers ────────────────────────────────────────────────────────────

def _run_image(path: str, pipeline: R0Pipeline) -> None:
    if not path:
        print("[R0] --path required for --source image")
        sys.exit(1)

    rgb = load_image(path)
    if rgb is None:
        sys.exit(1)

    annotated = pipeline.process_frame(rgb, frame_id=os.path.basename(path))

    cv2.imshow("R0 — Image", annotated)
    print("[R0] Press any key to close.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def _run_video(path: str, pipeline: R0Pipeline) -> None:
    if not path:
        print("[R0] --path required for --source video")
        sys.exit(1)

    print(f"[R0] Processing video: {path}")
    for frame_idx, rgb in iter_video_frames(path, skip=FRAME_SKIP):
        annotated = pipeline.process_frame(rgb, frame_id=f"frame_{frame_idx:06d}")

        cv2.imshow("R0 — Video", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


def _run_rtsp(pipeline: R0Pipeline) -> None:
    if not RTSP_URL:
        print("[R0] RTSP_URL is not set in .env")
        print("     Add:  RTSP_URL=rtsp://your_camera_url")
        sys.exit(1)

    reader = RTSPReader()
    reader.start()

    frame_count = 0
    try:
        while True:
            rgb = reader.get_frame(timeout=0.2)
            if rgb is None:
                continue

            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                # Still display the frame without running detection
                import numpy as np
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                cv2.imshow("R0 — RTSP", bgr)
            else:
                annotated = pipeline.process_frame(rgb, frame_id=f"rtsp_{frame_count}")
                cv2.imshow("R0 — RTSP", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except KeyboardInterrupt:
        print("\n[R0] Ctrl+C — stopping.")
    finally:
        reader.stop()
        cv2.destroyAllWindows()
        print("[R0] Done.")


if __name__ == "__main__":
    main()
