"""
batch_enroll_10k.py — High-Throughput 10,000+ Person Bulk Enrollment and FAISS Vector Index Generator.

Features:
  - Bulk processing of 10k+ images from a directory or CSV.
  - InsightFace buffalo_l GPU-accelerated face detection and 512-D embedding extraction.
  - L2 normalization for exact cosine similarity.
  - Fast FAISS IndexIDMap2(IndexFlatIP(512)) generation.
  - Optional synchronization into PostgreSQL and SQLite databases.
  - Generates standalone gallery_10k.index and metadata catalog ready for AWS S3 upload.

Usage:
  python batch_enroll_10k.py --image-dir /path/to/photos --output-index ../data/gallery_10k.index
  python batch_enroll_10k.py --csv /path/to/metadata.csv --sync-db
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

# Setup project root
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("[WARN] faiss not installed. Run: pip install faiss-cpu")

try:
    from insightface.app import FaceAnalysis
except ImportError:
    print("[ERROR] insightface is required. Run: pip install insightface")
    sys.exit(1)


def init_face_model(det_size: int = 640, device: str = "auto") -> FaceAnalysis:
    providers = []
    if device in ("auto", "cuda"):
        providers.extend(["CUDAExecutionProvider", "DmlExecutionProvider"])
    providers.append("CPUExecutionProvider")

    print(f"[INIT] Loading InsightFace buffalo_l with providers: {providers}")
    app = FaceAnalysis(name="buffalo_l", providers=providers)
    app.prepare(ctx_id=0, det_size=(det_size, det_size))
    return app


def process_image(app: FaceAnalysis, image_path: Path, min_score: float = 0.50) -> Optional[Tuple[np.ndarray, float]]:
    """Reads image, detects primary face, and returns L2-normalized 512-D embedding."""
    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return None

        faces = app.get(img)
        if not faces:
            return None

        # Filter by detection confidence
        valid_faces = [f for f in faces if getattr(f, "det_score", 0.0) >= min_score]
        if not valid_faces:
            return None

        # Select largest face by bounding box area
        best_face = max(
            valid_faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        )

        emb = best_face.normed_embedding
        if emb is None:
            emb = best_face.embedding
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm

        return emb.astype(np.float32), float(getattr(best_face, "det_score", 0.90))
    except Exception as ex:
        return None


def collect_images_from_dir(image_dir: Path) -> List[Tuple[str, Path, str]]:
    """
    Collects images from directory.
    Supports flat structure: photo1_person_name.jpg
    or subdirectories: /person_name/photo.jpg
    """
    supported_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    items = []

    for entry in image_dir.rglob("*"):
        if entry.is_file() and entry.suffix.lower() in supported_exts:
            if entry.parent != image_dir:
                name = entry.parent.name.replace("_", " ").title()
            else:
                stem = entry.stem
                clean_name = stem.split("_")[0] if "_" in stem else stem
                name = clean_name.replace("-", " ").title()
            category = "Authorized Watchlist"
            items.append((name, entry, category))

    return items


def collect_images_from_csv(csv_path: Path) -> List[Tuple[str, Path, str]]:
    """Reads CSV with columns: name,image_path,category"""
    import csv
    items = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "Unknown").strip()
            img_path = Path(row.get("image_path", "").strip())
            category = row.get("category", "Authorized Watchlist").strip()
            if img_path.exists():
                items.append((name, img_path, category))
    return items


def sync_to_databases(records: List[Dict]):
    """Syncs enrolled records into SQLite and PostgreSQL."""
    print(f"[DB-SYNC] Syncing {len(records)} records into PostgreSQL and SQLite...")

    # 1. SQLite sync
    try:
        import sqlite3
        sqlite_path = BACKEND_DIR / "data" / "frs_rnd.db"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(sqlite_path))
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS people (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, created_at TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS face_embeddings (id INTEGER PRIMARY KEY AUTOINCREMENT, person_id INTEGER, embedding BLOB, image_path TEXT, created_at TEXT, FOREIGN KEY(person_id) REFERENCES people(id))")

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        for r in records:
            name = r["display_name"]
            cur.execute("INSERT OR IGNORE INTO people (name, created_at) VALUES (?, ?)", (name, now_str))
            cur.execute("SELECT id FROM people WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                p_id = row[0]
                emb_blob = np.array(r["embedding"], dtype=np.float32).tobytes()
                cur.execute("INSERT INTO face_embeddings (person_id, embedding, image_path, created_at) VALUES (?, ?, ?, ?)",
                            (p_id, emb_blob, r.get("image_path", ""), now_str))
        conn.commit()
        conn.close()
        print("[DB-SYNC] SQLite sync completed successfully.")
    except Exception as ex:
        print(f"[DB-SYNC] SQLite sync error: {ex}")

    # 2. PostgreSQL sync
    try:
        import psycopg2
        pg_host = os.getenv("DB_HOST", "localhost")
        pg_port = int(os.getenv("DB_PORT", "5432"))
        pg_db = os.getenv("DB_NAME", "main_crowd_ai")
        pg_user = os.getenv("DB_USER", "postgres")
        pg_pass = os.getenv("DB_PASSWORD", "postgres")

        pg_conn = psycopg2.connect(
            host=pg_host, port=pg_port, dbname=pg_db, user=pg_user, password=pg_pass, connect_timeout=3
        )
        pg_cur = pg_conn.cursor()
        for r in records:
            pg_cur.execute(
                """
                INSERT INTO frs_reference_profiles 
                (id, reference_id, reference_code, display_name, category, status, active, reference_image_path, embedding_vector, embedding_model, embedding_version, created_by, last_updated_date, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, 'ACTIVE', true, %s, %s, 'buffalo_l', '1.0.0', '10k_Batch_Enrollment', %s, NOW(), NOW())
                ON CONFLICT (reference_id) DO UPDATE SET 
                    embedding_vector = EXCLUDED.embedding_vector,
                    reference_image_path = EXCLUDED.reference_image_path,
                    last_updated_date = EXCLUDED.last_updated_date;
                """,
                (
                    r["reference_id"],
                    r["reference_id"],
                    r["display_name"],
                    r["category"],
                    r.get("image_path", ""),
                    json.dumps(r["embedding"]),
                    time.strftime("%d %b %Y"),
                ),
            )
        pg_conn.commit()
        pg_conn.close()
        print("[DB-SYNC] PostgreSQL sync completed successfully.")
    except Exception as ex:
        print(f"[DB-SYNC] PostgreSQL sync skipped/warning: {ex}")


def main():
    parser = argparse.ArgumentParser(description="Batch enroll 10k+ faces and create FAISS vector index.")
    parser.add_argument("--image-dir", type=str, default=None, help="Path to folder of photos")
    parser.add_argument("--csv", type=str, default=None, help="CSV file path with metadata")
    parser.add_argument("--output-index", type=str, default=str(BACKEND_DIR / "data" / "gallery_10k.index"), help="Output path for FAISS index file")
    parser.add_argument("--output-meta", type=str, default=str(BACKEND_DIR / "data" / "gallery_10k_metadata.json"), help="Output path for metadata catalog")
    parser.add_argument("--det-size", type=int, default=640, help="InsightFace detector size (640 recommended)")
    parser.add_argument("--quality-min", type=float, default=0.45, help="Minimum face detection score")
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "cuda", "cpu"], help="Inference device")
    parser.add_argument("--sync-db", action="store_true", help="Sync enrolled profiles into SQLite and PostgreSQL")
    args = parser.parse_args()

    # Collect source images
    items = []
    if args.image_dir and Path(args.image_dir).exists():
        print(f"[INPUT] Scanning directory: {args.image_dir}")
        items = collect_images_from_dir(Path(args.image_dir))
    elif args.csv and Path(args.csv).exists():
        print(f"[INPUT] Reading CSV: {args.csv}")
        items = collect_images_from_csv(Path(args.csv))
    else:
        default_dir = BACKEND_DIR / "data" / "enrollment"
        if default_dir.exists():
            print(f"[INPUT] Using default enrollment directory: {default_dir}")
            items = collect_images_from_dir(default_dir)
        else:
            print("[ERROR] Please specify a valid --image-dir or --csv with photos.")
            sys.exit(1)

    print(f"[INPUT] Found {len(items)} image files to process.")
    if not items:
        print("[WARN] No images found. Exiting.")
        return

    # Initialize AI Face Model
    app = init_face_model(det_size=args.det_size, device=args.device)

    # Process all faces
    embeddings_list = []
    ids_list = []
    metadata_list = []
    failed_count = 0

    t_start = time.time()
    print("[PROCESSING] Extracting 512-D embeddings...")

    for i, (name, img_path, category) in enumerate(tqdm(items, desc="Enrolling")):
        res = process_image(app, img_path, min_score=args.quality_min)
        if res is None:
            failed_count += 1
            continue

        emb, det_score = res
        int_id = len(ids_list)
        ref_id = f"WL-{int_id+1:06d}"

        embeddings_list.append(emb)
        ids_list.append(int_id)
        metadata_list.append({
            "id": int_id,
            "reference_id": ref_id,
            "display_name": name,
            "category": category,
            "image_path": str(img_path),
            "det_score": round(det_score, 3),
            "embedding": emb.tolist(),
        })

    elapsed = time.time() - t_start
    total_enrolled = len(embeddings_list)
    fps = round(total_enrolled / max(0.001, elapsed), 1)

    print(f"\n[SUMMARY] Processed: {len(items)} | Enrolled: {total_enrolled} | Skipped/No-Face: {failed_count}")
    print(f"[SUMMARY] Elapsed Time: {elapsed:.2f}s ({fps} faces/sec)")

    if not embeddings_list:
        print("[WARN] No valid faces enrolled. Exiting without saving index.")
        return

    # Build FAISS Index
    if FAISS_AVAILABLE:
        print("[FAISS] Building FAISS IndexIDMap2 with IndexFlatIP(512)...")
        dim = 512
        embeddings_mat = np.vstack(embeddings_list).astype(np.float32)
        ids_arr = np.array(ids_list, dtype=np.int64)

        base_index = faiss.IndexFlatIP(dim)
        index = faiss.IndexIDMap2(base_index)
        index.add_with_ids(embeddings_mat, ids_arr)

        out_idx_path = Path(args.output_index)
        out_idx_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(out_idx_path))
        print(f"[FAISS] Successfully saved index to: {out_idx_path} ({index.ntotal} vectors)")

        # Save metadata JSON
        out_meta_path = Path(args.output_meta)
        meta_dict = {
            r["id"]: {
                "reference_id": r["reference_id"],
                "display_name": r["display_name"],
                "category": r["category"],
                "image_path": r["image_path"],
            }
            for r in metadata_list
        }
        with open(out_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_dict, f, indent=2)
        print(f"[META] Successfully saved metadata catalog to: {out_meta_path}")

        # Also save sidecar .meta.json for matcher.load_faiss_index
        sidecar_meta = out_idx_path.with_suffix(".meta.json")
        with open(sidecar_meta, "w", encoding="utf-8") as f:
            json.dump({str(r["id"]): [r["reference_id"], r["display_name"]] for r in metadata_list}, f)
        print(f"[META] Successfully saved matcher sidecar meta to: {sidecar_meta}")

    # Sync to databases if requested
    if args.sync_db:
        sync_to_databases(metadata_list)

    print("\n[DONE] 10k Batch Enrollment complete! All vectors ready for production.")


if __name__ == "__main__":
    main()
