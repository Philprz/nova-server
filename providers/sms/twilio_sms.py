# providers/sms/twilio_sms.py - Implémentation Twilio SMS API (fallback optionnel)

import os
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from .base import SMSProvider, SMSResult


class TwilioSMSProvider(SMSProvider):
    """
    Provider SMS via Twilio (fallback/alternative à OVH).

    Configuration requise:
    - TWILIO_ACCOUNT_SID: Account SID Twilio
    - TWILIO_AUTH_TOKEN: Auth Token Twilio
    - TWILIO_FROM: Numéro d'expéditeur Twilio (ex: +15551234567)

    Documentation:
    https://www.twilio.com/docs/sms/api

    Usage:
        provider = TwilioSMSProvider()
        result = await provider.send_sms("+33612345678", "Votre code: 123456")
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None
    ):
        """
        Initialise le provider Twilio.

        Args:
            account_sid: Twilio Account SID (défaut: env TWILIO_ACCOUNT_SID)
            auth_token: Twilio Auth Token (défaut: env TWILIO_AUTH_TOKEN)
            from_number: Numéro d'expéditeur (défaut: env TWILIO_FROM)
        """
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.getenv("TWILIO_FROM")

        # Validation
        if not all([self.account_sid, self.auth_token, self.from_number]):
            raise ValueError(
                "Twilio SMS configuration incomplete. Required: "
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM"
            )

        # Client Twilio
        try:
            self.client = Client(self.account_sid, self.auth_token)
        except Exception as e:
            raise ValueError(f"Failed to initialize Twilio client: {e}")

    async def send_sms(self, to: str, message: str) -> SMSResult:
        """
        Envoie un SMS via Twilio.

        Args:
            to: Numéro au format E.164 (+33612345678)
            message: Contenu du SMS

        Returns:
            SMSResult
        """
        try:
            # Normaliser le numéro
            to_normalized = to.strip()
            if not to_normalized.startswith("+"):
                to_normalized = f"+{to_normalized}"

            # Appel Twilio (messages.create est synchrone, mais on wrap en async)
            twilio_message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_normalized
            )

            # Réponse Twilio: Message object avec .sid, .status, etc.
            message_id = twilio_message.sid
            status = twilio_message.status  # queued, sent, delivered, failed

            if status in ("queued", "sent", "delivered"):
                return SMSResult(
                    success=True,
                    message_id=message_id,
                    provider="twilio",
                    extra_data={
                        "status": status,
                        "price": twilio_message.price,
                        "price_unit": twilio_message.price_unit
                    }
                )
            else:
                return SMSResult(
                    success=False,
                    error=f"Twilio message status: {status}",
                    provider="twilio"
                )

        except TwilioRestException as e:
            # Erreur API Twilio (numéro invalide, quota, etc.)
            error_msg = f"Twilio API error: {e.msg} (code: {e.code})"
            return SMSResult(
                success=False,
                error=error_msg,
                provider="twilio"
            )

        except Exception as e:
            # Erreur réseau/autre
            error_msg = f"Twilio SMS send failed: {str(e)}"
            return SMSResult(
                success=False,
                error=error_msg,
                provider="twilio"
            )

    def get_provider_name(self) -> str:
        return "twilio"

    async def check_balance(self) -> Optional[float]:
        """
        Vérifie le crédit Twilio.

        Returns:
            Balance en USD (float) ou None si erreur
        """
        try:
            balance = self.client.api.v2010.balance.fetch()
            return float(balance.balance)

        except Exception as e:
            print(f"Failed to check Twilio balance: {e}")
            return None
