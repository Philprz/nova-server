"""
NOVA Auth Routes
POST /api/auth/login    — SAP validation → JWT NOVA
POST /api/auth/refresh  — rotation refresh token
POST /api/auth/logout   — révocation refresh token
GET  /api/auth/me       — profil utilisateur courant
"""

import logging
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth.auth_db import (
    get_mailbox_by_id,
    get_refresh_token,
    get_society_by_sap_company,
    get_user_by_id,
    get_user_by_sap_login,
    get_user_mailbox_ids,
    list_user_permissions,
    revoke_refresh_token,
    store_refresh_token,
    touch_last_login,
)
from auth.dependencies import AuthenticatedUser, get_current_user
from auth.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
)
from auth.sap_validator import validate_sap_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ── Modèles Pydantic ───────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    sap_company_db: str
    sap_username:   str
    sap_password:   str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int = 3600


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """
    Flux :
    1. Vérifie que la société existe dans nova_auth.db
    2. Vérifie que l'utilisateur est enregistré dans NOVA
    3. Valide les credentials via SAP B1
    4. Émet un JWT NOVA + refresh token
    """
    # 1. Société
    society = get_society_by_sap_company(body.sap_company_db)
    if not society:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Société inconnue ou inactive",
        )

    # 2. Utilisateur NOVA
    user = get_user_by_sap_login(society["id"], body.sap_username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non enregistré dans NOVA",
        )

    # 3. Validation SAP (stateless — session discardée immédiatement)
    sap_ok = await validate_sap_credentials(
        sap_base_url=society["sap_base_url"],
        company_db=body.sap_company_db,
        username=body.sap_username,
        password=body.sap_password,
    )
    if not sap_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials SAP invalides",
        )

    # 4. Emission des tokens
    mailbox_ids = get_user_mailbox_ids(user["id"])
    access_token = create_access_token(
        user_id=user["id"],
        sap_username=user["sap_username"],
        society_id=society["id"],
        sap_company_db=society["sap_company_db"],
        role=user["role"],
        mailbox_ids=mailbox_ids,
    )
    raw_refresh, token_hash, expires_at = create_refresh_token(user["id"])
    store_refresh_token(user["id"], token_hash, expires_at.isoformat())
    touch_last_login(user["id"])

    logger.info(f"Login OK : {body.sap_username}@{body.sap_company_db} (role={user['role']})")

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest) -> TokenResponse:
    """
    Rotation du refresh token :
    1. Vérifie le token en base (non révoqué, non expiré)
    2. Révoque l'ancien
    3. Émet une nouvelle paire access + refresh
    """
    token_hash = hash_token(body.refresh_token)
    stored = get_refresh_token(token_hash)

    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou révoqué",
        )

    # Vérifier expiration
    expires_at = datetime.fromisoformat(stored["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expiré",
        )

    user = get_user_by_id(stored["user_id"])
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur inactif",
        )

    society_row = __import__("auth.auth_db", fromlist=["get_society_by_id"]).get_society_by_id(user["society_id"])

    # Rotation : révoquer l'ancien, émettre le nouveau
    revoke_refresh_token(token_hash)

    mailbox_ids = get_user_mailbox_ids(user["id"])
    new_access = create_access_token(
        user_id=user["id"],
        sap_username=user["sap_username"],
        society_id=user["society_id"],
        sap_company_db=society_row["sap_company_db"] if society_row else "",
        role=user["role"],
        mailbox_ids=mailbox_ids,
    )
    new_raw_refresh, new_hash, new_expires = create_refresh_token(user["id"])
    store_refresh_token(user["id"], new_hash, new_expires.isoformat())

    return TokenResponse(access_token=new_access, refresh_token=new_raw_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """Révoque le refresh token fourni."""
    token_hash = hash_token(body.refresh_token)
    revoke_refresh_token(token_hash)


@router.get("/me")
async def me(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Retourne le profil et les permissions de l'utilisateur courant."""
    permissions = list_user_permissions(user.user_id)
    return {
        "user_id":      user.user_id,
        "sap_username": user.sap_username,
        "society_id":   user.society_id,
        "sap_company":  user.sap_company,
        "role":         user.role,
        "mailboxes": [
            {
                "mailbox_id":    p["mailbox_id"],
                "address":       p["address"],
                "display_name":  p.get("mailbox_name"),
                "can_read":      bool(p["can_read"]),
                "can_write":     bool(p["can_write"]),
            }
            for p in permissions
        ],
    }
