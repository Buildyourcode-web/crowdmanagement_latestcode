import os
from pathlib import Path
from typing import Optional
from app.config import settings


class StorageService:
    def __init__(self):
        self.media_root = Path(settings.MEDIA_ROOT)
        self.media_root.mkdir(parents=True, exist_ok=True)
        (self.media_root / "frs" / "detected").mkdir(parents=True, exist_ok=True)
        (self.media_root / "frs" / "reference").mkdir(parents=True, exist_ok=True)
        (self.media_root / "incidents").mkdir(parents=True, exist_ok=True)

    def get_public_url(self, relative_path: str) -> str:
        """Returns normalized media URL."""
        if relative_path.startswith("http://") or relative_path.startswith("https://") or relative_path.startswith("data:"):
            return relative_path
        clean_path = relative_path.lstrip("/").replace("\\", "/")
        return f"/{clean_path}"


storage_service = StorageService()
