# services/mfa_sms.py - Service d'OTP SMS pour MFA (génération, envoi, vérification)

import secrets
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from providers.sms.base import SMSProvider, MockSMSProvider
from providers.sms.ovh_sms import OVHSMSProvider
from providers.sms.twilio_sms import TwilioSMSProvider
from core.logging import log_mfa_event

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class SMSOTPService:
    """
    Service pour gérer les OTP SMS (One-Time Password par SMS).

    Workflow:
    1. send_otp(user_id, phone) -> Génère OTP 6 chiffres, stocke (hash + TTL), envoie SMS
    2. verify_otp(user_id, code) -> Vérifie code, consomme si valide
    3. Stockage: Redis (TTL 5min) ou in-memory (dev)

    Rate limiting géré par core/rate_limit.py (endpoints).
    """

    OTP_LENGTH = 6
    OTP_TTL_SECONDS = 300  # 5 minutes
    MAX_VERIFY_ATTEMPTS = 3  # Max 3 essais par OTP

    def __init__(self, sms_provider: Optional[SMSProvider] = None):
        """
        Initialise le service SMS OTP.

        Args:
            sms_provider: Provider SMS (auto-détection si None)
        """
        # Auto-sélection du provider SMS
        if sms_provider is None:
            sms_provider = self._get_default_provider()

        self.sms_provider = sms_provider

        # Stockage OTP (Redis ou in-memory)
        self._setup_storage()

    def _get_default_provider(self) -> SMSProvider:
        """
        Sélectionne automatiquement le provider SMS.

        Priorité:
        1. OVH si configuré (OVH_APP_KEY présent)
        2. Twilio si configuré (TWILIO_ACCOUNT_SID présent)
        3. Mock (dev/tests)
        """
        # Essayer OVH en priorité
        if os.getenv("OVH_APP_KEY"):
            try:
                return OVHSMSProvider()
            except ValueError:
                print("OVH SMS configuration incomplete, trying Twilio...")

        # Essayer Twilio en fallback
        if os.getenv("TWILIO_ACCOUNT_SID"):
            try:
                return TwilioSMSProvider()
            except ValueError:
                print("Twilio SMS configuration incomplete, using mock...")

        # Fallback: Mock (dev)
        print("No SMS provider configured, using MockSMSProvider")
        return MockSMSProvider()

    def _setup_storage(self):
        """Configure le stockage OTP (Redis ou in-memory)."""
        redis_url = os.getenv("REDIS_URL")

        if REDIS_AVAILABLE and redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                self.storage_type = "redis"
                print("SMS OTP storage: Redis")
            except Exception as e:
                print(f"Redis unavailable for SMS OTP: {e}, using in-memory")
                self.storage_type = "memory"
                self._memory_store: Dict[str, Dict[str, Any]] = {}
        else:
            self.storage_type = "memory"
            self._memory_store: Dict[str, Dict[str, Any]] = {}
            print("SMS OTP storage: in-memory")

    def _generate_otp(self) -> str:
        """Génère un OTP numérique à 6 chiffres."""
        return "".join(str(secrets.randbelow(10)) for _ in range(self.OTP_LENGTH))

    def _get_storage_key(self, user_id: int) -> str:
        """Clé de stockage pour OTP."""
        return f"mfa:sms_otp:{user_id}"

    def _store_otp(self, user_id: int, otp: str, phone: str) -> None:
        """
        Stocke l'OTP avec TTL.

        Stockage:
        {
            "otp": "123456",
            "phone": "+33612345678",
            "created_at": "2025-10-16T10:30:00",
            "attempts": 0
        }
        """
        key = self._get_storage_key(user_id)
        data = {
            "otp": otp,
            "phone": phone,
            "created_at": datetime.utcnow().isoformat(),
            "attempts": 0
        }

        if self.storage_type == "redis":
            # Stocker en JSON avec TTL
            import json
            self.redis_client.setex(key, self.OTP_TTL_SECONDS, json.dumps(data))
        else:
            # In-memory avec expiration
            expiry = datetime.utcnow() + timedelta(seconds=self.OTP_TTL_SECONDS)
            data["expiry"] = expiry
            self._memory_store[key] = data

    def _get_otp_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Récupère les données OTP stockées."""
        key = self._get_storage_key(user_id)

        if self.storage_type == "redis":
            import json
            raw = self.redis_client.get(key)
            if raw:
                return json.loads(raw)
            return None
        else:
            data = self._memory_store.get(key)
            if data:
                # Vérifier expiration
                if datetime.utcnow() < data["expiry"]:
                    return data
                else:
                    # Expiré, supprimer
                    del self._memory_store[key]
            return None

    def _increment_attempts(self, user_id: int) -> int:
        """Incrémente le compteur de tentatives."""
        key = self._get_storage_key(user_id)
        data = self._get_otp_data(user_id)

        if not data:
            return 0

        data["attempts"] += 1

        if self.storage_type == "redis":
            import json
            ttl = self.redis_client.ttl(key)
            self.redis_client.setex(key, max(ttl, 1), json.dumps(data))
        else:
            self._memory_store[key] = data

        return data["attempts"]

    def _delete_otp(self, user_id: int) -> None:
        """Supprime l'OTP après utilisation/expiration."""
        key = self._get_storage_key(user_id)

        if self.storage_type == "redis":
            self.redis_client.delete(key)
        else:
            if key in self._memory_store:
                del self._memory_store[key]

    async def send_otp(self, user_id: int, phone_e164: str) -> Dict[str, Any]:
        """
        Génère et envoie un OTP par SMS.

        Args:
            user_id: ID utilisateur
            phone_e164: Numéro au format E.164 (+33612345678)

        Returns:
            {
                "success": True/False,
                "message_id": "...",
                "expires_at": "2025-10-16T10:35:00Z",
                "error": "..." (si échec)
            }

        Rate limiting géré par l'endpoint.
        """
        # Générer OTP
        otp = self._generate_otp()

        # Stocker
        self._store_otp(user_id, otp, phone_e164)

        # Message SMS
        message = f"Votre code de vérification IT SPIRIT NOVA: {otp}\nValide 5 minutes."

        # Envoyer via provider
        result = await self.sms_provider.send_sms(phone_e164, message)

        # Log
        log_mfa_event(
            "sms_otp_sent",
            user_id=user_id,
            result="success" if result.success else "failure",
            mfa_method="sms",
            extra_data={"provider": result.provider, "message_id": result.message_id}
        )

        if result.success:
            expires_at = datetime.utcnow() + timedelta(seconds=self.OTP_TTL_SECONDS)
            return {
                "success": True,
                "message_id": result.message_id,
                "expires_at": expires_at.isoformat() + "Z",
                "provider": result.provider
            }
        else:
            return {
                "success": False,
                "error": result.error or "Failed to send SMS"
            }

    async def verify_otp(self, user_id: int, code: str) -> bool:
        """
        Vérifie un OTP SMS.

        Args:
            user_id: ID utilisateur
            code: Code saisi (6 chiffres)

        Returns:
            True si valide, False sinon

        Note:
        - Max 3 tentatives par OTP
        - Consomme l'OTP si valide (one-time)
        - Supprime l'OTP après 3 échecs
        """
        data = self._get_otp_data(user_id)

        if not data:
            log_mfa_event("sms_otp_verify", user_id=user_id, result="failure", mfa_method="sms",
                          extra_data={"reason": "no_otp_found"})
            return False

        # Vérifier le nombre de tentatives
        if data["attempts"] >= self.MAX_VERIFY_ATTEMPTS:
            log_mfa_event("sms_otp_verify", user_id=user_id, result="failure", mfa_method="sms",
                          extra_data={"reason": "max_attempts_exceeded"})
            self._delete_otp(user_id)
            return False

        # Vérifier le code
        if code.strip() == data["otp"]:
            # Valide! Consommer l'OTP
            self._delete_otp(user_id)
            log_mfa_event("sms_otp_verify", user_id=user_id, result="success", mfa_method="sms")
            return True
        else:
            # Invalide, incrémenter tentatives
            attempts = self._increment_attempts(user_id)
            log_mfa_event("sms_otp_verify", user_id=user_id, result="failure", mfa_method="sms",
                          extra_data={"attempts": attempts})

            # Supprimer après 3 échecs
            if attempts >= self.MAX_VERIFY_ATTEMPTS:
                self._delete_otp(user_id)

            return False


# Instance globale
sms_otp_service = SMSOTPService()
