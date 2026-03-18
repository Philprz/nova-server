"""
NOVA JWT Service
- Access token  : HS256, 60 min (configurable)
- Refresh token : opaque secrets.token_urlsafe(48), stocké haché SHA-256, 7 jours
"""

import jwt
import secrets
import hashlib
import uuid
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("NOVA_JWT_SECRET", "")
ALGORITHM  = "HS256"
ACCESS_TTL = timedelta(minutes=int(os.getenv("NOVA_JWT_ACCESS_TTL_MINUTES", "60")))
REFRESH_TTL = timedelta(days=int(os.getenv("NOVA_JWT_REFRESH_TTL_DAYS", "7")))


def _require_secret() -> str:
    if not SECRET_KEY:
        raise RuntimeError(
            "NOVA_JWT_SECRET n'est pas défini dans .env — impossible d'émettre des tokens"
        )
    return SECRET_KEY


def create_access_token(
    user_id: int,
    sap_username: str,
    society_id: int,
    sap_company_db: str,
    role: str,
    mailbox_ids: List[int],
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub":         str(user_id),
        "sap_user":    sap_username,
        "society_id":  society_id,
        "sap_company": sap_company_db,
        "role":        role,
        "mailbox_ids": mailbox_ids,
        "iat":         now,
        "exp":         now + ACCESS_TTL,
        "jti":         str(uuid.uuid4()),
    }
    return jwt.encode(payload, _require_secret(), algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> Tuple[str, str, datetime]:
    """
    Retourne (raw_token, token_hash, expires_at).
    raw_token  → renvoyé au client
    token_hash → stocké en base
    expires_at → datetime UTC
    """
    raw = secrets.token_urlsafe(48)
    token_hash = hash_token(raw)
    expires_at = datetime.now(timezone.utc) + REFRESH_TTL
    return raw, token_hash, expires_at


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Décode et valide signature + expiration.
    Lève jwt.ExpiredSignatureError ou jwt.InvalidTokenError en cas d'échec.
    """
    return jwt.decode(token, _require_secret(), algorithms=[ALGORITHM])


def hash_token(raw: str) -> str:
    """SHA-256 hex digest d'un token brut."""
    return hashlib.sha256(raw.encode()).hexdigest()
