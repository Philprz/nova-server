"""Endpoints /api/sapauth/* — auth par session SAP B1.

Port Python de apps/api/src/routes/auth.ts + routes/sap.ts (projet BILLING).
Le cookie `pa_session` (HttpOnly, signé HMAC-SHA256) ne contient qu'un
sessionId UUID ; le B1SESSION reste serveur via le store in-memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth.auth_db import (
    get_society_by_sap_company,
    get_user_by_sap_login,
    touch_last_login,
)
from auth.sap_session.config import (
    ABSOLUTE_TIMEOUT_MINUTES,
    COOKIE_NAME,
    IDLE_TIMEOUT_MINUTES,
    SECURE_COOKIES,
)
from auth.sap_session.cookie_signing import sign, unsign
from auth.sap_session.require_session import SapSessionContext, require_sap_session
from auth.sap_session.sap_auth_service import (
    SapAuthError,
    sap_login,
    sap_logout,
    sap_ping,
)
from auth.sap_session.store import (
    create_session,
    delete_session,
    get_session,
    slide_idle_expiry,
)
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sapauth", tags=["SAP Auth Session"])


class LoginBody(BaseModel):
    company_db: str = Field(..., min_length=1, alias="companyDb")
    user_name: str = Field(..., min_length=1, alias="userName")
    password: str = Field(..., min_length=1)

    model_config = {"populate_by_name": True}


def _now_plus_minutes(minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _set_session_cookie(response: Response, session_id: str, expires_at: datetime) -> None:
    signed = sign(session_id)
    max_age = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        key=COOKIE_NAME,
        value=signed,
        max_age=max_age,
        httponly=True,
        secure=SECURE_COOKIES,
        samesite="lax",
        path="/",
    )


def _session_payload(session) -> dict:
    return {
        "user": session.sap_user,
        "displayName": session.display_name,
        "role": session.role,
        "companyDb": session.company_db,
        "societyId": session.society_id,
        "expiresAt": session.expires_at.isoformat(),
    }


@router.post("/login")
async def login(body: LoginBody) -> JSONResponse:
    """1. allowlist société (table societies) → 401 si inconnue/inactive
    2. SAP login (society.sap_base_url) → 401 INVALID_CREDENTIALS / 503 SAP_UNREACHABLE
    3. provisionnement (nova_users) → 403 USER_NOT_PROVISIONED / USER_DISABLED
    4. création session in-memory + Set-Cookie pa_session signé
    """
    society = get_society_by_sap_company(body.company_db)
    if not society:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Société inconnue ou inactive",
        )

    try:
        sap_result = await sap_login(
            body.company_db,
            body.user_name,
            body.password,
            base_url=society["sap_base_url"],
        )
    except SapAuthError as err:
        is_invalid_creds = err.status_code == 401
        error_code = "INVALID_CREDENTIALS" if is_invalid_creds else "SAP_UNREACHABLE"
        http_code = (
            status.HTTP_401_UNAUTHORIZED if is_invalid_creds else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        logger.warning(
            "sapauth login failed (%s) for %s@%s: %s",
            error_code,
            body.user_name,
            body.company_db,
            err,
        )
        raise HTTPException(status_code=http_code, detail=error_code) from err

    # nova_users filtre déjà sur is_active=1, get_user_by_sap_login renvoie None sinon
    user = get_user_by_sap_login(society["id"], body.user_name)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="USER_NOT_PROVISIONED",
        )

    idle_expires_at = _now_plus_minutes(IDLE_TIMEOUT_MINUTES)
    absolute_expires_at = _now_plus_minutes(ABSOLUTE_TIMEOUT_MINUTES)
    session = create_session(
        b1_session=sap_result.b1_session,
        sap_cookie_header=sap_result.sap_cookie_header,
        company_db=body.company_db,
        sap_base_url=society["sap_base_url"],
        sap_user=body.user_name,
        user_id=user["id"],
        society_id=society["id"],
        display_name=user["display_name"],
        role=user["role"],
        session_timeout_minutes=sap_result.session_timeout_minutes,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
    )

    try:
        touch_last_login(user["id"])
    except Exception as exc:
        logger.debug("touch_last_login best-effort failed: %s", exc)

    logger.info(
        "sapauth login OK : %s@%s (role=%s, sessionId=%s)",
        body.user_name,
        body.company_db,
        user["role"],
        session.session_id,
    )

    response = JSONResponse({"success": True, "data": _session_payload(session)})
    _set_session_cookie(response, session.session_id, session.expires_at)
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Logout best-effort SAP + suppression session in-memory + clear cookie."""
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        session_id = unsign(raw)
        if session_id:
            session = get_session(session_id)
            if session is not None:
                await sap_logout(session.sap_cookie_header, base_url=session.sap_base_url)
                delete_session(session_id)

    response = JSONResponse({"success": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me")
async def me(session: SapSessionContext = Depends(require_sap_session)) -> dict:
    # require_sap_session a déjà glissé l'idle expiry ; on relit l'état frais
    # depuis le store pour récupérer expires_at à jour.
    stored = get_session(session.session_id)
    if stored is None:
        # require_sap_session vient de valider ; cas extrême uniquement
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SESSION_EXPIRED",
        )
    return {"success": True, "data": _session_payload(stored)}


@router.post("/keepalive")
async def keepalive(
    session: SapSessionContext = Depends(require_sap_session),
) -> JSONResponse:
    """Vérifie que SAP répond encore, puis glisse l'idle expiry et renouvelle le cookie."""
    ping_ok = await sap_ping(session.sap_cookie_header, base_url=session.sap_base_url)
    if not ping_ok:
        delete_session(session.session_id)
        response = JSONResponse(
            {"success": False, "error": "SESSION_EXPIRED"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    updated = slide_idle_expiry(session.session_id, IDLE_TIMEOUT_MINUTES)
    if updated is None:
        response = JSONResponse(
            {"success": False, "error": "SESSION_EXPIRED"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        response.delete_cookie(COOKIE_NAME, path="/")
        return response

    response = JSONResponse({"success": True, "data": _session_payload(updated)})
    _set_session_cookie(response, updated.session_id, updated.expires_at)
    return response


@router.post("/ping")
async def ping(session: SapSessionContext = Depends(require_sap_session)) -> dict:
    """Endpoint de démo : prouve que sap_cookie_header est réinjecté vers SAP côté serveur."""
    ok = await sap_ping(session.sap_cookie_header, base_url=session.sap_base_url)
    if not ok:
        # Le B1SESSION n'est plus valide côté SAP — purger la session NOVA
        delete_session(session.session_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SESSION_EXPIRED",
        )
    return {"success": True, "data": {"sap": "ok"}}
