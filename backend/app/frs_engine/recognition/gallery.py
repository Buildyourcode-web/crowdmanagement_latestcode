"""
gallery.py — Multi-embedding Gallery representation and validation.

Supports multiple face embeddings per identity.
Compatible with DB loading, JSON loading, and in-memory dynamic updates.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

try:
    from app.frs_engine.recognition.embedding import normalize_embedding, validate_embedding, EXPECTED_DIM
except ImportError:
    from app.recognition.embedding import normalize_embedding, validate_embedding, EXPECTED_DIM


@dataclass
class IdentityRecord:
    """
    Represents one enrolled identity with one or more 512-D embeddings.
    """
    person_id: Union[int, str]
    name: str
    embeddings: List[np.ndarray] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class GalleryData:
    """
    In-memory gallery store maintaining multi-embedding identity mappings.
    """

    def __init__(self) -> None:
        # person_id -> IdentityRecord
        self._identities: Dict[Union[int, str], IdentityRecord] = {}

    @property
    def identity_count(self) -> int:
        return len(self._identities)

    @property
    def total_embedding_count(self) -> int:
        return sum(len(rec.embeddings) for rec in self._identities.values())

    def clear(self) -> None:
        self._identities.clear()

    def get_identity(self, person_id: Union[int, str]) -> Optional[IdentityRecord]:
        return self._identities.get(person_id)

    def list_identities(self) -> List[IdentityRecord]:
        return list(self._identities.values())

    def add_embedding(
        self,
        person_id: Union[int, str],
        name: str,
        embedding: np.ndarray,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Add a single embedding for a given person_id.
        Returns True if embedding is valid and added, False otherwise.
        """
        if not validate_embedding(embedding):
            return False

        norm_emb = normalize_embedding(embedding)
        if norm_emb is None:
            return False

        if person_id not in self._identities:
            self._identities[person_id] = IdentityRecord(
                person_id=person_id,
                name=name,
                embeddings=[norm_emb],
                metadata=metadata or {},
            )
        else:
            rec = self._identities[person_id]
            rec.name = name  # update name if provided
            rec.embeddings.append(norm_emb)

        return True

    def load_from_flat_lists(
        self,
        embeddings: List[np.ndarray],
        ids: List[Union[int, str]],
        names: List[str],
    ) -> int:
        """
        Load gallery from flat parallel lists (e.g. from database repository).
        """
        added_count = 0
        for emb, pid, name in zip(embeddings, ids, names):
            if self.add_embedding(person_id=pid, name=name, embedding=emb):
                added_count += 1
        return added_count

    def load_from_json(self, json_source: Union[str, os.PathLike]) -> int:
        """
        Load gallery from JSON file or JSON string.

        JSON Format:
        [
            {
                "person_id": "person_001",
                "name": "Alice",
                "embeddings": [
                    [512 floats...],
                    [512 floats...]
                ]
            }
        ]
        """
        if os.path.exists(str(json_source)):
            with open(json_source, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(str(json_source))

        if not isinstance(data, list):
            raise ValueError("Gallery JSON must contain a top-level list of identity records.")

        added_count = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            pid = item.get("person_id")
            name = item.get("name", str(pid))
            embs = item.get("embeddings", [])

            if pid is None:
                continue

            for emb in embs:
                arr = np.array(emb, dtype=np.float32)
                if self.add_embedding(person_id=pid, name=name, embedding=arr, metadata=item.get("metadata")):
                    added_count += 1

        return added_count

    def get_flat_matrix(self) -> Tuple[np.ndarray, List[Union[int, str]], List[str]]:
        """
        Returns:
            embeddings_matrix: (N, 512) float32 array
            person_ids       : List of length N
            person_names     : List of length N
        """
        flat_embs: List[np.ndarray] = []
        flat_ids: List[Union[int, str]] = []
        flat_names: List[str] = []

        for rec in self._identities.values():
            for emb in rec.embeddings:
                flat_embs.append(emb)
                flat_ids.append(rec.person_id)
                flat_names.append(rec.name)

        if not flat_embs:
            return np.zeros((0, EXPECTED_DIM), dtype=np.float32), [], []

        matrix = np.vstack(flat_embs).astype(np.float32)
        return matrix, flat_ids, flat_names
