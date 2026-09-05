import os
import sqlite3

import psycopg2
from psycopg2 import Binary
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

SQLITE_DB = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    ),
    "data",
    "frs_rnd.db",
)

POSTGRES_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "frs data"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}


# ============================================================
# MAIN
# ============================================================

def migrate():

    print("=" * 70)
    print("       SQLite → PostgreSQL FRS DATABASE MIGRATION")
    print("=" * 70)

    print("\nSQLite:")
    print(SQLITE_DB)

    print("\nPostgreSQL:")
    print(
        f"{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}"
    )
    print(
        f"Database: {POSTGRES_CONFIG['dbname']}"
    )

    # ========================================================
    # CHECK SQLITE
    # ========================================================

    if not os.path.exists(SQLITE_DB):

        raise FileNotFoundError(
            f"SQLite database not found:\n{SQLITE_DB}"
        )

    # ========================================================
    # CONNECT SQLITE
    # ========================================================

    sqlite_conn = sqlite3.connect(
        SQLITE_DB
    )

    sqlite_conn.row_factory = sqlite3.Row

    sqlite_cur = sqlite_conn.cursor()

    print("\n[OK] SQLite connected.")

    # ========================================================
    # READ COUNTS
    # ========================================================

    people_count = sqlite_cur.execute(
        "SELECT COUNT(*) FROM people"
    ).fetchone()[0]

    embedding_count = sqlite_cur.execute(
        "SELECT COUNT(*) FROM face_embeddings"
    ).fetchone()[0]

    event_count = sqlite_cur.execute(
        "SELECT COUNT(*) FROM rnd_events"
    ).fetchone()[0]

    print("\nSQLite data:")
    print(f"  People      : {people_count}")
    print(f"  Embeddings  : {embedding_count}")
    print(f"  R&D Events  : {event_count}")

    # ========================================================
    # CONNECT POSTGRESQL
    # ========================================================

    pg_conn = psycopg2.connect(
        **POSTGRES_CONFIG
    )

    pg_cur = pg_conn.cursor()

    print("\n[OK] PostgreSQL connected.")

    # ========================================================
    # VERIFY TABLES
    # ========================================================

    required_tables = [
        "people",
        "face_embeddings",
        "rnd_events",
    ]

    for table in required_tables:

        pg_cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = %s
            )
            """,
            (table,),
        )

        exists = pg_cur.fetchone()[0]

        if not exists:

            raise RuntimeError(
                f"PostgreSQL table '{table}' does not exist."
            )

    print("[OK] PostgreSQL tables verified.")

    # ========================================================
    # IMPORTANT
    #
    # We don't delete PostgreSQL data.
    # Existing records are preserved.
    # ========================================================

    # ========================================================
    # PEOPLE
    # ========================================================

    print("\n" + "-" * 70)
    print("Migrating PEOPLE")
    print("-" * 70)

    people = sqlite_cur.execute(
        """
        SELECT
            id,
            name,
            created_at
        FROM people
        ORDER BY id
        """
    ).fetchall()

    # Old SQLite person_id → new PostgreSQL person_id
    person_id_map = {}

    people_inserted = 0
    people_existing = 0

    for person in people:

        old_id = person["id"]
        name = person["name"]
        created_at = person["created_at"]

        # Check whether person already exists
        pg_cur.execute(
            """
            SELECT id
            FROM people
            WHERE name = %s
            """,
            (name,),
        )

        existing = pg_cur.fetchone()

        if existing:

            new_id = existing[0]

            people_existing += 1

            print(
                f"[EXISTS] {name} "
                f"(SQLite ID={old_id}, "
                f"PostgreSQL ID={new_id})"
            )

        else:

            pg_cur.execute(
                """
                INSERT INTO people
                    (
                        name,
                        created_at
                    )
                VALUES
                    (
                        %s,
                        %s
                    )
                RETURNING id
                """,
                (
                    name,
                    created_at,
                ),
            )

            new_id = pg_cur.fetchone()[0]

            people_inserted += 1

            print(
                f"[INSERTED] {name} "
                f"(SQLite ID={old_id}, "
                f"PostgreSQL ID={new_id})"
            )

        person_id_map[old_id] = new_id

    pg_conn.commit()

    # ========================================================
    # FACE EMBEDDINGS
    # ========================================================

    print("\n" + "-" * 70)
    print("Migrating FACE EMBEDDINGS")
    print("-" * 70)

    embeddings = sqlite_cur.execute(
        """
        SELECT
            id,
            person_id,
            embedding,
            image_path,
            created_at
        FROM face_embeddings
        ORDER BY id
        """
    ).fetchall()

    embeddings_inserted = 0
    embeddings_existing = 0

    for embedding_row in embeddings:

        old_embedding_id = embedding_row["id"]
        old_person_id = embedding_row["person_id"]
        embedding_blob = embedding_row["embedding"]
        image_path = embedding_row["image_path"]
        created_at = embedding_row["created_at"]

        # ----------------------------------------------------
        # Find corresponding PostgreSQL person
        # ----------------------------------------------------

        if old_person_id not in person_id_map:

            print(
                f"[SKIP] Embedding {old_embedding_id}: "
                f"person {old_person_id} not found."
            )

            continue

        new_person_id = person_id_map[
            old_person_id
        ]

        # ----------------------------------------------------
        # Validate embedding
        # ----------------------------------------------------

        if embedding_blob is None:

            print(
                f"[SKIP] Embedding "
                f"{old_embedding_id}: empty BLOB"
            )

            continue

        embedding_bytes = bytes(
            embedding_blob
        )

        # 512 float32 values × 4 bytes = 2048
        # This is a useful validation for buffalo_l.
        if len(embedding_bytes) != 2048:

            print(
                f"[WARNING] Embedding "
                f"{old_embedding_id}: "
                f"{len(embedding_bytes)} bytes"
            )

        # ----------------------------------------------------
        # Check whether this embedding already exists
        # ----------------------------------------------------

        pg_cur.execute(
            """
            SELECT id
            FROM face_embeddings
            WHERE id = %s
            """,
            (old_embedding_id,),
        )

        existing = pg_cur.fetchone()

        if existing:

            embeddings_existing += 1

            print(
                f"[EXISTS] Embedding "
                f"{old_embedding_id}"
            )

            continue

        # ----------------------------------------------------
        # Insert embedding
        # ----------------------------------------------------

        pg_cur.execute(
            """
            INSERT INTO face_embeddings
                (
                    id,
                    person_id,
                    embedding,
                    image_path,
                    created_at
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """,
            (
                old_embedding_id,
                new_person_id,
                Binary(embedding_bytes),
                image_path,
                created_at,
            ),
        )

        embeddings_inserted += 1

        print(
            f"[INSERTED] Embedding "
            f"{old_embedding_id} "
            f"→ Person {new_person_id} "
            f"({len(embedding_bytes)} bytes)"
        )

    pg_conn.commit()

    # ========================================================
    # R&D EVENTS
    # ========================================================

    print("\n" + "-" * 70)
    print("Migrating R&D EVENTS")
    print("-" * 70)

    events = sqlite_cur.execute(
        """
        SELECT
            id,
            timestamp,
            source,
            frame_id,
            predicted_name,
            person_id,
            similarity,
            threshold,
            is_known,
            notes
        FROM rnd_events
        ORDER BY id
        """
    ).fetchall()

    events_inserted = 0
    events_existing = 0

    for event in events:

        old_event_id = event["id"]

        # Check duplicate
        pg_cur.execute(
            """
            SELECT id
            FROM rnd_events
            WHERE id = %s
            """,
            (old_event_id,),
        )

        existing = pg_cur.fetchone()

        if existing:

            events_existing += 1
            continue

        old_person_id = event["person_id"]

        new_person_id = None

        if old_person_id is not None:

            new_person_id = person_id_map.get(
                old_person_id
            )

        pg_cur.execute(
            """
            INSERT INTO rnd_events
                (
                    id,
                    timestamp,
                    source,
                    frame_id,
                    predicted_name,
                    person_id,
                    similarity,
                    threshold,
                    is_known,
                    notes
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """,
            (
                old_event_id,
                event["timestamp"],
                event["source"],
                event["frame_id"],
                event["predicted_name"],
                new_person_id,
                event["similarity"],
                event["threshold"],
                event["is_known"],
                event["notes"],
            ),
        )

        events_inserted += 1

    pg_conn.commit()

    # ========================================================
    # RESET SEQUENCES
    # ========================================================

    print("\n[INFO] Resetting PostgreSQL sequences...")

    pg_cur.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(
                'people',
                'id'
            ),
            COALESCE(
                (SELECT MAX(id) FROM people),
                1
            ),
            true
        );
        """
    )

    pg_cur.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(
                'face_embeddings',
                'id'
            ),
            COALESCE(
                (SELECT MAX(id)
                 FROM face_embeddings),
                1
            ),
            true
        );
        """
    )

    pg_cur.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(
                'rnd_events',
                'id'
            ),
            COALESCE(
                (SELECT MAX(id)
                 FROM rnd_events),
                1
            ),
            true
        );
        """
    )

    pg_conn.commit()

    # ========================================================
    # VERIFY COUNTS
    # ========================================================

    pg_cur.execute(
        "SELECT COUNT(*) FROM people"
    )
    pg_people = pg_cur.fetchone()[0]

    pg_cur.execute(
        "SELECT COUNT(*) FROM face_embeddings"
    )
    pg_embeddings = pg_cur.fetchone()[0]

    pg_cur.execute(
        "SELECT COUNT(*) FROM rnd_events"
    )
    pg_events = pg_cur.fetchone()[0]

    # ========================================================
    # CLOSE
    # ========================================================

    sqlite_conn.close()
    pg_conn.close()

    # ========================================================
    # SUMMARY
    # ========================================================

    print("\n")
    print("=" * 70)
    print("                 MIGRATION COMPLETE")
    print("=" * 70)

    print("\nPEOPLE")
    print(
        f"SQLite total       : {people_count}"
    )
    print(
        f"Inserted            : {people_inserted}"
    )
    print(
        f"Already existed    : {people_existing}"
    )
    print(
        f"PostgreSQL total   : {pg_people}"
    )

    print("\nFACE EMBEDDINGS")
    print(
        f"SQLite total       : {embedding_count}"
    )
    print(
        f"Inserted            : {embeddings_inserted}"
    )
    print(
        f"Already existed    : {embeddings_existing}"
    )
    print(
        f"PostgreSQL total   : {pg_embeddings}"
    )

    print("\nR&D EVENTS")
    print(
        f"SQLite total       : {event_count}"
    )
    print(
        f"Inserted            : {events_inserted}"
    )
    print(
        f"Already existed    : {events_existing}"
    )
    print(
        f"PostgreSQL total   : {pg_events}"
    )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    migrate()