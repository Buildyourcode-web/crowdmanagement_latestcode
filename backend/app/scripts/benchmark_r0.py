"""
benchmark_r0.py — R0 Pose Benchmark Script

Purpose:
    Given ONE enrollment image and a folder of test images (different poses),
    compute similarity of each test image against the enrollment embedding.

    Tracks genuine vs impostor test cases separately to compute:
    - Genuine similarity distribution (min, max, mean, median)
    - Impostor similarity distribution (min, max, mean, median)
    - Classification metrics (TP, FN, TN, FP, TAR, FAR, FRR)

Usage:
    python scripts/benchmark_r0.py \\
        --enrollment data/enrollment/satish_1.jpg \\
        --testdir    data/test/satish/ \\
        --name       "Satish" \\
        --threshold  0.50

Output:
    data/results/r0_satish.csv
    Console summary table with genuine/impostor breakdown
"""

import argparse
import csv
import os
import sys
import datetime
import statistics
from pathlib import Path
from typing import List, Tuple, Optional

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from app.models.face_model import FaceModel
from app.input.image_input import load_image
from app.recognition.embedding import cosine_similarity, validate_embedding
from app.config import MATCH_THRESHOLD

# ── Supported image extensions ─────────────────────────────────────────────────
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def collect_images(folder: str) -> List[Path]:
    """Return sorted list of image paths in a folder (including subdirectories)."""
    p = Path(folder)
    if not p.is_dir():
        print(f"[Benchmark] ERROR: Test folder not found: {folder}")
        sys.exit(1)
    images = sorted([f for f in p.glob("**/*") if f.suffix.lower() in IMG_EXTS and f.is_file()])
    return images


def determine_ground_truth(img_path: Path, genuine_prefix: str) -> str:
    """
    Determine whether an image is genuine or impostor.
    1. Parent directory named 'genuine' or 'impostor'
    2. Filename starting with genuine_prefix
    """
    parent_name = img_path.parent.name.lower()
    if parent_name == "genuine":
        return "genuine"
    if parent_name == "impostor":
        return "impostor"

    if genuine_prefix and img_path.name.lower().startswith(genuine_prefix.lower()):
        return "genuine"

    return "impostor"


def get_enrollment_embedding(
    model: FaceModel, image_path: str
) -> Tuple[np.ndarray, float]:
    """
    Load enrollment image and extract embedding.

    Returns:
        (embedding, det_score)
    """
    print(f"\n[Benchmark] Loading enrollment image: {image_path}")
    rgb = load_image(image_path)
    if rgb is None:
        print("[Benchmark] ERROR: Cannot read enrollment image.")
        sys.exit(1)

    faces = model.detect_faces(rgb)

    if len(faces) == 0:
        print("[Benchmark] ERROR: No face detected in enrollment image.")
        print("             Use a clear frontal photo with visible face.")
        sys.exit(1)

    if len(faces) > 1:
        print(f"[Benchmark] WARNING: {len(faces)} faces found in enrollment image.")
        print("             Using highest-confidence face.")
        faces.sort(key=lambda f: f.det_score, reverse=True)

    face = faces[0]
    print(f"[Benchmark] Enrollment face - det_score: {face.det_score:.4f}")
    return face.embedding, face.det_score


def run_benchmark(
    model: FaceModel,
    enrollment_embedding: np.ndarray,
    test_images: List[Path],
    threshold: float,
    name: str,
    genuine_prefix: str,
) -> List[dict]:
    """
    Run each test image against the enrollment embedding.

    Returns list of result dicts, one per image.
    """
    results = []

    print(f"\n[Benchmark] Running {len(test_images)} test images against enrollment...")
    print(f"            Threshold      : {threshold}")
    print(f"            Identity       : {name}")
    print(f"            Genuine prefix : '{genuine_prefix}'\n")

    # Header
    print(f"  {'Image':<25} {'Type':<9} {'Similarity':>10}  {'Result':<8}  {'Correct':<8}  {'Det Score':>9}  {'Note'}")
    print(f"  {'-'*25} {'-'*9} {'-'*10}  {'-'*8}  {'-'*8}  {'-'*9}  {'-'*15}")

    for img_path in test_images:
        gt = determine_ground_truth(img_path, genuine_prefix)
        rgb = load_image(str(img_path))

        display_name = img_path.name

        # ── Cannot read ──────────────────────────────────────────────────────
        if rgb is None:
            record = _make_record(
                image=display_name,
                ground_truth=gt,
                similarity=None,
                recognized=None,
                correct=False,
                det_score=None,
                note="cannot_read",
            )
            results.append(record)
            print(f"  {display_name:<25} {gt:<9} {'':>10}  {'ERROR':<8}  {'NO':<8}  {'':>9}  cannot read file")
            continue

        faces = model.detect_faces(rgb)

        # ── No face ──────────────────────────────────────────────────────────
        if len(faces) == 0:
            record = _make_record(
                image=display_name,
                ground_truth=gt,
                similarity=None,
                recognized=None,
                correct=False,
                det_score=None,
                note="no_face_detected",
            )
            results.append(record)
            print(f"  {display_name:<25} {gt:<9} {'':>10}  {'NO FACE':<8}  {'NO':<8}  {'':>9}  no face detected")
            continue

        # ── Multiple faces: use highest confidence ────────────────────────
        if len(faces) > 1:
            faces.sort(key=lambda f: f.det_score, reverse=True)
            note = f"multi_face({len(faces)})"
        else:
            note = ""

        face = faces[0]

        if not validate_embedding(face.embedding):
            record = _make_record(
                image=display_name,
                ground_truth=gt,
                similarity=None,
                recognized=None,
                correct=False,
                det_score=face.det_score,
                note="invalid_embedding",
            )
            results.append(record)
            print(f"  {display_name:<25} {gt:<9} {'':>10}  {'ERROR':<8}  {'NO':<8}  {face.det_score:>9.4f}  invalid embedding")
            continue

        sim = cosine_similarity(enrollment_embedding, face.embedding)
        recognized = sim >= threshold
        result_label = "[YES]" if recognized else "[NO]"

        # Decision correctness
        if gt == "genuine":
            correct = recognized
        else:
            correct = not recognized

        correct_label = "YES" if correct else "NO"

        record = _make_record(
            image=display_name,
            ground_truth=gt,
            similarity=sim,
            recognized=recognized,
            correct=correct,
            det_score=face.det_score,
            note=note,
        )
        results.append(record)

        print(
            f"  {display_name:<25} {gt:<9} {sim:>10.4f}  {result_label:<8}  "
            f"{correct_label:<8}  {face.det_score:>9.4f}  {note}"
        )

    return results


def save_csv(results: List[dict], output_path: str, name: str, threshold: float) -> None:
    """Write results to CSV for later analysis and R1 comparison."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fieldnames = [
        "image", "ground_truth", "similarity", "recognized", "correct",
        "det_score", "note", "threshold", "identity", "experiment"
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["similarity"] = f"{r['similarity']:.4f}" if r["similarity"] is not None else ""
            row["det_score"]  = f"{r['det_score']:.4f}"  if r["det_score"]  is not None else ""
            row["threshold"]  = threshold
            row["identity"]   = name
            row["experiment"] = "R0"
            writer.writerow(row)

    print(f"\n[Benchmark] Results saved -> {output_path}")


def print_summary(results: List[dict], threshold: float) -> None:
    """Print clean summary with separate Genuine, Impostor, and Classification stats."""
    genuine_all = [r for r in results if r["ground_truth"] == "genuine"]
    impostor_all = [r for r in results if r["ground_truth"] == "impostor"]

    genuine_valid = [r for r in genuine_all if r["similarity"] is not None]
    impostor_valid = [r for r in impostor_all if r["similarity"] is not None]

    # Genuine breakdown
    genuine_count = len(genuine_all)
    genuine_tp = sum(1 for r in genuine_valid if r["recognized"] == "YES")
    genuine_fn = genuine_count - genuine_tp
    genuine_rate = (genuine_tp / genuine_count * 100.0) if genuine_count > 0 else 0.0

    genuine_sims = [r["similarity"] for r in genuine_valid]

    # Impostor breakdown
    impostor_count = len(impostor_all)
    impostor_fp = sum(1 for r in impostor_valid if r["recognized"] == "YES")
    impostor_tn = impostor_count - impostor_fp
    impostor_rej_rate = (impostor_tn / impostor_count * 100.0) if impostor_count > 0 else 0.0

    impostor_sims = [r["similarity"] for r in impostor_valid]

    # Classification Metrics
    tp = genuine_tp
    fn = genuine_fn
    tn = impostor_tn
    fp = impostor_fp

    tar = (tp / (tp + fn) * 100.0) if (tp + fn) > 0 else 0.0
    far = (fp / (fp + tn) * 100.0) if (fp + tn) > 0 else 0.0
    frr = (fn / (tp + fn) * 100.0) if (tp + fn) > 0 else 0.0

    print("\n" + "=" * 60)
    print("  R0 BENCHMARK SUMMARY")
    print("=" * 60)

    print("\nGENUINE")
    print("-------")
    print(f"Images tested       : {genuine_count}")
    print(f"Recognized          : {genuine_tp}")
    print(f"Recognition rate    : {genuine_rate:.2f}%")
    if genuine_sims:
        print(f"Similarity min      : {min(genuine_sims):.4f}")
        print(f"Similarity max      : {max(genuine_sims):.4f}")
        print(f"Similarity mean     : {statistics.mean(genuine_sims):.4f}")
        print(f"Similarity median   : {statistics.median(genuine_sims):.4f}")
    else:
        print("Similarity stats    : N/A")

    print("\nIMPOSTOR")
    print("--------")
    print(f"Images tested       : {impostor_count}")
    print(f"False accepts       : {impostor_fp}")
    print(f"Rejection rate      : {impostor_rej_rate:.2f}%")
    if impostor_sims:
        print(f"Similarity min      : {min(impostor_sims):.4f}")
        print(f"Similarity max      : {max(impostor_sims):.4f}")
        print(f"Similarity mean     : {statistics.mean(impostor_sims):.4f}")
        print(f"Similarity median   : {statistics.median(impostor_sims):.4f}")
    else:
        print("Similarity stats    : N/A")

    print("\nCLASSIFICATION")
    print("--------------")
    print(f"TP : {tp}")
    print(f"FN : {fn}")
    print(f"TN : {tn}")
    print(f"FP : {fp}")
    print()
    print(f"TAR : {tar:.2f}%")
    print(f"FAR : {far:.2f}%")
    print(f"FRR : {frr:.2f}%")
    print("=" * 60)
    print()
    print("  [INFO] These numbers are the R0 baseline.")
    print("         R1 (Pose-TTA) will run the SAME images and we compare.")
    print("=" * 60)


def _make_record(image, ground_truth, similarity, recognized, correct, det_score, note=""):
    return {
        "image": image,
        "ground_truth": ground_truth,
        "similarity": similarity,
        "recognized": ("YES" if recognized else "NO") if recognized is not None else "ERROR",
        "correct": "YES" if correct else "NO",
        "det_score": det_score,
        "note": note,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="R0 Pose Benchmark — test one enrollment image against a folder of poses."
    )
    parser.add_argument(
        "--enrollment",
        required=True,
        help="Path to the enrollment (front-facing) image.",
    )
    parser.add_argument(
        "--testdir",
        required=True,
        help="Folder containing test images (all poses).",
    )
    parser.add_argument(
        "--name",
        required=True,
        help='Identity label, e.g. "Person_001".',
    )
    parser.add_argument(
        "--genuine-prefix",
        default="",
        help="Filename prefix for genuine images (default: {name.lower()}_).",
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
        help="Output CSV path. Default: data/results/r0_{name}.csv",
    )
    args = parser.parse_args()

    # Default output path and genuine prefix
    safe_name = args.name.lower().replace(" ", "_")
    output_csv = args.output or f"data/results/r0_{safe_name}.csv"
    genuine_prefix = args.genuine_prefix or f"{safe_name}_"

    print("=" * 60)
    print("  FRS R&D — R0 Pose Benchmark")
    print("=" * 60)
    print(f"  Identity       : {args.name}")
    print(f"  Enrollment     : {args.enrollment}")
    print(f"  Test folder    : {args.testdir}")
    print(f"  Genuine prefix : '{genuine_prefix}'")
    print(f"  Threshold      : {args.threshold}")
    print(f"  Output         : {output_csv}")
    print("=" * 60)

    # ── Load model ─────────────────────────────────────────────────────────────
    print("\n[Benchmark] Loading InsightFace buffalo_l...")
    model = FaceModel()

    # ── Enrollment embedding ────────────────────────────────────────────────────
    enrollment_emb, enroll_score = get_enrollment_embedding(model, args.enrollment)

    # ── Collect test images ────────────────────────────────────────────────────
    test_images = collect_images(args.testdir)
    if not test_images:
        print(f"[Benchmark] ERROR: No images found in {args.testdir}")
        sys.exit(1)

    print(f"[Benchmark] Found {len(test_images)} test images in {args.testdir}")

    # ── Run benchmark ──────────────────────────────────────────────────────────
    results = run_benchmark(
        model=model,
        enrollment_embedding=enrollment_emb,
        test_images=test_images,
        threshold=args.threshold,
        name=args.name,
        genuine_prefix=genuine_prefix,
    )

    # ── Save CSV ───────────────────────────────────────────────────────────────
    save_csv(results, output_csv, args.name, args.threshold)

    # ── Summary ────────────────────────────────────────────────────────────────
    print_summary(results, args.threshold)


if __name__ == "__main__":
    main()
