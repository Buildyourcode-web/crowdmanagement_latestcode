"""
benchmark_r0_gallery.py — R0 Multi-Identity Large-Scale Gallery Benchmark Script

Purpose:
    Test a folder of images (e.g. 3,100 photos) against an enrolled multi-identity gallery
    (e.g., Satish, Ram) to measure false acceptance rates, score distributions, and top matches.

    For every image:
    1. Detect face using InsightFace buffalo_l.
    2. Extract normalized 512-D embedding.
    3. Compute cosine similarity against ALL enrolled identities in the gallery.
    4. Find the best matching identity and score.
    5. Log all per-identity scores.

Usage:
    python scripts/benchmark_r0_gallery.py \\
        --testdir   data/test/3100_criminals/ \\
        --threshold 0.50

    Optional: specify enrollment images directly if not using local DB:
    python scripts/benchmark_r0_gallery.py \\
        --testdir data/test/3100_criminals/ \\
        --enroll  Satish=data/enrollment/satish_1.jpg \\
        --enroll  Ram=data/enrollment/ram_1.jpg

Output:
    data/results/r0_gallery_3100.csv
    Console summary + TOP 20 HIGHEST MATCHES table
"""

import argparse
import csv
import os
import sys
import datetime
import statistics
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from app.models.face_model import FaceModel
from app.input.image_input import load_image
from app.recognition.embedding import cosine_similarity, validate_embedding
from app.recognition.matcher import IdentityMatcher
from app.database import repository as db
from app.config import MATCH_THRESHOLD

# ── Supported image extensions ─────────────────────────────────────────────────
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def collect_images(folder: str) -> List[Path]:
    """Return sorted list of image paths in a folder (recursively)."""
    p = Path(folder)
    if not p.is_dir():
        print(f"[Benchmark] ERROR: Test folder not found: {folder}")
        sys.exit(1)
    images = sorted([f for f in p.glob("**/*") if f.suffix.lower() in IMG_EXTS and f.is_file()])
    return images


def parse_enroll_args(enroll_list: List[str], model: FaceModel) -> Dict[str, np.ndarray]:
    """
    Parse CLI enroll arguments formatted as Name=path/to/image.jpg
    Extracts embeddings for specified identities.
    """
    gallery = {}
    for entry in enroll_list:
        if "=" not in entry:
            print(f"[Benchmark] WARNING: Ignoring invalid --enroll argument: '{entry}'. Use format Name=path/to/image.jpg")
            continue
        name, path = entry.split("=", 1)
        name = name.strip()
        path = path.strip()

        print(f"[Benchmark] Extracting enrollment embedding for '{name}' from: {path}")
        rgb = load_image(path)
        if rgb is None:
            print(f"[Benchmark] ERROR: Cannot read enrollment image for '{name}' at: {path}")
            sys.exit(1)

        faces = model.detect_faces(rgb)
        if not faces:
            print(f"[Benchmark] ERROR: No face detected in enrollment image for '{name}'")
            sys.exit(1)

        if len(faces) > 1:
            faces.sort(key=lambda f: f.det_score, reverse=True)

        gallery[name] = faces[0].embedding
        print(f"[Benchmark] Enrolled '{name}' (det_score: {faces[0].det_score:.4f})")

    return gallery


def load_gallery_from_db() -> Dict[str, np.ndarray]:
    """Load enrolled identities and embeddings from local SQLite database."""
    embeddings, ids, names = db.load_all_embeddings()
    gallery = {}
    for name, emb in zip(names, embeddings):
        gallery[name] = emb
    return gallery


def determine_ground_truth(img_path: Path, known_names: List[str]) -> str:
    """
    Determine if the test image is a known genuine identity or an unknown impostor.
    Checks directory structure and filename prefixes.
    """
    path_str = str(img_path).lower()
    filename = img_path.name.lower()

    for name in known_names:
        n_lower = name.lower()
        if f"genuine/{n_lower}" in path_str or f"genuine\\{n_lower}" in path_str:
            return name
        if filename.startswith(f"{n_lower}_") or filename.startswith(f"{n_lower}-"):
            return name

    return "impostor"


def run_gallery_benchmark(
    model: FaceModel,
    gallery: Dict[str, np.ndarray],
    test_images: List[Path],
    threshold: float,
) -> List[dict]:
    """
    Run every test image against all identities in the gallery.
    """
    results = []
    names = list(gallery.keys())

    print(f"\n[Benchmark] Starting Gallery Test on {len(test_images)} images against {len(names)} identities: {names}")
    print(f"            Threshold: {threshold}\n")

    # Console Header
    header_names = "  ".join([f"{name:>10}" for name in names])
    print(f"  {'Image':<28} {'GT':<10} {header_names}  {'Best Match':<12} {'Score':>7}  {'Result':<8}")
    print(f"  {'-'*28} {'-'*10} {'-'*len(header_names)}  {'-'*12} {'-'*7}  {'-'*8}")

    for idx, img_path in enumerate(test_images, 1):
        gt = determine_ground_truth(img_path, names)
        display_name = img_path.name

        rgb = load_image(str(img_path))
        if rgb is None:
            record = {
                "image": display_name,
                "ground_truth": gt,
                "faces_detected": 0,
                "best_match_identity": "None",
                "best_match_score": 0.0,
                "accepted_at_threshold": "NO",
                "correct": "YES" if gt == "impostor" else "NO",
                "det_score": 0.0,
                "note": "cannot_read",
            }
            for n in names:
                record[f"sim_{n}"] = 0.0
            results.append(record)
            continue

        faces = model.detect_faces(rgb)

        if not faces:
            record = {
                "image": display_name,
                "ground_truth": gt,
                "faces_detected": 0,
                "best_match_identity": "None",
                "best_match_score": 0.0,
                "accepted_at_threshold": "NO",
                "correct": "YES" if gt == "impostor" else "NO",
                "det_score": 0.0,
                "note": "no_face_detected",
            }
            for n in names:
                record[f"sim_{n}"] = 0.0
            results.append(record)
            continue

        # If multiple faces detected, take highest confidence face
        if len(faces) > 1:
            faces.sort(key=lambda f: f.det_score, reverse=True)
            note = f"multi_face({len(faces)})"
        else:
            note = ""

        face = faces[0]

        # Compute cosine similarity against all gallery identities
        sims = {}
        best_name = "None"
        best_score = -1.0

        for n, emb in gallery.items():
            s = cosine_similarity(emb, face.embedding)
            sims[n] = s
            if s > best_score:
                best_score = s
                best_name = n

        accepted = best_score >= threshold
        accepted_str = "YES" if accepted else "NO"

        # Correctness logic
        if gt == "impostor":
            correct = not accepted
        else:
            correct = accepted and (best_name.lower() == gt.lower())

        record = {
            "image": display_name,
            "ground_truth": gt,
            "faces_detected": len(faces),
            "best_match_identity": best_name,
            "best_match_score": best_score,
            "accepted_at_threshold": accepted_str,
            "correct": "YES" if correct else "NO",
            "det_score": face.det_score,
            "note": note,
        }

        for n in names:
            record[f"sim_{n}"] = sims[n]

        results.append(record)

        # Print progress row
        sim_str = "  ".join([f"{sims[n]:>10.4f}" for n in names])
        res_label = f"[{best_name}]" if accepted else "[NO MATCH]"
        
        # Print progress every 100 images or for matches above threshold
        if idx % 100 == 0 or accepted or idx <= 10 or idx == len(test_images):
            print(
                f"  {display_name:<28} {gt:<10} {sim_str}  {best_name:<12} {best_score:>7.4f}  {res_label:<8}"
            )

    return results


def save_csv(results: List[dict], output_path: str, names: List[str], threshold: float) -> None:
    """Write results to CSV."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    base_fields = [
        "image", "ground_truth", "faces_detected", "best_match_identity",
        "best_match_score", "accepted_at_threshold", "correct", "det_score", "note"
    ]
    sim_fields = [f"sim_{n}" for n in names]
    fieldnames = base_fields + sim_fields

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["best_match_score"] = f"{r['best_match_score']:.4f}" if r["best_match_score"] is not None else ""
            row["det_score"] = f"{r['det_score']:.4f}" if r["det_score"] is not None else ""
            for n in names:
                row[f"sim_{n}"] = f"{r[f'sim_{n}']:.4f}" if r[f"sim_{n}"] is not None else ""
            writer.writerow(row)

    print(f"\n[Benchmark] CSV saved -> {output_path}")


def print_summary(results: List[dict], names: List[str], threshold: float) -> None:
    """Print multi-identity gallery test summary and TOP 20 matches table."""
    total = len(results)
    detected_records = [r for r in results if r["faces_detected"] > 0]
    no_face_records = [r for r in results if r["faces_detected"] == 0]

    print("\n" + "=" * 70)
    print("  R0 MULTI-IDENTITY GALLERY BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"  Total images tested    : {total}")
    print(f"  Faces detected         : {len(detected_records)}")
    print(f"  No face detected       : {len(no_face_records)}")
    print(f"  Decision threshold     : {threshold:.2f}")

    print("\n" + "─" * 70)
    print("  PER-IDENTITY IMPOSTOR / MATCH METRICS")
    print("─" * 70)
    print(f"  {'Identity':<15} {'Matches (>= threshold)':<24} {'Max Score':<12} {'Mean Score':<12}")
    print(f"  {'-'*15} {'-'*24} {'-'*12} {'-'*12}")

    overall_max_score = -1.0
    overall_max_image = ""
    overall_max_identity = ""

    for n in names:
        scores = [r[f"sim_{n}"] for r in detected_records]
        matches = [r for r in detected_records if r[f"sim_{n}"] >= threshold]
        
        max_score = max(scores) if scores else 0.0
        mean_score = statistics.mean(scores) if scores else 0.0

        if max_score > overall_max_score:
            overall_max_score = max_score
            top_rec = max(detected_records, key=lambda r: r[f"sim_{n}"])
            overall_max_image = top_rec["image"]
            overall_max_identity = n

        print(f"  {n:<15} {len(matches):<24} {max_score:>10.4f}  {mean_score:>10.4f}")

    print("\n" + "─" * 70)
    print(f"  Overall Highest Score  : {overall_max_score:.4f} ({overall_max_identity} on {overall_max_image})")
    print("─" * 70)

    # ── TOP 20 HIGHEST MATCHES TABLE ─────────────────────────────────────────
    sorted_detected = sorted(detected_records, key=lambda r: r["best_match_score"], reverse=True)
    top_20 = sorted_detected[:20]

    print("\n" + "=" * 70)
    print("  TOP 20 HIGHEST MATCHES")
    print("=" * 70)
    print(f"  {'Rank':<5} {'Image':<30} {'Matched Identity':<18} {'Score':>8}  {'Accepted?'}")
    print(f"  {'-'*5} {'-'*30} {'-'*18} {'-'*8}  {'-'*9}")

    for rank, r in enumerate(top_20, 1):
        acc = f"[YES]" if r["best_match_score"] >= threshold else "[NO]"
        print(f"  {rank:<5} {r['image']:<30} {r['best_match_identity']:<18} {r['best_match_score']:>8.4f}  {acc}")

    print("=" * 70)
    print("\n  [INFO] Benchmark complete. Review CSV for detailed distributions.")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="R0 Multi-Identity Large-Scale Gallery Benchmark"
    )
    parser.add_argument(
        "--testdir",
        required=True,
        help="Folder containing test images (e.g. data/test/3100_criminals/).",
    )
    parser.add_argument(
        "--enroll",
        action="append",
        default=[],
        help="Specify enrollment image in format Name=path/to/image.jpg. Can be passed multiple times.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=MATCH_THRESHOLD,
        help=f"Match threshold (default: {MATCH_THRESHOLD}).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output CSV path. Default: data/results/r0_gallery_benchmark.csv",
    )
    args = parser.parse_args()

    output_csv = args.output or "data/results/r0_gallery_benchmark.csv"

    print("=" * 70)
    print("  FRS R&D — R0 Large-Scale Multi-Identity Gallery Benchmark")
    print("=" * 70)
    print(f"  Test folder : {args.testdir}")
    print(f"  Threshold   : {args.threshold}")
    print(f"  Output CSV  : {output_csv}")
    print("=" * 70)

    print("\n[Benchmark] Loading InsightFace buffalo_l...")
    model = FaceModel()

    # ── Load Gallery ───────────────────────────────────────────────────────────
    gallery = {}
    if args.enroll:
        gallery = parse_enroll_args(args.enroll, model)
    else:
        db.init_db()
        gallery = load_gallery_from_db()

    if not gallery:
        print("[Benchmark] ERROR: Gallery is empty!")
        print("             Please either enroll identities into SQLite DB using enroll_person.py,")
        print("             or pass enrollment images via CLI:")
        print("             --enroll Satish=data/enrollment/satish_1.jpg --enroll Ram=data/enrollment/ram_1.jpg")
        sys.exit(1)

    print(f"\n[Benchmark] Active Gallery ({len(gallery)} identities): {list(gallery.keys())}")

    # ── Collect test images ────────────────────────────────────────────────────
    test_images = collect_images(args.testdir)
    print(f"[Benchmark] Found {len(test_images)} test images in {args.testdir}")

    # ── Run benchmark ──────────────────────────────────────────────────────────
    results = run_gallery_benchmark(
        model=model,
        gallery=gallery,
        test_images=test_images,
        threshold=args.threshold,
    )

    # ── Save CSV & Print Summary ───────────────────────────────────────────────
    save_csv(results, output_csv, list(gallery.keys()), args.threshold)
    print_summary(results, list(gallery.keys()), args.threshold)


if __name__ == "__main__":
    main()
