"""
NOVA Admin Routes — accès réservé au rôle ADMIN
CRUD : sociétés, utilisateurs, boîtes mail, permissions

Sous-routeur llm_admin_router (prefixe /api/admin/llm) : administration LLM dynamique.
Auth INDEPENDANTE du JWT utilisateur (session token simple, TTL 4h).
"""

import os
import re
import time
import json
import asyncio
import logging
import secrets
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from pydantic import BaseModel, Field, field_validator

import auth.auth_db as db
from auth.auth_db import CapacityExceededError
from auth.dependencies import AuthenticatedUser, get_current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(get_current_user)])

_admin = Depends(require_role("ADMIN"))


# ── Pydantic Models ────────────────────────────────────────────────────────────

class SocietyCreate(BaseModel):
    name:           str
    sap_company_db: str
    sap_base_url:   str
    max_users:      int = Field(default=1, ge=1)


class SocietyUpdate(BaseModel):
    name:         Optional[str] = None
    sap_base_url: Optional[str] = None
    is_active:    Optional[bool] = None
    max_users:    Optional[int] = Field(default=None, ge=1)


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
            max_users=body.max_users,
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
    except CapacityExceededError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
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
    try:
        updated = db.update_user(user_id, **kwargs)
    except CapacityExceededError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
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


# ===========================================================================
# Admin LLM dynamique
# Routeur INDEPENDANT (pas de dependance JWT). Auth = session token simple
# stocke cote serveur en memoire, valide via header X-LLM-Admin-Token.
# ===========================================================================

import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.database_models import (
    SessionLocal, LLMProvider, LLMConfiguration, AdminCredentials,
    BenchmarkCase, BenchmarkRun, BenchmarkResult,
)
from services.encryption_service import encrypt, decrypt, mask
from services.llm_router import get_llm_router
from services.llm_pricing import get_pricing, get_all_pricing


llm_admin_router = APIRouter(prefix="/api/admin/llm", tags=["Admin LLM"])


_SESSION_TTL = int(os.getenv("NOVA_ADMIN_SESSION_TTL", "14400"))  # 4h
_ADMIN_SESSIONS: Dict[str, float] = {}  # token -> expires_at_epoch


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _normalize_answer(answer: str) -> str:
    """Reponse de securite : insensible casse/espaces avant hash."""
    return answer.strip().lower()


def _purge_expired_sessions() -> None:
    now = time.time()
    expired = [t for t, exp in _ADMIN_SESSIONS.items() if exp < now]
    for t in expired:
        _ADMIN_SESSIONS.pop(t, None)


def require_llm_admin(request: Request) -> None:
    """Valide le header X-LLM-Admin-Token contre la table en memoire."""
    _purge_expired_sessions()
    token = request.headers.get("X-LLM-Admin-Token", "")
    if not token or token not in _ADMIN_SESSIONS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Session admin LLM invalide ou expiree")
    # Glissement TTL : prolonge a chaque appel valide
    _ADMIN_SESSIONS[token] = time.time() + _SESSION_TTL


def _db() -> Session:
    return SessionLocal()


# ── Auth Pydantic ────────────────────────────────────────────────────────────

class LLMAdminSetup(BaseModel):
    password: str = Field(min_length=8, max_length=200)
    security_question: str = Field(min_length=3, max_length=500)
    security_answer: str = Field(min_length=1, max_length=500)


class LLMAdminLogin(BaseModel):
    password: str


class LLMAdminReset(BaseModel):
    security_answer: str
    new_password: str = Field(min_length=8, max_length=200)


# ── Auth endpoints ───────────────────────────────────────────────────────────

@llm_admin_router.get("/auth/status")
async def auth_status() -> Dict[str, Any]:
    """Indique si le premier parametrage a deja ete fait (pour l'UI)."""
    db_sess = _db()
    try:
        creds = db_sess.query(AdminCredentials).first()
        return {
            "initialized": bool(creds),
            "security_question": creds.security_question if creds else None,
        }
    finally:
        db_sess.close()


@llm_admin_router.post("/auth/setup")
async def auth_setup(body: LLMAdminSetup) -> Dict[str, Any]:
    """Premier parametrage. Refuse si deja initialise."""
    db_sess = _db()
    try:
        if db_sess.query(AdminCredentials).first():
            raise HTTPException(status_code=409, detail="Deja initialise. Utiliser /auth/reset.")
        creds = AdminCredentials(
            password_hash=_hash_password(body.password),
            security_question=body.security_question,
            security_answer_hash=_hash_password(_normalize_answer(body.security_answer)),
        )
        db_sess.add(creds)
        db_sess.commit()
        token = secrets.token_urlsafe(32)
        _ADMIN_SESSIONS[token] = time.time() + _SESSION_TTL
        logger.info("Admin LLM: setup initial reussi")
        return {"session_token": token, "expires_in": _SESSION_TTL}
    finally:
        db_sess.close()


@llm_admin_router.post("/auth/login")
async def auth_login(body: LLMAdminLogin) -> Dict[str, Any]:
    db_sess = _db()
    try:
        creds = db_sess.query(AdminCredentials).first()
        if not creds:
            raise HTTPException(status_code=409, detail="Non initialise. Faire /auth/setup.")
        if not _verify_password(body.password, creds.password_hash):
            raise HTTPException(status_code=401, detail="Mot de passe incorrect")
        token = secrets.token_urlsafe(32)
        _ADMIN_SESSIONS[token] = time.time() + _SESSION_TTL
        logger.info("Admin LLM: connexion reussie")
        return {"session_token": token, "expires_in": _SESSION_TTL}
    finally:
        db_sess.close()


@llm_admin_router.post("/auth/reset")
async def auth_reset(body: LLMAdminReset) -> Dict[str, Any]:
    """Reset via reponse a la question de securite."""
    db_sess = _db()
    try:
        creds = db_sess.query(AdminCredentials).first()
        if not creds:
            raise HTTPException(status_code=409, detail="Non initialise")
        if not _verify_password(_normalize_answer(body.security_answer),
                                creds.security_answer_hash):
            raise HTTPException(status_code=401, detail="Reponse de securite incorrecte")
        creds.password_hash = _hash_password(body.new_password)
        db_sess.commit()
        # Invalider toutes les sessions existantes
        _ADMIN_SESSIONS.clear()
        token = secrets.token_urlsafe(32)
        _ADMIN_SESSIONS[token] = time.time() + _SESSION_TTL
        logger.info("Admin LLM: mot de passe reinitialise via question de securite")
        return {"session_token": token, "expires_in": _SESSION_TTL}
    finally:
        db_sess.close()


# ── Providers Pydantic ──────────────────────────────────────────────────────

_BASE_URL_RE = re.compile(r"^https?://[\w\-.]+(:\d+)?(/.*)?$", re.IGNORECASE)


def _normalize_base_url(v: str) -> str:
    """Trim, supprime trailing slash, ajoute https:// si absent."""
    if v is None:
        return v
    v = v.strip().rstrip("/")
    if not v:
        raise ValueError("base_url ne peut pas etre vide")
    # Reparer les cas frequents : "https//foo", "http//foo", "foo.com"
    if v.startswith("https//"):
        v = "https://" + v[len("https//"):]
    elif v.startswith("http//"):
        v = "http://" + v[len("http//"):]
    elif not v.lower().startswith(("http://", "https://")):
        v = "https://" + v
    if not _BASE_URL_RE.match(v):
        raise ValueError(f"base_url invalide : {v!r}. Format attendu : https://hostname[:port][/path]")
    return v


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    api_format: str = Field(pattern="^(anthropic|openai)$")
    api_key: str = Field(min_length=1)
    available_models: List[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str) -> str:
        return _normalize_base_url(v)


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    api_format: Optional[str] = Field(default=None, pattern="^(anthropic|openai)$")
    api_key: Optional[str] = None  # None = ne pas changer
    available_models: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _normalize_base_url(v)


def _serialize_provider(prov: LLMProvider) -> Dict[str, Any]:
    try:
        plain = decrypt(prov.api_key_encrypted)
        # Preview compact a largeur fixe : 4 etoiles + 4 derniers chars
        # (jamais > 8 chars affiches quelle que soit la longueur reelle de la cle)
        if len(plain) <= 4:
            key_preview = "*" * len(plain)
        else:
            key_preview = "****" + plain[-4:]
    except ValueError:
        key_preview = "(indechiffrable)"
    return {
        "id": prov.id,
        "name": prov.name,
        "base_url": prov.base_url,
        "api_format": prov.api_format,
        "api_key_preview": key_preview,
        "available_models": prov.available_models or [],
        "is_active": prov.is_active,
        "created_at": prov.created_at.isoformat() if prov.created_at else None,
        "updated_at": prov.updated_at.isoformat() if prov.updated_at else None,
    }


# ── Providers endpoints ─────────────────────────────────────────────────────

@llm_admin_router.get("/pricing", dependencies=[Depends(require_llm_admin)])
async def get_pricing_catalog() -> Dict[str, Any]:
    """Catalogue de prix LLM (USD par million de tokens). Maintenu manuellement
    dans services/llm_pricing.py. Indicatif — verifier les prix officiels."""
    return get_all_pricing()


@llm_admin_router.get("/providers", dependencies=[Depends(require_llm_admin)])
async def list_providers() -> Dict[str, Any]:
    db_sess = _db()
    try:
        rows = db_sess.query(LLMProvider).order_by(LLMProvider.id.asc()).all()
        return {"providers": [_serialize_provider(p) for p in rows]}
    finally:
        db_sess.close()


@llm_admin_router.post("/providers", status_code=201,
                       dependencies=[Depends(require_llm_admin)])
async def create_provider(body: ProviderCreate) -> Dict[str, Any]:
    db_sess = _db()
    try:
        prov = LLMProvider(
            name=body.name,
            base_url=body.base_url,
            api_format=body.api_format,
            api_key_encrypted=encrypt(body.api_key),
            available_models=body.available_models,
            is_active=body.is_active,
        )
        db_sess.add(prov)
        try:
            db_sess.commit()
        except IntegrityError as exc:
            db_sess.rollback()
            raise HTTPException(status_code=409, detail=f"Nom deja utilise: {body.name}") from exc
        db_sess.refresh(prov)
        get_llm_router().reload()
        return _serialize_provider(prov)
    finally:
        db_sess.close()


@llm_admin_router.put("/providers/{provider_id}",
                      dependencies=[Depends(require_llm_admin)])
async def update_provider(provider_id: int, body: ProviderUpdate) -> Dict[str, Any]:
    db_sess = _db()
    try:
        prov = db_sess.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
        if not prov:
            raise HTTPException(status_code=404, detail="Provider introuvable")
        if body.name is not None:
            prov.name = body.name
        if body.base_url is not None:
            prov.base_url = body.base_url
        if body.api_format is not None:
            prov.api_format = body.api_format
        if body.api_key is not None:
            prov.api_key_encrypted = encrypt(body.api_key)
        if body.available_models is not None:
            prov.available_models = body.available_models
        if body.is_active is not None:
            prov.is_active = body.is_active
        try:
            db_sess.commit()
        except IntegrityError as exc:
            db_sess.rollback()
            raise HTTPException(status_code=409, detail="Conflit (nom deja utilise ?)") from exc
        db_sess.refresh(prov)
        get_llm_router().reload()
        return _serialize_provider(prov)
    finally:
        db_sess.close()


@llm_admin_router.delete("/providers/{provider_id}", status_code=204,
                         dependencies=[Depends(require_llm_admin)])
async def delete_provider(provider_id: int) -> None:
    db_sess = _db()
    try:
        prov = db_sess.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
        if not prov:
            raise HTTPException(status_code=404, detail="Provider introuvable")
        in_use = (db_sess.query(LLMConfiguration)
                  .filter(LLMConfiguration.provider_id == provider_id).count())
        if in_use:
            raise HTTPException(
                status_code=409,
                detail=f"Provider utilise par {in_use} entree(s) de configuration. "
                       "Retirer de la chaine avant suppression.",
            )
        db_sess.delete(prov)
        db_sess.commit()
        get_llm_router().reload()
    finally:
        db_sess.close()


@llm_admin_router.post("/test/{provider_id}",
                       dependencies=[Depends(require_llm_admin)])
async def test_provider(provider_id: int) -> Dict[str, Any]:
    ok, msg = await get_llm_router().test_provider(provider_id)
    return {"ok": ok, "message": msg}


@llm_admin_router.post("/providers/{provider_id}/discover-models",
                       dependencies=[Depends(require_llm_admin)])
async def discover_models(provider_id: int) -> Dict[str, Any]:
    """
    Interroge l'API du fournisseur pour lister les modeles disponibles.
    Supporte le format OpenAI-compatible (GET /v1/models avec Bearer) et
    le format Anthropic (GET /v1/models avec x-api-key).
    """
    import httpx
    db_sess = _db()
    try:
        prov = db_sess.query(LLMProvider).filter(LLMProvider.id == provider_id).first()
        if not prov:
            raise HTTPException(status_code=404, detail="Provider introuvable")
        try:
            api_key = decrypt(prov.api_key_encrypted)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=f"Cle indechiffrable : {exc}")
        base_url = prov.base_url.rstrip("/")
        api_format = prov.api_format
    finally:
        db_sess.close()

    url = f"{base_url}/v1/models"
    if api_format == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        sc = exc.response.status_code if exc.response is not None else "?"
        body = exc.response.text[:200] if exc.response is not None else ""
        raise HTTPException(status_code=502, detail=f"HTTP {sc} : {body}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")

    # Format de reponse : OpenAI/Mistral renvoient {"data": [{"id": "..."}, ...]}
    # Anthropic renvoie {"data": [{"id": "..."}, ...]} egalement (depuis 2024)
    raw = data.get("data") or data.get("models") or []
    models = sorted({(m.get("id") or m.get("name") or "") for m in raw if isinstance(m, dict)})
    models = [m for m in models if m]
    return {"models": models, "count": len(models)}


class TestEntry(BaseModel):
    provider_id: int
    model_name: str = Field(min_length=1, max_length=200)


@llm_admin_router.post("/test-entry", dependencies=[Depends(require_llm_admin)])
async def test_entry(body: TestEntry) -> Dict[str, Any]:
    """Teste un couple (provider, modele) precis — utilise par le bouton
    Tester de chaque entree de chaine."""
    ok, msg, latency = await get_llm_router().test_entry(body.provider_id,
                                                        body.model_name)
    return {"ok": ok, "message": msg, "latency_ms": latency}


@llm_admin_router.post("/test-chain", dependencies=[Depends(require_llm_admin)])
async def test_chain() -> Dict[str, Any]:
    """
    Teste chaque entree de la chaine de routage active et retourne un rapport.
    Chaque appel utilise le modele exact configure (pas le modele par defaut).
    """
    # Forcer le rechargement pour tester l'etat reel en base, pas la cache
    router = get_llm_router()
    router.reload()
    report = await router.test_chain()
    if not report:
        return {
            "ok": False,
            "summary": "Aucune chaine configuree (DB vide ou .env vide).",
            "results": [],
        }
    n_ok = sum(1 for r in report if r["ok"])
    return {
        "ok": n_ok == len(report),
        "summary": f"{n_ok}/{len(report)} entree(s) operationnelle(s)",
        "results": report,
    }


# ── Configuration Pydantic ──────────────────────────────────────────────────

class ConfigEntry(BaseModel):
    provider_id: int
    model_name: str = Field(min_length=1, max_length=200)


class ConfigUpdate(BaseModel):
    """priority 0 = principal. Ordre du tableau = ordre de priorite."""
    chain: List[ConfigEntry] = Field(min_length=1)


# ── Configuration endpoints ─────────────────────────────────────────────────

@llm_admin_router.get("/config", dependencies=[Depends(require_llm_admin)])
async def get_config() -> Dict[str, Any]:
    db_sess = _db()
    try:
        rows = (db_sess.query(LLMConfiguration, LLMProvider)
                .join(LLMProvider, LLMConfiguration.provider_id == LLMProvider.id)
                .filter(LLMConfiguration.is_enabled.is_(True))
                .order_by(LLMConfiguration.priority.asc())
                .all())
        chain = [{
            "priority": cfg.priority,
            "provider_id": cfg.provider_id,
            "provider_name": prov.name,
            "model_name": cfg.model_name,
            "api_format": prov.api_format,
        } for cfg, prov in rows]
        return {"chain": chain}
    finally:
        db_sess.close()


@llm_admin_router.put("/config", dependencies=[Depends(require_llm_admin)])
async def put_config(body: ConfigUpdate) -> Dict[str, Any]:
    db_sess = _db()
    try:
        # Verifier tous les provider_id existent et sont actifs
        ids = [e.provider_id for e in body.chain]
        provs = db_sess.query(LLMProvider).filter(LLMProvider.id.in_(ids)).all()
        prov_map = {p.id: p for p in provs}
        for entry in body.chain:
            if entry.provider_id not in prov_map:
                raise HTTPException(
                    status_code=404,
                    detail=f"Provider id={entry.provider_id} introuvable",
                )
            if entry.model_name not in (prov_map[entry.provider_id].available_models or []):
                raise HTTPException(
                    status_code=400,
                    detail=f"Modele '{entry.model_name}' non declare pour provider "
                           f"{prov_map[entry.provider_id].name}",
                )

        # Remplacement atomique : delete + insert dans la meme transaction
        db_sess.query(LLMConfiguration).delete()
        for prio, entry in enumerate(body.chain):
            db_sess.add(LLMConfiguration(
                provider_id=entry.provider_id,
                model_name=entry.model_name,
                priority=prio,
                is_enabled=True,
            ))
        db_sess.commit()
        get_llm_router().reload()
        return {"success": True, "count": len(body.chain)}
    finally:
        db_sess.close()


# ===========================================================================
# Benchmark LLM : cas de test, runs, résultats avec scoring automatique
# ===========================================================================

class BenchmarkCaseCreate(BaseModel):
    label: str
    email_content: str
    expected_output: dict
    # expected_output = {"client": "...", "products": [{"code":"...", "name":"...", "quantity": N}]}


class BenchmarkRunCreate(BaseModel):
    label: Optional[str] = None
    provider_model_pairs: List[dict]
    # [{"provider_id": 1, "model_name": "claude-sonnet-4-6"}, ...]
    case_ids: Optional[List[int]] = None
    # None = utiliser tous les cas actifs


def _score_result(expected: dict, actual_raw: Optional[str]) -> dict:
    """
    Compare la sortie brute du LLM (JSON string) à la sortie attendue.
    Retourne un dict de scores entre 0.0 et 1.0.
    Pondération score_global : json_valid 15%, client_match 25%,
    product_recall 30%, product_precision 15%, qty_accuracy 15%.
    """
    scores = {
        "score_json_valid": 0.0,
        "score_client_match": 0.0,
        "score_product_recall": 0.0,
        "score_product_precision": 0.0,
        "score_qty_accuracy": 0.0,
        "score_global": 0.0,
    }
    if not actual_raw:
        return scores

    # JSON valid
    try:
        actual = json.loads(actual_raw)
        scores["score_json_valid"] = 1.0
    except (json.JSONDecodeError, ValueError):
        return scores

    # Client match
    exp_client = (expected.get("client") or "").strip().lower()
    act_client = (actual.get("client") or "").strip().lower()
    if not exp_client:
        scores["score_client_match"] = 1.0
    elif act_client:
        ratio = SequenceMatcher(None, exp_client, act_client).ratio()
        scores["score_client_match"] = 1.0 if ratio >= 0.8 else ratio
    # sinon 0.0

    # Products
    exp_products: list = expected.get("products") or []
    act_products: list = actual.get("products") or []

    if not exp_products:
        scores["score_product_recall"] = 1.0
        scores["score_product_precision"] = 1.0
        scores["score_qty_accuracy"] = 1.0
    else:
        matched_pairs: list = []
        for i, ep in enumerate(exp_products):
            exp_code = (ep.get("code") or ep.get("item_code") or "").strip().lower()
            exp_name = (ep.get("name") or "").strip().lower()
            best_j, best_score = -1, 0.0
            for j, ap in enumerate(act_products):
                act_code = (ap.get("code") or ap.get("item_code") or "").strip().lower()
                act_name = (ap.get("name") or "").strip().lower()
                if exp_code and act_code and exp_code == act_code:
                    sc = 1.0
                elif exp_name and act_name:
                    sc = SequenceMatcher(None, exp_name, act_name).ratio()
                else:
                    sc = 0.0
                if sc > best_score:
                    best_score = sc
                    best_j = j
            if best_j >= 0 and best_score >= 0.8:
                matched_pairs.append((i, best_j))

        matched_count = len(matched_pairs)
        scores["score_product_recall"] = matched_count / len(exp_products)
        scores["score_product_precision"] = (
            matched_count / len(act_products) if act_products else 0.0
        )
        if matched_pairs:
            qty_hits = 0
            for i, j in matched_pairs:
                exp_qty = exp_products[i].get("quantity") or exp_products[i].get("qty")
                act_qty = act_products[j].get("quantity") or act_products[j].get("qty")
                if exp_qty is not None and act_qty is not None:
                    try:
                        if abs(float(exp_qty) - float(act_qty)) < 0.01:
                            qty_hits += 1
                    except (TypeError, ValueError):
                        pass
            scores["score_qty_accuracy"] = qty_hits / len(matched_pairs)

    weights = {
        "score_json_valid": 0.15,
        "score_client_match": 0.25,
        "score_product_recall": 0.30,
        "score_product_precision": 0.15,
        "score_qty_accuracy": 0.15,
    }
    scores["score_global"] = sum(scores[k] * w for k, w in weights.items())
    return scores


# ── Benchmark ────────────────────────────────────────────────────────────────

@llm_admin_router.get("/benchmark/cases", dependencies=[Depends(require_llm_admin)])
async def list_benchmark_cases() -> dict:
    db: Session = SessionLocal()
    try:
        cases = db.query(BenchmarkCase).filter(
            BenchmarkCase.is_active.is_(True)
        ).order_by(BenchmarkCase.created_at.desc()).all()
        return {"cases": [
            {
                "id": c.id, "label": c.label,
                "expected_output": c.expected_output,
                "created_at": c.created_at.isoformat(),
            }
            for c in cases
        ]}
    finally:
        db.close()


@llm_admin_router.post("/benchmark/cases/parse-eml",
                       dependencies=[Depends(require_llm_admin)])
async def parse_eml_for_benchmark(file: UploadFile = File(...)) -> dict:
    """
    Parse un fichier .eml et retourne le texte brut extrait.
    Ne crée pas de cas — retourne seulement les données pour pré-remplir
    le formulaire côté client.
    """
    import email as _email
    from email import policy as _policy

    if not file.filename.lower().endswith('.eml'):
        raise HTTPException(status_code=400,
                            detail="Fichier .eml attendu")

    raw = await file.read()
    try:
        msg = _email.message_from_bytes(raw,
                                        policy=_policy.default)
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail=f"Impossible de parser le fichier : {exc}")

    subject = str(msg.get('Subject', '')).strip()
    sender  = str(msg.get('From', '')).strip()

    body_text = ''
    # Priorité : text/plain, sinon text/html nettoyé
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == 'text/plain':
            try:
                body_text = part.get_content()
                break
            except Exception:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    body_text = payload.decode(charset, errors='replace')
                    break
    if not body_text:
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                try:
                    html = part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True)
                    html = payload.decode('utf-8', errors='replace') if payload else ''
                # Suppression basique des balises HTML
                import re as _re
                body_text = _re.sub(r'<[^>]+>', ' ', html)
                body_text = _re.sub(r'[ \t]{2,}', ' ', body_text)
                body_text = '\n'.join(
                    line.strip() for line in body_text.splitlines()
                    if line.strip()
                )
                break

    return {
        "subject": subject,
        "from":    sender,
        "body_text": body_text[:8000],  # limite raisonnable pour un email
    }


@llm_admin_router.post("/benchmark/cases", status_code=status.HTTP_201_CREATED,
                       dependencies=[Depends(require_llm_admin)])
async def create_benchmark_case(body: BenchmarkCaseCreate) -> dict:
    db: Session = SessionLocal()
    try:
        case = BenchmarkCase(
            label=body.label,
            email_content=body.email_content,
            expected_output=body.expected_output,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return {"id": case.id, "label": case.label}
    finally:
        db.close()


@llm_admin_router.delete("/benchmark/cases/{case_id}",
                          status_code=status.HTTP_204_NO_CONTENT,
                          dependencies=[Depends(require_llm_admin)])
async def delete_benchmark_case(case_id: int) -> None:
    db: Session = SessionLocal()
    try:
        case = db.query(BenchmarkCase).filter(BenchmarkCase.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Cas introuvable")
        case.is_active = False
        db.commit()
    finally:
        db.close()


@llm_admin_router.post("/benchmark/run", status_code=status.HTTP_201_CREATED,
                       dependencies=[Depends(require_llm_admin)])
async def start_benchmark_run(body: BenchmarkRunCreate) -> dict:
    """Lance un run de benchmark en arrière-plan. Retourne immédiatement le run_id."""
    db: Session = SessionLocal()
    try:
        # Résoudre les case_ids
        if body.case_ids:
            case_ids = body.case_ids
        else:
            case_ids = [
                c.id for c in db.query(BenchmarkCase).filter(
                    BenchmarkCase.is_active.is_(True)
                ).all()
            ]
        if not case_ids:
            raise HTTPException(status_code=400, detail="Aucun cas de test disponible")

        # Résoudre les noms de providers
        llm_entries = []
        for pair in body.provider_model_pairs:
            prov = db.query(LLMProvider).filter(
                LLMProvider.id == pair["provider_id"]
            ).first()
            if not prov:
                raise HTTPException(
                    status_code=404,
                    detail=f"Provider id={pair['provider_id']} introuvable",
                )
            llm_entries.append({
                "provider_id": prov.id,
                "provider_name": prov.name,
                "model_name": pair["model_name"],
            })

        run = BenchmarkRun(
            label=body.label,
            llm_entries=llm_entries,
            case_ids=case_ids,
            status="pending",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    finally:
        db.close()

    # Lancer l'exécution en arrière-plan
    asyncio.create_task(_execute_benchmark_run(run_id))
    return {"run_id": run_id, "status": "pending"}


async def _execute_benchmark_run(run_id: int) -> None:
    """Exécute un run de benchmark de façon asynchrone."""
    router = get_llm_router()

    db: Session = SessionLocal()
    try:
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.now()
        db.commit()
        llm_entries = run.llm_entries
        case_ids = run.case_ids
        cases = db.query(BenchmarkCase).filter(BenchmarkCase.id.in_(case_ids)).all()
        cases_map = {c.id: c for c in cases}
    finally:
        db.close()

    # Prompt système NOVA standard
    system_prompt = (
        "Tu es NOVA, un assistant commercial. Analyse l'email suivant et extrais "
        "les informations au format JSON strict : "
        "{\"client\": \"NOM_CLIENT\", \"products\": [{\"code\": \"REF\", \"name\": \"NOM\", \"quantity\": N}]}. "
        "Réponds UNIQUEMENT avec le JSON, sans texte autour."
    )

    for case_id in case_ids:
        case = cases_map.get(case_id)
        if not case:
            continue

        # Appels parallèles pour tous les LLMs sur ce cas
        tasks = [
            router.call_for_benchmark(
                provider_id=entry["provider_id"],
                model_name=entry["model_name"],
                system_prompt=system_prompt,
                user_message=case.email_content,
                max_tokens=1024,
                temperature=0.0,
            )
            for entry in llm_entries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        db = SessionLocal()
        try:
            for idx, entry in enumerate(llm_entries):
                res = results[idx]
                if isinstance(res, Exception):
                    raw_response = None
                    latency_ms = 0
                    error_message = str(res)
                else:
                    raw_response = res.get("raw_response")
                    latency_ms = res.get("latency_ms", 0)
                    error_message = res.get("error")

                parsed = None
                if raw_response:
                    try:
                        parsed = json.loads(raw_response)
                    except (json.JSONDecodeError, ValueError):
                        pass

                scores = _score_result(case.expected_output, raw_response)

                result = BenchmarkResult(
                    run_id=run_id,
                    case_id=case_id,
                    provider_id=entry["provider_id"],
                    provider_name=entry["provider_name"],
                    model_name=entry["model_name"],
                    raw_response=raw_response,
                    parsed_response=parsed,
                    latency_ms=latency_ms,
                    error_message=error_message,
                    **scores,
                )
                db.add(result)
            db.commit()
        finally:
            db.close()

    # Marquer le run comme terminé
    db = SessionLocal()
    try:
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if run:
            run.status = "completed"
            run.completed_at = datetime.now()
            db.commit()
    finally:
        db.close()


@llm_admin_router.get("/benchmark/runs", dependencies=[Depends(require_llm_admin)])
async def list_benchmark_runs() -> dict:
    db: Session = SessionLocal()
    try:
        runs = db.query(BenchmarkRun).order_by(
            BenchmarkRun.created_at.desc()
        ).limit(50).all()
        return {"runs": [
            {
                "id": r.id,
                "label": r.label,
                "status": r.status,
                "llm_count": len(r.llm_entries or []),
                "case_count": len(r.case_ids or []),
                "created_at": r.created_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ]}
    finally:
        db.close()


@llm_admin_router.get("/benchmark/runs/{run_id}", dependencies=[Depends(require_llm_admin)])
async def get_benchmark_run(run_id: int) -> dict:
    """Retourne le détail d'un run : résultats par cas et par LLM, scores agrégés."""
    db: Session = SessionLocal()
    try:
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run introuvable")

        results = db.query(BenchmarkResult).filter(
            BenchmarkResult.run_id == run_id
        ).all()

        cases = db.query(BenchmarkCase).filter(
            BenchmarkCase.id.in_(run.case_ids or [])
        ).all()
        cases_map = {c.id: c.label for c in cases}

        # Agrégation par LLM
        llm_agg: dict = {}
        for r in results:
            key = f"{r.provider_name}:{r.model_name}"
            if key not in llm_agg:
                llm_agg[key] = {
                    "provider_name": r.provider_name,
                    "model_name": r.model_name,
                    "scores": {
                        "score_json_valid": [],
                        "score_client_match": [],
                        "score_product_recall": [],
                        "score_product_precision": [],
                        "score_qty_accuracy": [],
                        "score_global": [],
                    },
                    "avg_latency_ms": [],
                    "error_count": 0,
                }
            entry = llm_agg[key]
            if r.error_message:
                entry["error_count"] += 1
            for sk in entry["scores"]:
                val = getattr(r, sk, None)
                if val is not None:
                    entry["scores"][sk].append(val)
            if r.latency_ms is not None:
                entry["avg_latency_ms"].append(r.latency_ms)

        # Calcul des moyennes
        llm_summary = []
        for key, entry in llm_agg.items():
            avg_scores = {
                sk: round(sum(vals) / len(vals), 3) if vals else 0.0
                for sk, vals in entry["scores"].items()
            }
            avg_lat = (
                int(sum(entry["avg_latency_ms"]) / len(entry["avg_latency_ms"]))
                if entry["avg_latency_ms"] else 0
            )
            llm_summary.append({
                "provider_name": entry["provider_name"],
                "model_name": entry["model_name"],
                "avg_scores": avg_scores,
                "avg_latency_ms": avg_lat,
                "error_count": entry["error_count"],
            })

        # Détail par cas
        detail_by_case = []
        for case_id in (run.case_ids or []):
            case_results = [r for r in results if r.case_id == case_id]
            detail_by_case.append({
                "case_id": case_id,
                "case_label": cases_map.get(case_id, f"Cas #{case_id}"),
                "results": [
                    {
                        "provider_name": r.provider_name,
                        "model_name": r.model_name,
                        "score_global": r.score_global,
                        "score_json_valid": r.score_json_valid,
                        "score_client_match": r.score_client_match,
                        "score_product_recall": r.score_product_recall,
                        "score_product_precision": r.score_product_precision,
                        "score_qty_accuracy": r.score_qty_accuracy,
                        "latency_ms": r.latency_ms,
                        "error_message": r.error_message,
                        "raw_response": r.raw_response,
                    }
                    for r in case_results
                ],
            })

        return {
            "run": {
                "id": run.id,
                "label": run.label,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            },
            "llm_summary": llm_summary,
            "detail_by_case": detail_by_case,
        }
    finally:
        db.close()
