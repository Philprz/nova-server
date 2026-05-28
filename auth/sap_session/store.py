"""Store in-memory des sessions SAP B1 indexées par UUID.

Port Python de apps/api/src/session/store.ts (projet BILLING).
Le B1SESSION n'est jamais envoyé au navigateur — seul un cookie signé contenant
le sessionId UUID circule côté client.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Literal, Optional

AppRole = Literal["ADMIN", "MANAGER", "ADV"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _min_date(a: datetime, b: datetime) -> datetime:
    return a if a <= b else b


@dataclass
class SapSession:
    session_id: str
    b1_session: str
    sap_cookie_header: str
    session_timeout_minutes: int
    company_db: str
    sap_base_url: str
    sap_user: str
    user_id: int
    society_id: int
    display_name: str
    role: AppRole
    idle_expires_at: datetime
    absolute_expires_at: datetime
    expires_at: datetime
    created_at: datetime = field(default_factory=_now)


_store: dict[str, SapSession] = {}
_lock = threading.Lock()


def create_session(
    *,
    b1_session: str,
    sap_cookie_header: Optional[str],
    company_db: str,
    sap_base_url: str,
    sap_user: str,
    user_id: int,
    society_id: int,
    display_name: str,
    role: AppRole,
    session_timeout_minutes: int,
    idle_expires_at: datetime,
    absolute_expires_at: datetime,
) -> SapSession:
    session = SapSession(
        session_id=str(uuid.uuid4()),
        b1_session=b1_session,
        sap_cookie_header=sap_cookie_header or f"B1SESSION={b1_session}",
        session_timeout_minutes=session_timeout_minutes,
        company_db=company_db,
        sap_base_url=sap_base_url,
        sap_user=sap_user,
        user_id=user_id,
        society_id=society_id,
        display_name=display_name,
        role=role,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        expires_at=_min_date(idle_expires_at, absolute_expires_at),
    )
    with _lock:
        _store[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[SapSession]:
    with _lock:
        session = _store.get(session_id)
        if session is None:
            return None
        now = _now()
        if session.idle_expires_at <= now or session.absolute_expires_at <= now:
            _store.pop(session_id, None)
            return None
        return session


def delete_session(session_id: str) -> None:
    with _lock:
        _store.pop(session_id, None)


def _update_session_locked(session_id: str, **patch) -> Optional[SapSession]:
    session = _store.get(session_id)
    if session is None:
        return None
    merged = replace(session, **patch)
    merged.expires_at = _min_date(merged.idle_expires_at, merged.absolute_expires_at)
    _store[session_id] = merged
    return merged


def update_session(session_id: str, **patch) -> Optional[SapSession]:
    with _lock:
        return _update_session_locked(session_id, **patch)


def slide_idle_expiry(session_id: str, ttl_minutes: int) -> Optional[SapSession]:
    """Glisse idle_expires_at à now+ttl, jamais au-delà de absolute_expires_at."""
    from datetime import timedelta

    with _lock:
        session = _store.get(session_id)
        if session is None:
            return None
        new_idle = _now() + timedelta(minutes=ttl_minutes)
        capped = _min_date(new_idle, session.absolute_expires_at)
        return _update_session_locked(session_id, idle_expires_at=capped)


def count_active_sessions() -> int:
    now = _now()
    with _lock:
        return sum(1 for s in _store.values() if s.expires_at > now)


def purge_expired_sessions() -> int:
    """Purge périodique pour éviter les fuites mémoire. Retourne le nb purgé."""
    now = _now()
    with _lock:
        expired = [sid for sid, s in _store.items() if s.expires_at <= now]
        for sid in expired:
            _store.pop(sid, None)
        return len(expired)
