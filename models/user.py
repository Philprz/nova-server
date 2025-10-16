# models/user.py - Modèle utilisateur avec support MFA/2FA

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from db.models import Base
import enum


class MFABackupMethod(str, enum.Enum):
    """Méthode de secours MFA"""
    NONE = "none"
    SMS = "sms"


class User(Base):
    """
    Modèle utilisateur avec support MFA complet.

    Champs MFA:
    - totp_secret: secret TOTP base32 (chiffré en production)
    - is_totp_enabled: si TOTP est activé
    - mfa_enforced: si MFA obligatoire pour cet utilisateur
    - recovery_codes_hashes: liste JSON de hash bcrypt des codes de récupération
    - phone_e164: numéro de téléphone au format E.164
    - is_phone_verified: si le numéro de téléphone a été vérifié
    - mfa_backup_method: méthode de secours (SMS ou none)
    - mfa_failed_attempts: compteur d'échecs de vérification MFA
    - mfa_lock_until: timestamp de verrouillage temporaire
    """
    __tablename__ = "users"

    # Champs de base
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # Champs de dates
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # === Champs MFA/2FA ===

    # TOTP (Google/Microsoft Authenticator)
    totp_secret = Column(Text, nullable=True, comment="Secret TOTP base32")
    is_totp_enabled = Column(Boolean, default=False, nullable=False, index=True)
    totp_enrolled_at = Column(DateTime(timezone=True), nullable=True, comment="Date d'activation TOTP")

    # Politique MFA
    mfa_enforced = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Si True, MFA obligatoire pour accéder aux routes sensibles"
    )

    # Recovery codes (codes de récupération one-time)
    recovery_codes_hashes = Column(
        JSONB,
        nullable=True,
        comment="Liste de hash bcrypt des recovery codes (10 codes)"
    )
    recovery_codes_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Téléphone pour SMS
    phone_e164 = Column(
        String(20),
        nullable=True,
        comment="Numéro au format E.164, ex: +33612345678"
    )
    is_phone_verified = Column(Boolean, default=False, nullable=False)
    phone_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Méthode de secours
    mfa_backup_method = Column(
        SQLEnum(MFABackupMethod, name="mfa_backup_method_enum"),
        default=MFABackupMethod.NONE,
        nullable=False,
        comment="Fallback si TOTP indisponible: sms ou none"
    )

    # Sécurité anti-bruteforce
    mfa_failed_attempts = Column(Integer, default=0, nullable=False)
    mfa_lock_until = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Verrouillage temporaire si trop d'échecs"
    )

    # Audit trail
    mfa_last_success = Column(DateTime(timezone=True), nullable=True)
    mfa_last_failure = Column(DateTime(timezone=True), nullable=True)
    mfa_last_ip = Column(String(45), nullable=True, comment="IPv4 ou IPv6")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', totp_enabled={self.is_totp_enabled})>"
