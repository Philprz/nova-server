"""
NOVA Admin Routes — accès réservé au rôle ADMIN
CRUD : sociétés, utilisateurs, boîtes mail, permissions
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import auth.auth_db as db
from auth.dependencies import AuthenticatedUser, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

_admin = Depends(require_role("ADMIN"))


# ── Pydantic Models ────────────────────────────────────────────────────────────

class SocietyCreate(BaseModel):
    name:           str
    sap_company_db: str
    sap_base_url:   str


class SocietyUpdate(BaseModel):
    name:         Optional[str] = None
    sap_base_url: Optional[str] = None
    is_active:    Optional[bool] = None


class UserCreate(BaseModel):
    society_id:   int
    sap_username: str
    display_name: str
    role:         str  # ADMIN | MANAGER | ADV


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role:         Optional[str] = None
    is_active:    Optional[bool] = None


class MailboxCreate(BaseModel):
    society_id:   int
    address:      str
    display_name: Optional[str] = None
    ms_tenant_id: Optional[str] = None


class MailboxUpdate(BaseModel):
    display_name: Optional[str] = None
    ms_tenant_id: Optional[str] = None
    is_active:    Optional[bool] = None


class GrantPermission(BaseModel):
    mailbox_id: int
    can_write:  bool = False


# ── Sociétés ──────────────────────────────────────────────────────────────────

@router.get("/societies")
async def list_societies(_user: AuthenticatedUser = _admin) -> dict:
    return {"societies": db.list_societies()}


@router.post("/societies", status_code=status.HTTP_201_CREATED)
async def create_society(
    body: SocietyCreate,
    _user: AuthenticatedUser = _admin,
) -> dict:
    try:
        society_id = db.create_society(
            name=body.name,
            sap_company_db=body.sap_company_db,
            sap_base_url=body.sap_base_url,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": society_id, **body.model_dump()}


@router.patch("/societies/{society_id}")
async def update_society(
    society_id: int,
    body: SocietyUpdate,
    _user: AuthenticatedUser = _admin,
) -> dict:
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    if "is_active" in kwargs:
        kwargs["is_active"] = int(kwargs["is_active"])
    updated = db.update_society(society_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Société introuvable")
    return {"success": True}


# ── Utilisateurs ──────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    society_id: Optional[int] = None,
    _user: AuthenticatedUser = _admin,
) -> dict:
    return {"users": db.list_users(society_id)}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _user: AuthenticatedUser = _admin,
) -> dict:
    if body.role not in ("ADMIN", "MANAGER", "ADV"):
        raise HTTPException(status_code=400, detail="Rôle invalide (ADMIN | MANAGER | ADV)")
    try:
        user_id = db.create_user(
            society_id=body.society_id,
            sap_username=body.sap_username,
            display_name=body.display_name,
            role=body.role,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": user_id, **body.model_dump()}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    _user: AuthenticatedUser = _admin,
) -> dict:
    if body.role and body.role not in ("ADMIN", "MANAGER", "ADV"):
        raise HTTPException(status_code=400, detail="Rôle invalide")
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    if "is_active" in kwargs:
        kwargs["is_active"] = int(kwargs["is_active"])
    updated = db.update_user(user_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"success": True}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    _user: AuthenticatedUser = _admin,
) -> None:
    db.deactivate_user(user_id)
    db.revoke_all_user_tokens(user_id)


# ── Boîtes mail ───────────────────────────────────────────────────────────────

@router.get("/mailboxes")
async def list_mailboxes(
    society_id: Optional[int] = None,
    _user: AuthenticatedUser = _admin,
) -> dict:
    return {"mailboxes": db.list_mailboxes(society_id)}


@router.post("/mailboxes", status_code=status.HTTP_201_CREATED)
async def create_mailbox(
    body: MailboxCreate,
    _user: AuthenticatedUser = _admin,
) -> dict:
    try:
        mailbox_id = db.create_mailbox(
            society_id=body.society_id,
            address=body.address,
            display_name=body.display_name,
            ms_tenant_id=body.ms_tenant_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": mailbox_id, **body.model_dump()}


@router.patch("/mailboxes/{mailbox_id}")
async def update_mailbox(
    mailbox_id: int,
    body: MailboxUpdate,
    _user: AuthenticatedUser = _admin,
) -> dict:
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    if "is_active" in kwargs:
        kwargs["is_active"] = int(kwargs["is_active"])
    updated = db.update_mailbox(mailbox_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Boîte mail introuvable")
    return {"success": True}


# ── Permissions ────────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: int,
    _user: AuthenticatedUser = _admin,
) -> dict:
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"permissions": db.list_user_permissions(user_id)}


@router.post("/users/{user_id}/permissions", status_code=status.HTTP_201_CREATED)
async def grant_permission(
    user_id: int,
    body: GrantPermission,
    current_admin: AuthenticatedUser = _admin,
) -> dict:
    if not db.get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not db.get_mailbox_by_id(body.mailbox_id):
        raise HTTPException(status_code=404, detail="Boîte mail introuvable")
    db.grant_mailbox_permission(
        user_id=user_id,
        mailbox_id=body.mailbox_id,
        can_write=body.can_write,
        granted_by=current_admin.user_id,
    )
    return {"success": True}


@router.delete("/users/{user_id}/permissions/{mailbox_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_permission(
    user_id: int,
    mailbox_id: int,
    _user: AuthenticatedUser = _admin,
) -> None:
    db.revoke_mailbox_permission(user_id, mailbox_id)
