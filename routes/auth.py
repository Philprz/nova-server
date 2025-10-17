"""
Routes d'authentification
Gestion de la connexion, déconnexion et tokens JWT
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

from db.session import get_db
from models.user import User
from core.security import (
    verify_password,
    create_mfa_pending_token,
    create_final_access_token
)

router = APIRouter()


class LoginRequest(BaseModel):
    """Modèle de requête pour la connexion"""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Modèle de réponse pour la connexion"""
    access_token: str
    token_type: str = "bearer"
    mfa_required: bool
    mfa_stage: str
    user_id: Optional[int] = None
    email: Optional[str] = None


class TokenResponse(BaseModel):
    """Modèle de réponse pour les tokens"""
    access_token: str
    token_type: str = "bearer"
    mfa_ok: bool = True


@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Étape 1 : Authentification par email/password (1er facteur)

    Si les credentials sont valides :
    - Retourne un token 'mfa_pending' (5 minutes)
    - Ce token ne donne accès qu'aux endpoints MFA
    - L'utilisateur doit compléter le 2FA pour obtenir un token complet

    Args:
        credentials: Email et mot de passe
        db: Session de base de données

    Returns:
        LoginResponse avec token mfa_pending

    Raises:
        HTTPException 401: Si les credentials sont invalides
        HTTPException 403: Si le compte est désactivé
    """
    # Rechercher l'utilisateur par email
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )

    # Vérifier le mot de passe
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )

    # Vérifier que le compte est actif
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé. Contactez l'administrateur."
        )

    # Mettre à jour la date de dernière connexion
    user.last_login = datetime.utcnow()
    db.commit()

    # Vérifier si le 2FA est activé pour cet utilisateur
    mfa_required = user.is_totp_enabled or user.mfa_enforced

    if mfa_required:
        # Générer un token mfa_pending (5 minutes)
        mfa_token = create_mfa_pending_token(
            user_id=user.id,
            email=user.email
        )

        return LoginResponse(
            access_token=mfa_token,
            token_type="bearer",
            mfa_required=True,
            mfa_stage="pending",
            user_id=user.id,
            email=user.email
        )
    else:
        # Si pas de 2FA activé, retourner directement un token complet
        # (pour la compatibilité avec les comptes sans 2FA)
        access_token = create_final_access_token(
            user_id=user.id,
            email=user.email,
            is_superuser=user.is_superuser
        )

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            mfa_required=False,
            mfa_stage="completed",
            user_id=user.id,
            email=user.email
        )


@router.post("/login/oauth2", response_model=TokenResponse)
async def login_oauth2(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Endpoint de login compatible OAuth2 (pour Swagger UI)

    IMPORTANT : Ce endpoint suppose que le 2FA est déjà configuré
    et retourne directement un token complet pour faciliter les tests.

    En production, utilisez /auth/login pour un flux 2FA complet.
    """
    # Rechercher l'utilisateur par username ou email
    user = db.query(User).filter(
        (User.username == form_data.username) |
        (User.email == form_data.username)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials invalides",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Vérifier le mot de passe
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials invalides",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Vérifier que le compte est actif
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé"
        )

    # Générer un token complet (pour Swagger UI)
    access_token = create_final_access_token(
        user_id=user.id,
        email=user.email,
        is_superuser=user.is_superuser
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        mfa_ok=True
    )


@router.post("/logout")
async def logout():
    """
    Déconnexion

    Note : Avec JWT, la déconnexion côté serveur est optionnelle.
    Le client doit simplement supprimer le token.

    Pour une révocation réelle, implémentez une blacklist Redis.
    """
    return {
        "success": True,
        "message": "Déconnexion réussie. Supprimez le token côté client."
    }


@router.get("/me")
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(lambda: None)  # À remplacer par get_current_user
):
    """
    Récupère les informations de l'utilisateur connecté

    Nécessite un token 'completed' (après 2FA)
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié"
        )

    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "totp_enabled": current_user.is_totp_enabled,
        "phone_verified": current_user.is_phone_verified,
        "mfa_enforced": current_user.mfa_enforced,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None
    }
