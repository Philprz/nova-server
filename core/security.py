# core/security.py - Gestion sécurité JWT avec stages MFA (mfa_pending, mfa_ok)

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_USE_LONG_RANDOM_STRING")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
MFA_PENDING_TOKEN_EXPIRE_MINUTES = 5  # Token temporaire court

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer pour extraction du token
security = HTTPBearer()


# === Password utilities ===

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe contre son hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash un mot de passe."""
    return pwd_context.hash(password)


# === JWT Token creation ===

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    mfa_stage: str = "completed"
) -> str:
    """
    Crée un JWT avec claim mfa_stage.

    Args:
        data: Payload (ex: {"sub": "user_id", "email": "user@example.com"})
        expires_delta: Durée de validité (défaut: ACCESS_TOKEN_EXPIRE_MINUTES)
        mfa_stage: "pending" (pré-MFA) ou "completed" (post-MFA)

    Returns:
        JWT token string

    Claims:
        - sub: user identifier (usually user.id or user.email)
        - mfa_stage: "pending" | "completed"
        - mfa_ok: True si mfa_stage="completed", False sinon
        - exp: expiration timestamp
        - iat: issued at timestamp
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        default_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.utcnow() + default_delta

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "mfa_stage": mfa_stage,
        "mfa_ok": mfa_stage == "completed"
    })

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_mfa_pending_token(user_id: int, email: str) -> str:
    """
    Crée un token temporaire après 1er facteur (login/password OK).
    L'utilisateur doit compléter le 2FA pour obtenir le token final.

    Args:
        user_id: ID de l'utilisateur
        email: Email de l'utilisateur

    Returns:
        JWT avec mfa_stage="pending" (TTL court: 5 min)
    """
    return create_access_token(
        data={"sub": str(user_id), "email": email, "type": "mfa_pending"},
        expires_delta=timedelta(minutes=MFA_PENDING_TOKEN_EXPIRE_MINUTES),
        mfa_stage="pending"
    )


def create_final_access_token(user_id: int, email: str, is_superuser: bool = False) -> str:
    """
    Crée le token final après MFA réussie.

    Args:
        user_id: ID utilisateur
        email: Email utilisateur
        is_superuser: Si l'utilisateur est admin

    Returns:
        JWT avec mfa_stage="completed" et mfa_ok=True
    """
    return create_access_token(
        data={
            "sub": str(user_id),
            "email": email,
            "is_superuser": is_superuser,
            "type": "access"
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        mfa_stage="completed"
    )


# === JWT Token validation ===

def decode_token(token: str) -> Dict[str, Any]:
    """
    Décode et valide un JWT.

    Args:
        token: JWT string

    Returns:
        Payload décodé

    Raises:
        HTTPException 401 si invalide/expiré
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# === FastAPI Dependencies ===

async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Extrait et valide le JWT (any stage).

    Returns:
        Token payload

    Raises:
        HTTPException 401 si token invalide
    """
    token = credentials.credentials
    payload = decode_token(token)

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject"
        )

    return payload


async def require_mfa_pending(
    token_data: Dict[str, Any] = Depends(get_current_user_from_token)
) -> Dict[str, Any]:
    """
    Dépendance pour endpoints qui nécessitent un token mfa_pending.
    Utilisé pour les endpoints de vérification MFA (verify TOTP/SMS/recovery).

    Usage:
        @router.post("/mfa/verify/totp")
        async def verify_totp(token_data: dict = Depends(require_mfa_pending)):
            user_id = int(token_data["sub"])
            ...
    """
    mfa_stage = token_data.get("mfa_stage")

    if mfa_stage != "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a pending MFA token. Please authenticate first."
        )

    return token_data


async def require_mfa_completed(
    token_data: Dict[str, Any] = Depends(get_current_user_from_token)
) -> Dict[str, Any]:
    """
    Dépendance pour routes sensibles nécessitant MFA complète.
    Vérifie que mfa_ok=True (mfa_stage="completed").

    Usage:
        @router.get("/api/clients/sensitive-data")
        async def get_sensitive_data(token_data: dict = Depends(require_mfa_completed)):
            ...
    """
    mfa_ok = token_data.get("mfa_ok", False)

    if not mfa_ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required to access this resource"
        )

    return token_data


async def get_optional_user(
    request: Request,
) -> Optional[Dict[str, Any]]:
    """
    Extrait le token si présent, sinon retourne None.
    Pour routes optionnellement authentifiées.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    try:
        payload = decode_token(token)
        return payload
    except HTTPException:
        return None


def get_client_ip(request: Request) -> str:
    """
    Extrait l'IP client (gère X-Forwarded-For pour proxies/load balancers).

    Args:
        request: FastAPI Request

    Returns:
        IP address string
    """
    # Priorité: X-Forwarded-For (si derrière proxy), sinon client.host
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Prendre la première IP de la liste (client original)
        return forwarded.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def get_user_agent(request: Request) -> str:
    """Extrait le User-Agent HTTP."""
    return request.headers.get("User-Agent", "unknown")
