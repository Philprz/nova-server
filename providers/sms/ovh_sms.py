# providers/sms/ovh_sms.py - Implémentation OVH SMS API

import os
from typing import Optional
import httpx
import ovh
from .base import SMSProvider, SMSResult


class OVHSMSProvider(SMSProvider):
    """
    Provider SMS via API OVH.

    Configuration requise (variables d'environnement):
    - OVH_APP_KEY: Application Key
    - OVH_APP_SECRET: Application Secret
    - OVH_CONSUMER_KEY: Consumer Key (token avec droits SMS)
    - OVH_SMS_ACCOUNT: Nom du compte SMS (ex: sms-ab12345-1)
    - OVH_SMS_SENDER: Nom d'expéditeur (max 11 chars, ex: ITSPIRIT)

    Documentation OVH SMS API:
    https://docs.ovh.com/fr/sms/envoyer-des-sms-depuis-une-url-http/

    Usage:
        provider = OVHSMSProvider()
        result = await provider.send_sms("+33612345678", "Votre code: 123456")
    """

    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        consumer_key: Optional[str] = None,
        sms_account: Optional[str] = None,
        sender: Optional[str] = None
    ):
        """
        Initialise le provider OVH.

        Args:
            app_key: OVH Application Key (défaut: env OVH_APP_KEY)
            app_secret: OVH Application Secret (défaut: env OVH_APP_SECRET)
            consumer_key: OVH Consumer Key (défaut: env OVH_CONSUMER_KEY)
            sms_account: Compte SMS (défaut: env OVH_SMS_ACCOUNT)
            sender: Nom d'expéditeur (défaut: env OVH_SMS_SENDER ou "ITSPIRIT")
        """
        self.app_key = app_key or os.getenv("OVH_APP_KEY")
        self.app_secret = app_secret or os.getenv("OVH_APP_SECRET")
        self.consumer_key = consumer_key or os.getenv("OVH_CONSUMER_KEY")
        self.sms_account = sms_account or os.getenv("OVH_SMS_ACCOUNT")
        self.sender = sender or os.getenv("OVH_SMS_SENDER", "ITSPIRIT")

        # Validation
        if not all([self.app_key, self.app_secret, self.consumer_key, self.sms_account]):
            raise ValueError(
                "OVH SMS configuration incomplete. Required: "
                "OVH_APP_KEY, OVH_APP_SECRET, OVH_CONSUMER_KEY, OVH_SMS_ACCOUNT"
            )

        # Client OVH
        try:
            self.client = ovh.Client(
                endpoint='ovh-eu',  # Europe
                application_key=self.app_key,
                application_secret=self.app_secret,
                consumer_key=self.consumer_key,
            )
        except Exception as e:
            raise ValueError(f"Failed to initialize OVH client: {e}")

    async def send_sms(self, to: str, message: str) -> SMSResult:
        """
        Envoie un SMS via API OVH.

        Args:
            to: Numéro au format E.164 (+33612345678)
            message: Contenu du SMS

        Returns:
            SMSResult
        """
        try:
            # Normaliser le numéro (OVH accepte +33... ou 0033...)
            to_normalized = to.strip()
            if not to_normalized.startswith("+"):
                to_normalized = f"+{to_normalized}"

            # Appel API OVH (POST /sms/{serviceName}/jobs)
            result = self.client.post(
                f'/sms/{self.sms_account}/jobs',
                charset='UTF-8',
                coding='7bit',
                message=message,
                receivers=[to_normalized],
                priority='high',
                sender=self.sender,
                senderForResponse=False,
                noStopClause=False,
            )

            # Réponse OVH: {"totalCreditsRemoved": 1, "invalidReceivers": [], "ids": [123456789], "validReceivers": ["+33612345678"]}
            message_id = str(result.get('ids', [None])[0])
            valid_receivers = result.get('validReceivers', [])

            if to_normalized not in valid_receivers:
                return SMSResult(
                    success=False,
                    error=f"Invalid receiver: {to}",
                    provider="ovh"
                )

            return SMSResult(
                success=True,
                message_id=message_id,
                provider="ovh",
                extra_data=result
            )

        except ovh.exceptions.APIError as e:
            # Erreur API OVH (quota, numéro invalide, etc.)
            error_msg = f"OVH API error: {e}"
            return SMSResult(
                success=False,
                error=error_msg,
                provider="ovh"
            )

        except Exception as e:
            # Erreur réseau/autre
            error_msg = f"OVH SMS send failed: {str(e)}"
            return SMSResult(
                success=False,
                error=error_msg,
                provider="ovh"
            )

    def get_provider_name(self) -> str:
        return "ovh"

    async def check_balance(self) -> Optional[float]:
        """
        Vérifie le crédit SMS restant.

        Returns:
            Nombre de crédits SMS (float) ou None si erreur

        Note: 1 crédit = 1 SMS de 160 caractères.
        """
        try:
            # GET /sms/{serviceName}
            sms_info = self.client.get(f'/sms/{self.sms_account}')
            credits_left = sms_info.get('creditsLeft', 0)

            return float(credits_left)

        except Exception as e:
            print(f"Failed to check OVH SMS balance: {e}")
            return None
