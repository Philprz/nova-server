"""
NOVA SAP Validator
Valide les credentials SAP d'un utilisateur de façon stateless.

Stratégie en deux étapes :
1. Si le serveur NOVA a déjà une session SAP active pour le même utilisateur/société,
   les credentials sont forcément valides — on court-circuite le second login.
2. Sinon, on tente un login SAP direct (stateless, session discardée).
"""

import httpx
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TIMEOUT = 15.0


def _nova_session_covers(username: str, company_db: str) -> bool:
    """
    Vérifie si le serveur NOVA a déjà une session SAP active
    pour cet utilisateur et cette société.
    Si oui, les credentials sont valides par définition.
    """
    try:
        from services.sap_business_service import get_sap_business_service
        svc = get_sap_business_service()
        if (
            svc.session_id
            and svc.session_timeout
            and datetime.now() < svc.session_timeout
            and (svc.username or "").lower() == username.lower()
            and (svc.company_db or "").lower() == company_db.lower()
        ):
            logger.info(
                "SAP validation via session NOVA existante : %s@%s", username, company_db
            )
            return True
    except Exception as e:
        logger.debug("_nova_session_covers: %s", e)
    return False


async def validate_sap_credentials(
    sap_base_url: str,
    company_db: str,
    username: str,
    password: str,
) -> bool:
    """
    Valide les credentials SAP.
    Retourne True si valides, False dans tous les autres cas.
    Ne stocke pas de session SAP.
    """
    # Court-circuit : session NOVA déjà active pour cet utilisateur
    if _nova_session_covers(username, company_db):
        return True

    # Sinon : login SAP direct (stateless)
    try:
        login_data = {
            "CompanyDB": company_db,
            "UserName":  username,
            "Password":  password,
        }
        async with httpx.AsyncClient(verify=False, timeout=TIMEOUT) as client:
            response = await client.post(f"{sap_base_url}/Login", json=login_data)

        if response.status_code == 200:
            logger.info("SAP validation OK : %s@%s", username, company_db)
            return True

        # Code SAP 305 = "User Already Logged In" → credentials corrects
        if response.status_code in (400, 409):
            try:
                body = response.json()
                sap_code = (body.get("error") or {}).get("code")
                if sap_code == 305:
                    logger.info(
                        "SAP validation OK (user already logged in) : %s@%s",
                        username, company_db,
                    )
                    return True
            except Exception:
                pass

        logger.warning(
            "SAP validation refusée : %s@%s — HTTP %s",
            username, company_db, response.status_code,
        )
        return False

    except httpx.TimeoutException:
        logger.error("SAP validation timeout : %s", sap_base_url)
        return False
    except Exception as e:
        logger.error("SAP validation erreur réseau : %s", e)
        return False
