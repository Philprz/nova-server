"""
Service de chiffrement symetrique pour les cles API stockees en base
(LLM providers, secrets admin).

Cle lue depuis NOVA_ENCRYPTION_KEY. Si absente, le serveur refuse de demarrer
et logge une cle generee a usage unique pour configuration manuelle.
"""

import os
import sys
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


_ENV_VAR = "NOVA_ENCRYPTION_KEY"
_fernet: Optional[Fernet] = None


def _load_fernet() -> Fernet:
    """
    Charge la cle Fernet depuis l'environnement. Erreur fatale si absente.
    """
    key = os.getenv(_ENV_VAR)
    if not key:
        generated = Fernet.generate_key().decode()
        logger.warning(
            "%s manquant. Cle generee a usage unique : %s "
            "(ajouter au .env puis redemarrer)",
            _ENV_VAR, generated,
        )
        print(
            f"ERROR: {_ENV_VAR} not set in environment.\n"
            f"Generated key (add to .env then restart): {generated}",
            file=sys.stderr,
        )
        raise RuntimeError(
            f"{_ENV_VAR} required for admin LLM module. See logs for generated key."
        )

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{_ENV_VAR} invalide (doit etre une cle Fernet base64 32 bytes) : {exc}"
        )


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = _load_fernet()
    return _fernet


def encrypt(value: str) -> str:
    """Chiffre une chaine et retourne le token base64 ASCII."""
    if value is None:
        raise ValueError("encrypt() refuse None")
    token = _get_fernet().encrypt(value.encode("utf-8"))
    return token.decode("ascii")


def decrypt(token: str) -> str:
    """Dechiffre un token Fernet et retourne la chaine originale."""
    if not token:
        raise ValueError("decrypt() refuse vide")
    try:
        raw = _get_fernet().decrypt(token.encode("ascii"))
    except InvalidToken as exc:
        raise ValueError(f"Token chiffre invalide ou corrompu : {exc}")
    return raw.decode("utf-8")


def mask(value: str, visible: int = 4) -> str:
    """Helper d'affichage : masque tout sauf les `visible` derniers caracteres."""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]
