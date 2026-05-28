"""Signature HMAC-SHA256 stdlib pour le cookie pa_session.

Format du cookie : `<value>.<base64url(hmac_sha256(value, COOKIE_SECRET))>`
- Pas de dépendance externe (hmac + hashlib + base64 sont stdlib).
- Vérification en hmac.compare_digest pour éviter les timing attacks.
- Levée explicite si COOKIE_SECRET n'est pas configurée — pas de fallback silencieux.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional

_SECRET = os.getenv("COOKIE_SECRET", "")


def _require_secret() -> bytes:
    if not _SECRET:
        raise RuntimeError(
            "COOKIE_SECRET n'est pas défini dans .env — impossible de signer les cookies pa_session"
        )
    return _SECRET.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def sign(value: str) -> str:
    """Retourne `<value>.<b64url(hmac)>`."""
    secret = _require_secret()
    mac = hmac.new(secret, value.encode("utf-8"), hashlib.sha256).digest()
    return f"{value}.{_b64url(mac)}"


def unsign(signed: str) -> Optional[str]:
    """Retourne la valeur si la signature est valide, sinon None.

    Vérification timing-safe via hmac.compare_digest.
    """
    if not signed or "." not in signed:
        return None
    value, sep, sig_b64 = signed.rpartition(".")
    if not sep or not value:
        return None
    try:
        provided_sig = _b64url_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        return None
    expected_sig = hmac.new(_require_secret(), value.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None
    return value
