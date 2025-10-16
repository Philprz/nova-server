# providers/sms/base.py - Interface abstraite pour les providers SMS

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SMSResult:
    """
    Résultat d'envoi SMS.

    Attributes:
        success: True si SMS envoyé avec succès
        message_id: ID du message (SID chez Twilio, messageId chez OVH)
        error: Message d'erreur si échec
        provider: Nom du provider (ovh, twilio, mock)
        extra_data: Données supplémentaires du provider
    """
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    provider: str = "unknown"
    extra_data: Optional[Dict[str, Any]] = None


class SMSProvider(ABC):
    """
    Interface abstraite pour les providers SMS.

    Implémentations:
    - OVHSMSProvider (priorité)
    - TwilioSMSProvider (fallback)
    - MockSMSProvider (dev/tests)

    Usage:
        provider = OVHSMSProvider(...)
        result = await provider.send_sms("+33612345678", "Votre code: 123456")
        if result.success:
            print(f"SMS envoyé: {result.message_id}")
        else:
            print(f"Erreur: {result.error}")
    """

    @abstractmethod
    async def send_sms(self, to: str, message: str) -> SMSResult:
        """
        Envoie un SMS.

        Args:
            to: Numéro destinataire au format E.164 (+33612345678)
            message: Contenu du SMS (max 160 caractères pour 1 crédit)

        Returns:
            SMSResult avec success, message_id, error

        Raises:
            Exception en cas d'erreur réseau/configuration
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Retourne le nom du provider (ovh, twilio, mock)."""
        pass

    @abstractmethod
    async def check_balance(self) -> Optional[float]:
        """
        Vérifie le crédit restant (si supporté par le provider).

        Returns:
            Crédit restant (float) ou None si non supporté

        Note: OVH retourne nombre de crédits, Twilio balance en USD.
        """
        pass


class MockSMSProvider(SMSProvider):
    """
    Provider SMS de test (dev/CI).
    Ne fait aucun appel externe, log uniquement.

    Usage:
        provider = MockSMSProvider()
        result = await provider.send_sms("+33612345678", "Test")
        # Toujours success=True, message_id="mock_..."
    """

    def __init__(self):
        self._sent_messages: list = []

    async def send_sms(self, to: str, message: str) -> SMSResult:
        """Simule l'envoi d'un SMS (success=True)."""
        import secrets

        message_id = f"mock_{secrets.token_hex(8)}"

        self._sent_messages.append({
            "to": to,
            "message": message,
            "message_id": message_id
        })

        print(f"[MockSMS] Sent to {to}: {message[:50]}... (ID: {message_id})")

        return SMSResult(
            success=True,
            message_id=message_id,
            provider="mock"
        )

    def get_provider_name(self) -> str:
        return "mock"

    async def check_balance(self) -> Optional[float]:
        """Mock: crédit illimité."""
        return 999999.0

    def get_sent_messages(self) -> list:
        """Helper pour tests: récupère les SMS envoyés."""
        return self._sent_messages

    def clear(self) -> None:
        """Helper pour tests: vide l'historique."""
        self._sent_messages.clear()
