"""Dépendance FastAPI : valide le cookie signé pa_session, glisse l'idle expiry,
retourne un SapSessionContext attaché à la requête.

Port Python de apps/api/src/middleware/require-session.ts.
Équivalent du preHandler Fastify, exprimé en `Depends(require_sap_session)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status

from auth.sap_session.config import COOKIE_NAME, IDLE_TIMEOUT_MINUTES
from auth.sap_session.cookie_signing import unsign
from auth.sap_session.store import AppRole, SapSession, slide_idle_expiry


@dataclass(frozen=True)
class SapSessionContext:
    """Identité applicative exposée aux routes protégées.

    sap_cookie_header est réinjecté côté serveur dans les appels SAP B1 ;
    il n'est jamais renvoyé au navigateur.
    """

    session_id: str
    user_id: int
    society_id: int
    sap_username: str
    sap_company_db: str
    sap_base_url: str
    display_name: str
    role: AppRole
    b1_session: str
    sap_cookie_header: str


def _to_context(session: SapSession) -> SapSessionContext:
    return SapSessionContext(
        session_id=session.session_id,
        user_id=session.user_id,
        society_id=session.society_id,
        sap_username=session.sap_user,
        sap_company_db=session.company_db,
        sap_base_url=session.sap_base_url,
        display_name=session.display_name,
        role=session.role,
        b1_session=session.b1_session,
        sap_cookie_header=session.sap_cookie_header,
    )


async def require_sap_session(request: Request, response: Response) -> SapSessionContext:
    """Lit le cookie signé pa_session, vérifie la session, glisse l'idle expiry.

    Lève 401 si :
    - cookie absent ou signature invalide
    - sessionId introuvable ou expiré (idle/absolute)
    Le cookie est purgé côté client en cas de session expirée.
    """
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    session_id = unsign(raw)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )

    session = slide_idle_expiry(session_id, IDLE_TIMEOUT_MINUTES)
    if session is None:
        # Session introuvable ou expirée → purger le cookie côté navigateur.
        response.delete_cookie(COOKIE_NAME, path="/")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SESSION_EXPIRED",
        )

    return _to_context(session)
