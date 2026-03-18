"""
NOVA SAP Validator
Valide les credentials SAP d'un utilisateur de façon stateless.
La session SAP obtenue est immédiatement discardée — NOVA n'en a pas besoin.
Pattern identique à SAPBusinessService.login() (services/sap_business_service.py).
"""

import httpx
import logging

logger = logging.getLogger(__name__)

TIMEOUT = 15.0


async def validate_sap_credentials(
    sap_base_url: str,
    company_db: str,
    username: str,
    password: str,
) -> bool:
    """
    Envoie les credentials à SAP B1 REST API.
    Retourne True si SAP répond 200, False dans tous les autres cas
    (mauvais credentials, timeout, erreur réseau).
    Ne stocke pas la session SAP.
    """
    try:
        login_data = {
            "CompanyDB": company_db,
            "UserName":  username,
            "Password":  password,
        }
        async with httpx.AsyncClient(verify=False, timeout=TIMEOUT) as client:
            response = await client.post(f"{sap_base_url}/Login", json=login_data)

        if response.status_code == 200:
            logger.info(f"SAP validation OK : {username}@{company_db}")
            return True

        logger.warning(
            f"SAP validation refusée : {username}@{company_db} — HTTP {response.status_code}"
        )
        return False

    except httpx.TimeoutException:
        logger.error(f"SAP validation timeout : {sap_base_url}")
        return False
    except Exception as e:
        logger.error(f"SAP validation erreur réseau : {e}")
        return False
