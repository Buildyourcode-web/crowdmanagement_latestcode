"""
repository.py — Hybrid PostgreSQL & SQLite R&D database repository.

Provides unified interface for FRS:
- First attempts PostgreSQL connection.
- Seamlessly falls back to local SQLite database (data/frs_rnd.db) if PostgreSQL is unavailable or unpopulated.
- Never crashes if database is temporarily offline.
"""

from __future__ import annotations

import os
import sqlite3
import datetime
from typing import List, Optional, Tuple

import numpy as np
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def _get_sqlite_path() -> str:
    candidates = [
        os.path.join(os.getcwd(), "backend", "data", "frs_rnd.db"),
        os.path.join(os.getcwd(), "data", "frs_rnd.db"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "frs_rnd.db"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return candidates[0]


def _get_pg_conn():
    import psycopg2
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    dbname = os.getenv("DB_NAME", "postgres")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=3,
    )


def init_db() -> None:
    """Initialize tables in both PostgreSQL (if reachable) and SQLite."""
    # SQLite
    try:
        sp = _get_sqlite_path()
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        sconn = sqlite3.connect(sp)
        scur = sconn.cursor()
        scur.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
        """)
        scur.execute("""
            CREATE TABLE IF NOT EXISTS face_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                embedding BLOB NOT NULL,
                image_path TEXT,
                created_at TEXT NOT NULL
            );
        """)
        scur.execute("""
            CREATE TABLE IF NOT EXISTS rnd_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT,
                frame_id TEXT,
                predicted_name TEXT,
                person_id INTEGER,
                similarity REAL,
                threshold REAL,
                is_known INTEGER,
                notes TEXT
            );
        """)
        sconn.commit()
        sconn.close()
    except Exception as e:
        logger.warning(f"[DB] SQLite init error: {e}")

    # PostgreSQL
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS face_embeddings (
                id SERIAL PRIMARY KEY,
                person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                embedding BYTEA NOT NULL,
                image_path TEXT,
                created_at TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rnd_events (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source TEXT,
                frame_id TEXT,
                predicted_name TEXT,
                person_id INTEGER,
                similarity REAL,
                threshold REAL,
                is_known INTEGER,
                notes TEXT
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"[DB] PostgreSQL init skipped: {e}")


def insert_person(name: str) -> int:
    """Create a new person in SQLite (and PostgreSQL if available)."""
    # SQLite
    sp = _get_sqlite_path()
    sconn = sqlite3.connect(sp)
    try:
        scur = sconn.cursor()
        scur.execute(
            "INSERT INTO people (name, created_at) VALUES (?, ?)",
            (name, _now()),
        )
        person_id = scur.lastrowid
        sconn.commit()
    finally:
        sconn.close()

    # Optional PG mirror
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute(
            "INSERT INTO people (name, created_at) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING RETURNING id;",
            (name, _now()),
        )
        pg.commit()
        pg.close()
    except Exception:
        pass

    return person_id


def get_person_by_name(name: str) -> Optional[dict]:
    """Look up person by name (case-insensitive) in SQLite or PostgreSQL."""
    sp = _get_sqlite_path()
    if os.path.exists(sp):
        try:
            sconn = sqlite3.connect(sp)
            scur = sconn.cursor()
            scur.execute(
                "SELECT id, name, category, created_at FROM people WHERE LOWER(name) = LOWER(?) LIMIT 1",
                (name,)
            )
            row = scur.fetchone()
            sconn.close()
            if row:
                return {"id": row[0], "name": row[1], "category": row[2] or "general", "created_at": row[3]}
        except Exception:
            pass

    try:
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute(
            "SELECT id, name, created_at FROM people WHERE LOWER(name) = LOWER(%s) LIMIT 1",
            (name,)
        )
        row = cur.fetchone()
        pg.close()
        if row:
            return {"id": row[0], "name": row[1], "category": "general", "created_at": row[2]}
    except Exception:
        pass

    return None


def list_people() -> List[dict]:
    """Return all enrolled people from SQLite (instant) or PostgreSQL."""
    sp = _get_sqlite_path()
    if os.path.exists(sp):
        try:
            sconn = sqlite3.connect(sp)
            scur = sconn.cursor()
            scur.execute("SELECT id, name, created_at FROM people ORDER BY name;")
            rows = scur.fetchall()
            sconn.close()
            if rows:
                return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]
        except Exception:
            pass

    try:
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute("SELECT id, name, created_at FROM people ORDER BY name;")
        rows = cur.fetchall()
        pg.close()
        if rows:
            return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]
    except Exception:
        pass

    return []


def insert_embedding(person_id: int, embedding: np.ndarray, image_path: Optional[str] = None) -> int:
    """Store one face embedding in SQLite."""
    embedding = np.asarray(embedding, dtype=np.float32)
    blob = embedding.tobytes()

    sp = _get_sqlite_path()
    sconn = sqlite3.connect(sp)
    try:
        scur = sconn.cursor()
        scur.execute(
            "INSERT INTO face_embeddings (person_id, embedding, image_path, created_at) VALUES (?, ?, ?, ?)",
            (person_id, blob, image_path, _now()),
        )
        emb_id = scur.lastrowid
        sconn.commit()
    finally:
        sconn.close()

    # Optional PG mirror
    try:
        import psycopg2
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute(
            "INSERT INTO face_embeddings (person_id, embedding, image_path, created_at) VALUES (%s, %s, %s, %s) RETURNING id;",
            (person_id, psycopg2.Binary(blob), image_path, _now()),
        )
        pg.commit()
        pg.close()
    except Exception:
        pass

    return emb_id


def load_all_embeddings() -> Tuple[List[np.ndarray], List[int], List[str]]:
    """Load all stored embeddings from SQLite or PostgreSQL."""
    rows = []

    # 1. Try PostgreSQL
    try:
        pg = _get_pg_conn()
        cur = pg.cursor()
        cur.execute("""
            SELECT p.id, p.name, e.embedding
            FROM people p
            JOIN face_embeddings e ON p.id = e.person_id
            ORDER BY p.id, e.id;
        """)
        rows = cur.fetchall()
        pg.close()
    except Exception:
        rows = []

    # 2. If PostgreSQL has no rows, load from SQLite
    if not rows:
        sp = _get_sqlite_path()
        if os.path.exists(sp):
            try:
                sconn = sqlite3.connect(sp)
                scur = sconn.cursor()
                scur.execute("""
                    SELECT p.id, p.name, e.embedding
                    FROM people p
                    JOIN face_embeddings e ON p.id = e.person_id
                    ORDER BY p.id, e.id;
                """)
                rows = scur.fetchall()
                sconn.close()
            except Exception as e:
                logger.warning(f"[DB] SQLite load_all_embeddings error: {e}")

    embeddings = []
    ids = []
    names = []

    for person_id, name, blob in rows:
        if blob is None:
            continue
        try:
            arr = np.frombuffer(bytes(blob), dtype=np.float32).copy()
            if arr.shape[0] != 512:
                continue
            norm = np.linalg.norm(arr)
            if norm == 0:
                continue
            arr = arr / norm
            embeddings.append(arr)
            ids.append(person_id)
            names.append(name)
        except Exception:
            pass

    return embeddings, ids, names


def log_recognition_event(
    source: str,
    predicted_name: str,
    similarity: float,
    threshold: float,
    is_known: bool,
    person_id: Optional[int] = None,
    frame_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Record recognition event in SQLite (and PostgreSQL if available)."""
    sp = _get_sqlite_path()
    try:
        sconn = sqlite3.connect(sp)
        scur = sconn.cursor()
        scur.execute(
            """
            INSERT INTO rnd_events (timestamp, source, frame_id, predicted_name, person_id, similarity, threshold, is_known, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), source, frame_id, predicted_name, person_id, similarity, threshold, int(is_known), notes),
        )
        sconn.commit()
        sconn.close()
    except Exception as e:
        logger.debug(f"[DB] SQLite log event error: {e}")


def fetch_rnd_events() -> List[dict]:
    """Fetch logged recognition events from SQLite."""
    sp = _get_sqlite_path()
    if os.path.exists(sp):
        try:
            sconn = sqlite3.connect(sp)
            scur = sconn.cursor()
            scur.execute("""
                SELECT id, timestamp, source, frame_id, predicted_name, person_id, similarity, threshold, is_known, notes
                FROM rnd_events
                ORDER BY timestamp DESC
                LIMIT 100;
            """)
            rows = scur.fetchall()
            sconn.close()
            return [
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "source": r[2],
                    "frame_id": r[3],
                    "predicted_name": r[4],
                    "person_id": r[5],
                    "similarity": r[6],
                    "threshold": r[7],
                    "is_known": bool(r[8]),
                    "notes": r[9],
                }
                for r in rows
            ]
        except Exception:
            pass
    return []


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")