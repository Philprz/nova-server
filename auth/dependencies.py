"""
NOVA FastAPI Dependencies — couche RBAC
Injecter dans les routes via Depends(...).

Exemples d'utilisation :
    user: AuthenticatedUser = Depends(get_current_user)
    user = Depends(require_role("ADMIN"))
    user = Depends(require_role("ADMIN", "MANAGER"))
    user = Depends(require_mailbox_access("mailbox_id"))
"""

import logging
from typing import Callable, List

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.auth_db import check_mailbox_permission, get_user_by_id
from auth.jwt_service import decode_access_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=True)


class AuthenticatedUser:
    """Objet injecté dans les handlers après validation du JWT."""

    def __init__(self, payload: dict):
        self.user_id:     int       = int(payload["sub"])
        self.sap_username: str      = payload["sap_user"]
        self.society_id:  int       = payload["society_id"]
        self.sap_company: str       = payload["sap_company"]
        self.role:        str       = payload["role"]
        self.mailbox_ids: List[int] = payload.get("mailbox_ids", [])

    def __repr__(self) -> str:
        return (
            f"AuthenticatedUser(id={self.user_id}, "
            f"sap={self.sap_username}, role={self.role})"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    1. Extrait le Bearer token.
    2. Décode et valide la signature + expiration.
    3. Vérifie que l'utilisateur est toujours actif en base.
    4. Retourne AuthenticatedUser.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    user_id = int(payload.get("sub", 0))
    db_user = get_user_by_id(user_id)
    if not db_user or not db_user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur inactif ou supprimé",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(payload)


def require_role(*roles: str) -> Callable:
    """
    Retourne une dépendance FastAPI qui vérifie le rôle.
    Lève HTTP 403 si le rôle de l'utilisateur n'est pas dans la liste.

    Usage : Depends(require_role("ADMIN", "MANAGER"))
    """
    async def _check(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis : {' ou '.join(roles)}",
            )
        return user

    return _check


def require_mailbox_access(mailbox_id_param: str = "mailbox_id") -> Callable:
    """
    Retourne une dépendance FastAPI qui vérifie l'accès à une boîte mail.
    - ADMIN : accès total (bypass).
    - Autres : vérifie user_mailbox_permissions.
    Lève HTTP 403 si aucune permission trouvée.

    Usage : Depends(require_mailbox_access("mailbox_id"))
    Le paramètre peut être un path param ou un query param.
    """
    async def _check(
        request: Request,
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.role == "ADMIN":
            return user

        raw = (
            request.path_params.get(mailbox_id_param)
            or request.query_params.get(mailbox_id_param)
        )
        if raw is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Paramètre '{mailbox_id_param}' manquant",
            )
        try:
            mailbox_id = int(raw)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{mailbox_id_param}' doit être un entier",
            )

        perm = check_mailbox_permission(user.user_id, mailbox_id)
        if not perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé à cette boîte mail",
            )
        return user

    return _check
