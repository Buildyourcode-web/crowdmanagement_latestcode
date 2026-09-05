"""
enroll_person.py — Enroll a person into the local R&D database.

Usage:
    python scripts/enroll_person.py --name "Person_001" --image "data/enrollment/person_001.jpg"

What this does:
    1. Load the image.
    2. Detect exactly one face (warn if zero or more than one).
    3. Generate a normalized 512-D embedding via buffalo_l.
    4. Store person + embedding in the local SQLite R&D database.

What this does NOT do:
    - Connect to production database.
    - Send emails.
    - Store credentials.
    - Implement 1-to-3 multi-image identity templates (that is future R&D).
"""

import argparse
import sys
import os

# Ensure the project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import repository as db
from app.models.face_model import FaceModel
from app.input.image_input import load_image
from app.config import MATCH_THRESHOLD


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enroll a person into the FRS R&D local database."
    )
    parser.add_argument(
        "--name",
        required=True,
        help='Identity label, e.g. "Person_001". Must be unique.',
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to enrollment image (frontal face recommended).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="If person already exists, add another embedding (for future multi-shot).",
    )
    args = parser.parse_args()

    # ── Initialise DB ──────────────────────────────────────────────────────────
    db.init_db()

    # ── Load image ─────────────────────────────────────────────────────────────
    print(f"[Enroll] Loading image: {args.image}")
    rgb = load_image(args.image)
    if rgb is None:
        print("[Enroll] ERROR: Cannot read image. Aborting.")
        sys.exit(1)

    # ── Detect face ────────────────────────────────────────────────────────────
    print("[Enroll] Loading face model (first run may take a moment)...")
    model = FaceModel()
    faces = model.detect_faces(rgb)

    if len(faces) == 0:
        print("[Enroll] ERROR: No face detected in the image.")
        print("         Please use a clear frontal face photograph.")
        sys.exit(1)

    if len(faces) > 1:
        print(f"[Enroll] WARNING: {len(faces)} faces detected. Using the highest-confidence face.")
        faces.sort(key=lambda f: f.det_score, reverse=True)

    face = faces[0]
    print(f"[Enroll] Face detected — confidence: {face.det_score:.3f}")

    # ── Get or create person ───────────────────────────────────────────────────
    existing = db.get_person_by_name(args.name)
    if existing and not args.force:
        print(f"[Enroll] ERROR: '{args.name}' already exists in the database.")
        print("         Use --force to add another embedding for the same person.")
        sys.exit(1)

    if existing:
        person_id = existing["id"]
        print(f"[Enroll] Adding additional embedding to existing person: {args.name} (id={person_id})")
    else:
        person_id = db.insert_person(args.name)
        print(f"[Enroll] Created new person: {args.name} (id={person_id})")

    # ── Store embedding ────────────────────────────────────────────────────────
    emb_id = db.insert_embedding(
        person_id=person_id,
        embedding=face.embedding,
        image_path=os.path.abspath(args.image),
    )

    print(f"[Enroll] ✅ Enrollment complete.")
    print(f"         Person  : {args.name}")
    print(f"         ID      : {person_id}")
    print(f"         Emb ID  : {emb_id}")
    print(f"         Dim     : {face.embedding.shape[0]}")
    print(f"         Det conf: {face.det_score:.4f}")
    print()
    print("You can now run R0:")
    print("  python scripts/run_r0.py --source rtsp")
    print("  python scripts/run_r0.py --source image --path data/test/test_face.jpg")


if __name__ == "__main__":
    main()
