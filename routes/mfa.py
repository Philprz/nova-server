# routes/mfa.py - Endpoints API pour MFA/2FA (TOTP, SMS, Recovery codes)

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
import phonenumbers

# Imports NOVA
from db.session import SessionLocal
from models.user import User, MFABackupMethod
from core.security import (
    require_mfa_pending,
    require_mfa_completed,
    create_final_access_token,
    get_client_ip,
    get_user_agent
)
from core.rate_limit import check_rate_limit, reset_rate_limit
from core.logging import log_mfa_event
from services.mfa_totp import totp_service
from services.recovery_codes import recovery_service
from services.mfa_sms import sms_otp_service


router = APIRouter(prefix="/mfa", tags=["MFA/2FA"])


# === Database dependency ===

def get_db():
    """FastAPI dependency pour obtenir une session DB."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# === Pydantic schemas ===

class TOTPEnrollResponse(BaseModel):
    """Réponse enrôlement TOTP."""
    secret: str = Field(..., description="Secret base32 (à stocker en sécurité)")
    provisioning_uri: str = Field(..., description="URI otpauth://...")
    qr_code: str = Field(..., description="QR code en base64 PNG")
    message: str = "Scannez le QR code avec votre app authenticator"


class TOTPVerifyRequest(BaseModel):
    """Requête vérification TOTP."""
    code: str = Field(..., min_length=6, max_length=6, description="Code TOTP 6 chiffres")

    @field_validator("code")
    def validate_numeric(cls, v):
        if not v.isdigit():
            raise ValueError("Code must be numeric")
        return v


class TOTPEnrollVerifyRequest(BaseModel):
    """Requête vérification enrôlement TOTP."""
    code: str = Field(..., min_length=6, max_length=6)

    @field_validator("code")
    def validate_numeric(cls, v):
        if not v.isdigit():
            raise ValueError("Code must be numeric")
        return v


class TOTPEnrollVerifyResponse(BaseModel):
    """Réponse vérification enrôlement TOTP."""
    success: bool
    recovery_codes: Optional[List[str]] = Field(None, description="Codes de récupération (une seule fois!)")
    message: str


class SMSSendResponse(BaseModel):
    """Réponse envoi OTP SMS."""
    success: bool
    message_id: Optional[str] = None
    expires_at: Optional[str] = None
    message: str


class SMSVerifyRequest(BaseModel):
    """Requête vérification OTP SMS."""
    code: str = Field(..., min_length=6, max_length=6, description="Code SMS 6 chiffres")

    @field_validator("code")
    def validate_numeric(cls, v):
        if not v.isdigit():
            raise ValueError("Code must be numeric")
        return v


class RecoveryVerifyRequest(BaseModel):
    """Requête vérification recovery code."""
    code: str = Field(..., min_length=9, max_length=9, description="Recovery code format XXXX-XXXX")


class PhoneSetRequest(BaseModel):
    """Requête configuration téléphone."""
    phone: str = Field(..., description="Numéro de téléphone au format international")

    @field_validator("phone")
    def validate_phone(cls, v):
        try:
            parsed = phonenumbers.parse(v, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Invalid phone number")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValueError("Invalid phone number format. Use E.164 format (+33612345678)")


class BackupMethodRequest(BaseModel):
    """Requête configuration méthode de secours."""
    method: MFABackupMethod


class AccessTokenResponse(BaseModel):
    """Réponse avec access token final."""
    access_token: str
    token_type: str = "bearer"
    mfa_ok: bool = True


# === Helper functions ===

def get_user_by_id(db: Session, user_id: int) -> User:
    """Récupère un utilisateur par ID ou raise 404."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def check_mfa_lock(user: User) -> None:
    """Vérifie si l'utilisateur est verrouillé (anti-bruteforce)."""
    if user.mfa_lock_until and user.mfa_lock_until > datetime.now(timezone.utc):
        remaining = (user.mfa_lock_until - datetime.now(timezone.utc)).total_seconds()
        raise HTTPException(
            status_code=429,
            detail={
                "error": "account_locked",
                "message": f"Too many failed MFA attempts. Try again in {int(remaining)}s.",
                "retry_after": int(remaining)
            }
        )


def increment_mfa_failure(db: Session, user: User, request: Request) -> None:
    """Incrémente le compteur d'échecs MFA et verrouille si nécessaire."""
    user.mfa_failed_attempts += 1
    user.mfa_last_failure = datetime.now(timezone.utc)
    user.mfa_last_ip = get_client_ip(request)

    # Verrouillage après 10 échecs (15 min)
    if user.mfa_failed_attempts >= 10:
        from datetime import timedelta
        user.mfa_lock_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        log_mfa_event("mfa_account_locked", user_id=user.id, result="locked",
                      ip_address=get_client_ip(request))

    db.commit()


def reset_mfa_failure(db: Session, user: User, request: Request) -> None:
    """Réinitialise le compteur d'échecs après succès."""
    user.mfa_failed_attempts = 0
    user.mfa_lock_until = None
    user.mfa_last_success = datetime.now(timezone.utc)
    user.mfa_last_ip = get_client_ip(request)
    db.commit()


# ================================
# 1. TOTP ENROLLMENT (enrôlement)
# ================================

@router.post("/totp/enroll/start", response_model=TOTPEnrollResponse)
async def totp_enroll_start(
    request: Request,
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Démarre l'enrôlement TOTP.
    Génère un secret, QR code et URI pour l'app authenticator.

    Pré-requis: token complet (1er facteur OK).

    Retourne:
    - secret (à sauvegarder!)
    - provisioning_uri
    - qr_code (base64 PNG)

    L'utilisateur doit ensuite appeler /totp/enroll/verify avec un code pour confirmer.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 5 enrôlements / heure
    check_rate_limit(f"totp_enroll:{user_id}", max_requests=5, window_seconds=3600)

    # Générer secret + QR
    secret, uri, qr_code = totp_service.enroll_user(user.email)

    # Sauvegarder secret (temporaire, pas encore activé)
    user.totp_secret = secret
    db.commit()

    log_mfa_event("totp_enroll_start", user_id=user.id, result="success",
                  ip_address=get_client_ip(request))

    return TOTPEnrollResponse(
        secret=secret,
        provisioning_uri=uri,
        qr_code=qr_code,
        message="Scan the QR code with your authenticator app, then verify with a code"
    )


@router.post("/totp/enroll/verify", response_model=TOTPEnrollVerifyResponse)
async def totp_enroll_verify(
    request: Request,
    body: TOTPEnrollVerifyRequest,
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Vérifie le code TOTP pour finaliser l'enrôlement.
    Si succès:
    - Active TOTP (is_totp_enabled=True)
    - Génère 10 recovery codes (retournés UNE SEULE FOIS!)

    Pré-requis: avoir appelé /totp/enroll/start avant.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 10 tentatives / minute
    check_rate_limit(f"totp_enroll_verify:{user_id}", max_requests=10, window_seconds=60)

    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP enrollment not started. Call /totp/enroll/start first.")

    # Vérifier le code
    is_valid = totp_service.verify_totp(user.totp_secret, body.code, valid_window=1)

    if not is_valid:
        log_mfa_event("totp_enroll_verify", user_id=user.id, result="failure",
                      ip_address=get_client_ip(request))
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    # Activer TOTP
    user.is_totp_enabled = True
    user.totp_enrolled_at = datetime.now(timezone.utc)

    # Générer recovery codes
    codes_plain = recovery_service.generate_codes(10)
    codes_hashes = recovery_service.hash_codes(codes_plain)
    user.recovery_codes_hashes = codes_hashes
    user.recovery_codes_generated_at = datetime.now(timezone.utc)

    db.commit()

    log_mfa_event("totp_enroll_verify", user_id=user.id, result="success",
                  ip_address=get_client_ip(request))

    return TOTPEnrollVerifyResponse(
        success=True,
        recovery_codes=codes_plain,
        message="TOTP activated! Save your recovery codes in a safe place. They will not be shown again."
    )


# ================================
# 2. MFA VERIFICATION (login)
# ================================

@router.post("/verify/totp", response_model=AccessTokenResponse)
async def verify_totp(
    request: Request,
    body: TOTPVerifyRequest,
    token_data: dict = Depends(require_mfa_pending),
    db: Session = Depends(get_db)
):
    """
    Vérifie le code TOTP après login (2ème facteur).

    Pré-requis: token mfa_pending (login/password OK).

    Si succès:
    - Retourne access_token final (mfa_ok=True)
    - Réinitialise compteurs d'échecs
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 10 tentatives / minute
    client_ip = get_client_ip(request)
    check_rate_limit(f"mfa_verify_totp:{user_id}:{client_ip}", max_requests=10, window_seconds=60)

    # Vérifier verrouillage
    check_mfa_lock(user)

    if not user.is_totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP not enabled for this account")

    # Vérifier code
    is_valid = totp_service.verify_totp(user.totp_secret, body.code, valid_window=1)

    if not is_valid:
        increment_mfa_failure(db, user, request)
        log_mfa_event("totp_verify", user_id=user.id, result="failure", mfa_method="totp",
                      ip_address=client_ip, user_agent=get_user_agent(request))
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    # Succès!
    reset_mfa_failure(db, user, request)
    reset_rate_limit(f"mfa_verify_totp:{user_id}:{client_ip}")

    log_mfa_event("totp_verify", user_id=user.id, result="success", mfa_method="totp",
                  ip_address=client_ip, user_agent=get_user_agent(request))

    # Générer token final
    access_token = create_final_access_token(user.id, user.email, user.is_superuser)

    return AccessTokenResponse(access_token=access_token, token_type="bearer", mfa_ok=True)


@router.post("/verify/sms", response_model=AccessTokenResponse)
async def verify_sms(
    request: Request,
    body: SMSVerifyRequest,
    token_data: dict = Depends(require_mfa_pending),
    db: Session = Depends(get_db)
):
    """
    Vérifie le code SMS OTP après login (2ème facteur fallback).

    Pré-requis:
    - token mfa_pending
    - avoir appelé /mfa/sms/send avant (OTP envoyé)
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 10 tentatives / minute
    client_ip = get_client_ip(request)
    check_rate_limit(f"mfa_verify_sms:{user_id}:{client_ip}", max_requests=10, window_seconds=60)

    # Vérifier verrouillage
    check_mfa_lock(user)

    if not user.phone_e164 or not user.is_phone_verified:
        raise HTTPException(status_code=400, detail="Phone number not verified for this account")

    # Vérifier code via service SMS
    is_valid = await sms_otp_service.verify_otp(user_id, body.code)

    if not is_valid:
        increment_mfa_failure(db, user, request)
        log_mfa_event("sms_verify", user_id=user.id, result="failure", mfa_method="sms",
                      ip_address=client_ip, user_agent=get_user_agent(request))
        raise HTTPException(status_code=400, detail="Invalid or expired SMS code")

    # Succès!
    reset_mfa_failure(db, user, request)
    reset_rate_limit(f"mfa_verify_sms:{user_id}:{client_ip}")

    log_mfa_event("sms_verify", user_id=user.id, result="success", mfa_method="sms",
                  ip_address=client_ip, user_agent=get_user_agent(request))

    # Token final
    access_token = create_final_access_token(user.id, user.email, user.is_superuser)

    return AccessTokenResponse(access_token=access_token, token_type="bearer", mfa_ok=True)


@router.post("/verify/recovery", response_model=AccessTokenResponse)
async def verify_recovery(
    request: Request,
    body: RecoveryVerifyRequest,
    token_data: dict = Depends(require_mfa_pending),
    db: Session = Depends(get_db)
):
    """
    Vérifie un recovery code (code de secours one-time).

    Pré-requis: token mfa_pending.

    Si succès:
    - Consomme le code (supprimé de la liste)
    - Retourne access token final
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 5 tentatives / minute (plus strict)
    client_ip = get_client_ip(request)
    check_rate_limit(f"mfa_verify_recovery:{user_id}:{client_ip}", max_requests=5, window_seconds=60)

    # Vérifier verrouillage
    check_mfa_lock(user)

    if not user.recovery_codes_hashes:
        raise HTTPException(status_code=400, detail="No recovery codes available")

    # Vérifier et consommer
    remaining_hashes = recovery_service.verify_and_consume(body.code, user.recovery_codes_hashes)

    if remaining_hashes is None:
        increment_mfa_failure(db, user, request)
        log_mfa_event("recovery_verify", user_id=user.id, result="failure", mfa_method="recovery",
                      ip_address=client_ip)
        raise HTTPException(status_code=400, detail="Invalid recovery code")

    # Succès! Mettre à jour DB
    user.recovery_codes_hashes = remaining_hashes if remaining_hashes else None
    reset_mfa_failure(db, user, request)
    db.commit()

    reset_rate_limit(f"mfa_verify_recovery:{user_id}:{client_ip}")

    log_mfa_event("recovery_verify", user_id=user.id, result="success", mfa_method="recovery",
                  ip_address=client_ip, extra_data={"remaining_codes": len(remaining_hashes)})

    # Token final
    access_token = create_final_access_token(user.id, user.email, user.is_superuser)

    return AccessTokenResponse(access_token=access_token, token_type="bearer", mfa_ok=True)


# ================================
# 3. SMS FALLBACK
# ================================

@router.post("/sms/send", response_model=SMSSendResponse)
async def sms_send(
    request: Request,
    token_data: dict = Depends(require_mfa_pending),
    db: Session = Depends(get_db)
):
    """
    Envoie un OTP SMS (fallback si TOTP indisponible).

    Pré-requis:
    - token mfa_pending
    - phone_e164 vérifié

    Rate limit: 1/min, 3/heure.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit strict: 1/min et 3/heure
    client_ip = get_client_ip(request)
    check_rate_limit(f"sms_send:{user_id}", max_requests=1, window_seconds=60)
    check_rate_limit(f"sms_send_hourly:{user_id}", max_requests=3, window_seconds=3600)

    if not user.phone_e164 or not user.is_phone_verified:
        raise HTTPException(status_code=400, detail="Phone number not verified")

    # Envoyer OTP
    result = await sms_otp_service.send_otp(user_id, user.phone_e164)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send SMS"))

    return SMSSendResponse(
        success=True,
        message_id=result.get("message_id"),
        expires_at=result.get("expires_at"),
        message=f"SMS sent to {user.phone_e164[-4:]}. Code valid for 5 minutes."
    )


# ================================
# 4. PHONE VERIFICATION
# ================================

@router.post("/phone/set")
async def phone_set(
    request: Request,
    body: PhoneSetRequest,
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Configure le numéro de téléphone et envoie un OTP de vérification.

    Pré-requis: token complet.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 3/heure
    check_rate_limit(f"phone_set:{user_id}", max_requests=3, window_seconds=3600)

    # Mettre à jour le numéro (non vérifié)
    user.phone_e164 = body.phone
    user.is_phone_verified = False
    db.commit()

    # Envoyer OTP de vérification
    result = await sms_otp_service.send_otp(user_id, body.phone)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send verification SMS"))

    log_mfa_event("phone_set", user_id=user.id, result="success", ip_address=get_client_ip(request))

    return {
        "success": True,
        "message": f"Verification code sent to {body.phone}. Use /mfa/phone/verify to confirm.",
        "expires_at": result.get("expires_at")
    }


@router.post("/phone/verify")
async def phone_verify(
    request: Request,
    body: SMSVerifyRequest,
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Vérifie le numéro de téléphone avec l'OTP reçu.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit
    check_rate_limit(f"phone_verify:{user_id}", max_requests=10, window_seconds=60)

    if not user.phone_e164:
        raise HTTPException(status_code=400, detail="No phone number set. Call /mfa/phone/set first.")

    # Vérifier OTP
    is_valid = await sms_otp_service.verify_otp(user_id, body.code)

    if not is_valid:
        log_mfa_event("phone_verify", user_id=user.id, result="failure", ip_address=get_client_ip(request))
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    # Marquer comme vérifié
    user.is_phone_verified = True
    user.phone_verified_at = datetime.now(timezone.utc)
    db.commit()

    log_mfa_event("phone_verify", user_id=user.id, result="success", ip_address=get_client_ip(request))

    return {
        "success": True,
        "message": f"Phone number {user.phone_e164} verified successfully"
    }


# ================================
# 5. RECOVERY CODES MANAGEMENT
# ================================

@router.post("/recovery/regenerate")
async def recovery_regenerate(
    request: Request,
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Régénère les recovery codes (invalide tous les anciens).

    Retourne les nouveaux codes UNE SEULE FOIS.

    Pré-requis: token complet.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Rate limit: 3/jour
    check_rate_limit(f"recovery_regenerate:{user_id}", max_requests=3, window_seconds=86400)

    # Générer nouveaux codes
    codes_plain = recovery_service.generate_codes(10)
    codes_hashes = recovery_service.hash_codes(codes_plain)

    user.recovery_codes_hashes = codes_hashes
    user.recovery_codes_generated_at = datetime.now(timezone.utc)
    db.commit()

    log_mfa_event("recovery_regenerate", user_id=user.id, result="success", ip_address=get_client_ip(request))

    return {
        "success": True,
        "recovery_codes": codes_plain,
        "message": "Save these codes in a safe place. They will not be shown again."
    }


@router.get("/recovery/list")
async def recovery_list(
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Liste les recovery codes (format masqué: ****-XX34).

    Utile pour que l'utilisateur sache combien il lui reste.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    if not user.recovery_codes_hashes:
        return {
            "count": 0,
            "codes": [],
            "message": "No recovery codes available. Generate them with /mfa/recovery/regenerate."
        }

    # Retourner masqué (on ne peut pas démasquer, c'est un hash!)
    count = len(user.recovery_codes_hashes)

    return {
        "count": count,
        "message": f"You have {count} recovery codes remaining. Codes cannot be displayed (hashed)."
    }


# ================================
# 6. BACKUP METHOD
# ================================

@router.post("/backup/set")
async def backup_method_set(
    request: Request,
    body: BackupMethodRequest,
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Configure la méthode de secours MFA (sms ou none).

    Pré-requis: token complet.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    # Valider cohérence
    if body.method == MFABackupMethod.SMS and (not user.phone_e164 or not user.is_phone_verified):
        raise HTTPException(status_code=400, detail="Cannot set SMS backup without verified phone number")

    user.mfa_backup_method = body.method
    db.commit()

    log_mfa_event("backup_method_set", user_id=user.id, result="success",
                  extra_data={"method": body.method.value}, ip_address=get_client_ip(request))

    return {
        "success": True,
        "backup_method": body.method.value,
        "message": f"Backup method set to: {body.method.value}"
    }


# ================================
# 7. STATUS / INFO
# ================================

@router.get("/status")
async def mfa_status(
    token_data: dict = Depends(require_mfa_completed),
    db: Session = Depends(get_db)
):
    """
    Retourne le statut MFA de l'utilisateur.

    Utile pour l'interface frontend.
    """
    user_id = int(token_data["sub"])
    user = get_user_by_id(db, user_id)

    return {
        "user_id": user.id,
        "email": user.email,
        "totp_enabled": user.is_totp_enabled,
        "totp_enrolled_at": user.totp_enrolled_at.isoformat() if user.totp_enrolled_at else None,
        "phone_number": user.phone_e164 if user.is_phone_verified else None,
        "phone_verified": user.is_phone_verified,
        "backup_method": user.mfa_backup_method.value if user.mfa_backup_method else "none",
        "recovery_codes_count": len(user.recovery_codes_hashes) if user.recovery_codes_hashes else 0,
        "mfa_enforced": user.mfa_enforced,
        "is_locked": user.mfa_lock_until > datetime.now(timezone.utc) if user.mfa_lock_until else False
    }
