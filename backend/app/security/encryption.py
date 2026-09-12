"""
app.security.encryption — Production Credential Encryption & RTSP URL Sanitization.

Provides AES-128-CBC / HMAC-SHA256 authenticated symmetric encryption via Fernet
for sensitive camera credentials (passwords, auth tokens, full RTSP URLs with credentials).
Ensures zero credential leakage in logs, API responses, errors, and WebSockets.
"""

import base64
import hashlib
import re
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse
from cryptography.fernet import Fernet
from app.config import settings


def _get_encryption_key() -> bytes:
    """
    Derives a consistent, URL-safe 32-byte Fernet key from settings.JWT_SECRET_KEY.
    In production environments, this can also read from a dedicated CAMERA_ENCRYPTION_KEY.
    """
    secret = getattr(settings, "CAMERA_ENCRYPTION_KEY", None) or settings.JWT_SECRET_KEY
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_get_encryption_key())


def encrypt_credential(plain_text: Optional[str]) -> Optional[str]:
    """Encrypt a sensitive string (password, token, or URL) for database storage."""
    if not plain_text:
        return None
    try:
        return _fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Credential encryption failed: {e}") from e


def decrypt_credential(cipher_text: Optional[str]) -> Optional[str]:
    """Decrypt an encrypted credential from database storage."""
    if not cipher_text:
        return None
    try:
        return _fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        # If cipher text is plaintext (legacy record fallback), return as is
        return cipher_text


def sanitize_rtsp_url(url: Optional[str], mask: str = "***") -> Optional[str]:
    """
    Strips or masks user:password from an RTSP URL for safe logging and client responses.
    Example:
      rtsp://admin:secret123@192.168.0.102:554/ch1
      -> rtsp://admin:***@192.168.0.102:554/ch1
    """
    if not url:
        return None
    try:
        # Match user:password@ pattern (greedy up to last @ before host)
        pattern = r"://([^/@:]+):(.*)@([^/@]+.*)"
        m = re.search(pattern, url)
        if m:
            proto = url.split("://")[0]
            return f"{proto}://{m.group(1)}:{mask}@{m.group(3)}"
        return url
    except Exception:
        return "rtsp://***:***@camera-stream"


def strip_credentials_from_url(url: Optional[str]) -> Optional[str]:
    """
    Strips credentials entirely from an RTSP URL.
    Example:
      rtsp://admin:secret123@192.168.0.102:554/ch1
      -> rtsp://192.168.0.102:554/ch1
    """
    if not url:
        return None
    try:
        clean, _, _ = extract_credentials_from_url(url)
        return clean
    except Exception:
        return url


def build_authenticated_rtsp_url(
    base_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """
    Injects or replaces username/password into an RTSP URL cleanly.
    Properly URL-encodes special characters in the password (e.g. '@', '#', '%').
    """
    if not base_url:
        return ""

    import urllib.parse

    clean_url, existing_user, existing_pwd = extract_credentials_from_url(base_url)
    effective_user = username or existing_user
    effective_pwd = password or existing_pwd

    if effective_user and effective_pwd:
        enc_pwd = urllib.parse.quote(effective_pwd)
        parts = clean_url.split("://", 1)
        if len(parts) == 2:
            return f"{parts[0]}://{effective_user}:{enc_pwd}@{parts[1]}"

    return clean_url or base_url


def extract_credentials_from_url(url: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extracts (clean_url, username, password) from an RTSP URL.
    Supports special characters in passwords (e.g., passwords containing '@' or '#').
    """
    if not url:
        return "", None, None

    import urllib.parse

    m = re.search(r"://([^/@:]+):(.*)@([^/@]+.*)", url)
    if m:
        user = m.group(1)
        raw_pwd = m.group(2)
        pwd = urllib.parse.unquote(raw_pwd)
        proto = url.split("://", 1)[0]
        clean = f"{proto}://{m.group(3)}"
        return clean, user, pwd

    return url, None, None
