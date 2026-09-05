import os
import sys

import cv2
import numpy as np
from dotenv import load_dotenv
from insightface.app import FaceAnalysis


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

sys.path.insert(0, PROJECT_ROOT)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# GPU DLL PATHS
# ============================================================

venv = os.environ.get("VIRTUAL_ENV")

if venv:

    cuda_paths = [
        os.path.join(
            venv,
            "Lib",
            "site-packages",
            "nvidia",
            "cublas",
            "bin",
        ),
        os.path.join(
            venv,
            "Lib",
            "site-packages",
            "nvidia",
            "cudnn",
            "bin",
        ),
        os.path.join(
            venv,
            "Lib",
            "site-packages",
            "nvidia",
            "cuda_runtime",
            "bin",
        ),
        os.path.join(
            venv,
            "Lib",
            "site-packages",
            "nvidia",
            "cufft",
            "bin",
        ),
        os.path.join(
            venv,
            "Lib",
            "site-packages",
            "nvidia",
            "nvjitlink",
            "bin",
        ),
    ]

    for path in cuda_paths:

        if os.path.isdir(path):
            os.environ["PATH"] = (
                path
                + os.pathsep
                + os.environ["PATH"]
            )


# ============================================================
# IMPORT YOUR DATABASE REPOSITORY
# ============================================================

from app.database import repository as db


# ============================================================
# CONFIG
# ============================================================

ENROLLMENT_DIR = os.path.join(
    PROJECT_ROOT,
    "data",
    "enrollment",
)


PERSON_IMAGES = {
    "Ram": "ram_1.jpg",
    "Satish": "satish_1.jpg",
}


# ============================================================
# LOAD FACE MODEL
# ============================================================

print("=" * 70)
print("          FRS POSTGRESQL FACE ENROLLMENT")
print("=" * 70)

print("\n[1/4] Loading buffalo_l...")

try:

    face_app = FaceAnalysis(
        name="buffalo_l",
        providers=[
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ],
    )

    face_app.prepare(
        ctx_id=0,
        det_size=(640, 640),
    )

except Exception as e:

    print("\n[ERROR] Could not load buffalo_l:")
    print(e)
    sys.exit(1)


print("[OK] buffalo_l loaded.")


# ============================================================
# DATABASE
# ============================================================

print("\n[2/4] Connecting to PostgreSQL...")

try:

    db.init_db()

    print("[OK] PostgreSQL connected.")

except Exception as e:

    print("\n[ERROR] PostgreSQL connection failed:")
    print(e)
    sys.exit(1)


# ============================================================
# ENROLL FUNCTION
# ============================================================

def enroll_person(
    name: str,
    image_filename: str,
):

    image_path = os.path.join(
        ENROLLMENT_DIR,
        image_filename,
    )

    print("\n" + "-" * 70)
    print(f"PERSON: {name}")
    print(f"IMAGE : {image_path}")
    print("-" * 70)

    # --------------------------------------------------------
    # Check image
    # --------------------------------------------------------

    if not os.path.exists(image_path):

        print(
            f"[ERROR] Image not found: "
            f"{image_path}"
        )

        return False

    # --------------------------------------------------------
    # Read image
    # --------------------------------------------------------

    image = cv2.imread(image_path)

    if image is None:

        print(
            f"[ERROR] Could not read image: "
            f"{image_path}"
        )

        return False

    print(
        f"[OK] Image loaded: "
        f"{image.shape[1]}x{image.shape[0]}"
    )

    # --------------------------------------------------------
    # Detect face
    # --------------------------------------------------------

    print("[INFO] Detecting face...")

    faces = face_app.get(image)

    if len(faces) == 0:

        print(
            "[ERROR] No face detected."
        )

        return False

    if len(faces) > 1:

        print(
            f"[WARNING] {len(faces)} faces detected."
        )

        # Select largest face
        face = max(
            faces,
            key=lambda f: (
                (f.bbox[2] - f.bbox[0])
                *
                (f.bbox[3] - f.bbox[1])
            ),
        )

        print(
            "[INFO] Using largest detected face."
        )

    else:

        face = faces[0]

    # --------------------------------------------------------
    # Get embedding
    # --------------------------------------------------------

    embedding = face.normed_embedding

    if embedding is None:

        print(
            "[ERROR] Face embedding is empty."
        )

        return False

    embedding = np.asarray(
        embedding,
        dtype=np.float32,
    )

    print(
        f"[OK] Embedding generated."
    )

    print(
        f"     Shape : {embedding.shape}"
    )

    print(
        f"     Dtype : {embedding.dtype}"
    )

    # --------------------------------------------------------
    # Validate embedding
    # --------------------------------------------------------

    if embedding.shape != (512,):

        print(
            "[ERROR] Expected 512-D embedding."
        )

        return False

    norm = np.linalg.norm(
        embedding
    )

    if norm == 0:

        print(
            "[ERROR] Embedding norm is zero."
        )

        return False

    # Normalize
    embedding = embedding / norm

    print(
        f"     Norm  : {np.linalg.norm(embedding):.6f}"
    )

    # --------------------------------------------------------
    # Get/create person
    # --------------------------------------------------------

    person = db.get_person_by_name(
        name
    )

    if person:

        person_id = person["id"]

        print(
            f"[INFO] Person already exists."
        )

        print(
            f"       PostgreSQL person_id = "
            f"{person_id}"
        )

    else:

        person_id = db.insert_person(
            name
        )

        print(
            f"[OK] Person created."
        )

        print(
            f"     PostgreSQL person_id = "
            f"{person_id}"
        )

    # --------------------------------------------------------
    # Insert embedding
    # --------------------------------------------------------

    embedding_id = db.insert_embedding(
        person_id=person_id,
        embedding=embedding,
        image_path=image_path,
    )

    print(
        f"[OK] Embedding inserted."
    )

    print(
        f"     embedding_id = "
        f"{embedding_id}"
    )

    print(
        f"     person_id    = "
        f"{person_id}"
    )

    print(
        f"     bytes        = "
        f"{embedding.nbytes}"
    )

    return True


# ============================================================
# ENROLL BOTH PEOPLE
# ============================================================

print("\n[3/4] Enrolling people...")

success_count = 0

for name, filename in PERSON_IMAGES.items():

    if enroll_person(
        name,
        filename,
    ):
        success_count += 1


# ============================================================
# VERIFY DATABASE
# ============================================================

print("\n[4/4] Verifying PostgreSQL...")

try:

    people = db.list_people()

    embeddings, ids, names = (
        db.load_all_embeddings()
    )

    print("\nPeople in PostgreSQL:")

    for person in people:

        print(
            f"  ID={person['id']} "
            f"Name={person['name']}"
        )

    print(
        f"\nTotal people      : "
        f"{len(people)}"
    )

    print(
        f"Total embeddings  : "
        f"{len(embeddings)}"
    )

    print(
        f"Embedding names   : "
        f"{names}"
    )

except Exception as e:

    print(
        "[ERROR] Verification failed:"
    )

    print(e)


# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 70)
print("              ENROLLMENT COMPLETE")
print("=" * 70)

print(
    f"\nSuccessfully processed: "
    f"{success_count}/2"
)

print(
    "\nThe embeddings are now stored in PostgreSQL."
)