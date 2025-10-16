# services/mfa_totp.py - Service TOTP (Time-based One-Time Password) avec pyotp

import pyotp
import qrcode
import io
import base64
from typing import Tuple, Optional
from PIL import Image


class TOTPService:
    """
    Service pour gérer TOTP (Google Authenticator, Microsoft Authenticator, Authy, etc.)
    Utilise pyotp (compatible RFC 6238).
    """

    ISSUER_NAME = "IT SPIRIT NOVA"
    DEFAULT_INTERVAL = 30  # secondes
    DEFAULT_DIGITS = 6

    @staticmethod
    def generate_secret() -> str:
        """
        Génère un secret TOTP aléatoire au format base32.

        Returns:
            Secret base32 (32 caractères, ex: "JBSWY3DPEHPK3PXP")

        Usage:
            secret = TOTPService.generate_secret()
            # Stocker en DB (chiffré en production!)
        """
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(secret: str, account_name: str, issuer: Optional[str] = None) -> str:
        """
        Génère l'URI de provisioning pour scannable par les apps authenticator.

        Args:
            secret: Secret TOTP base32
            account_name: Nom du compte (généralement email ou username)
            issuer: Nom de l'application (défaut: IT SPIRIT NOVA)

        Returns:
            URI au format otpauth://totp/...

        Exemple:
            otpauth://totp/IT%20SPIRIT%20NOVA:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=IT%20SPIRIT%20NOVA
        """
        issuer = issuer or TOTPService.ISSUER_NAME

        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=account_name, issuer_name=issuer)

        return uri

    @staticmethod
    def generate_qr_code(provisioning_uri: str, size: int = 300) -> str:
        """
        Génère un QR code scannable par les apps authenticator.

        Args:
            provisioning_uri: URI otpauth://...
            size: Taille du QR code en pixels (défaut 300x300)

        Returns:
            QR code en base64 PNG (data:image/png;base64,...)

        Usage:
            qr_base64 = TOTPService.generate_qr_code(uri)
            # Retourner au client pour affichage: <img src="{qr_base64}" />
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Redimensionner
        img = img.resize((size, size), Image.LANCZOS)

        # Convertir en base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        return f"data:image/png;base64,{img_base64}"

    @staticmethod
    def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
        """
        Vérifie un code TOTP contre le secret.

        Args:
            secret: Secret TOTP base32
            code: Code à 6 chiffres entré par l'utilisateur
            valid_window: Fenêtre de tolérance en intervalles (défaut: 1 = ±30s)
                         0 = strict (uniquement code actuel)
                         1 = tolérance ±30s (recommandé pour clock drift)
                         2 = tolérance ±60s

        Returns:
            True si code valide, False sinon

        Usage:
            is_valid = TOTPService.verify_totp(user.totp_secret, "123456")
            if is_valid:
                # Authentifier l'utilisateur
        """
        totp = pyotp.TOTP(secret)

        # pyotp.verify retourne True/False (gère valid_window automatiquement)
        return totp.verify(code, valid_window=valid_window)

    @staticmethod
    def get_current_code(secret: str) -> str:
        """
        Génère le code TOTP actuel (utile pour tests/debug).

        Args:
            secret: Secret TOTP base32

        Returns:
            Code à 6 chiffres actuel

        WARNING: Ne jamais exposer en production! Uniquement pour tests.
        """
        totp = pyotp.TOTP(secret)
        return totp.now()

    @staticmethod
    def enroll_user(account_name: str) -> Tuple[str, str, str]:
        """
        Helper pour enrôlement complet d'un utilisateur.

        Args:
            account_name: Email ou username

        Returns:
            (secret, provisioning_uri, qr_code_base64)

        Usage:
            secret, uri, qr = TOTPService.enroll_user("user@example.com")
            # 1. Sauvegarder secret en DB (chiffré!)
            # 2. Retourner uri + qr au client
            # 3. Client scanne QR ou saisit secret manuellement
            # 4. Client soumet un code pour vérification
        """
        secret = TOTPService.generate_secret()
        uri = TOTPService.get_provisioning_uri(secret, account_name)
        qr_code = TOTPService.generate_qr_code(uri)

        return secret, uri, qr_code


# Instance globale (stateless, pas besoin de configuration)
totp_service = TOTPService()
