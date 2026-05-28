"""Service d'authentification SAP B1 Service Layer.

Port Python de apps/api/src/services/sap-auth.service.ts (projet BILLING).
Le B1SESSION reçu de SAP est conservé côté serveur uniquement ; jamais exposé
au navigateur. Les classes d'erreur SapAuthError et SapSessionExpiredError
conservent la même sémantique que la version TypeScript.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from services.sap_tls import SAP_VERIFY

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = (os.getenv("SAP_REST_BASE_URL") or "").rstrip("/")
_SAP_LANG = os.getenv("SAP_LANG", "FR")
_TIMEOUT_SECONDS = 15.0


class SapAuthError(Exception):
    """SAP a refusé l'authentification ou est injoignable."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class SapSessionExpiredError(Exception):
    """SAP a renvoyé 401 sur un appel post-login : le B1SESSION n'est plus valide.

    Le handler appelant doit purger la session NOVA PA et renvoyer
    401 SESSION_EXPIRED au front.
    """

    def __init__(self, context: str = "B1SESSION expiré") -> None:
        super().__init__(context)


@dataclass(frozen=True)
class SapLoginResult:
    b1_session: str
    sap_cookie_header: str
    session_timeout_minutes: int


def normalize_sap_cookie_header(sap_session_cookie: str) -> str:
    """Si on reçoit seulement une valeur brute B1SESSION, on la rétablit en `B1SESSION=...`."""
    return sap_session_cookie if "=" in sap_session_cookie else f"B1SESSION={sap_session_cookie}"


def _extract_cookie_value(cookie_header: str, name: str) -> Optional[str]:
    match = re.search(rf"{re.escape(name)}=([^;,\s]+)", cookie_header)
    return match.group(1) if match else None


def _extract_sap_cookie_header(response: httpx.Response) -> Optional[str]:
    """Recompose un header Cookie unique à partir des Set-Cookie SAP.

    SAP peut renvoyer plusieurs Set-Cookie (B1SESSION, ROUTEID, HASH_B1SESSION) ;
    httpx les expose tous via headers.get_list("set-cookie").
    """
    raw_set_cookies = response.headers.get_list("set-cookie")
    cookie_map: dict[str, str] = {}
    for header in raw_set_cookies:
        if not header:
            continue
        for name in ("B1SESSION", "ROUTEID", "HASH_B1SESSION"):
            value = _extract_cookie_value(header, name)
            if value:
                cookie_map[name] = value

    if "B1SESSION" not in cookie_map:
        return None
    return "; ".join(f"{n}={v}" for n, v in cookie_map.items())


async def sap_login(
    company_db: str,
    user_name: str,
    password: str,
    *,
    base_url: Optional[str] = None,
) -> SapLoginResult:
    """Appelle POST {base_url}/Login sur SAP Service Layer.

    base_url permet de surcharger SAP_REST_BASE_URL (utile pour le cas
    multi-société où society.sap_base_url prime). Lève SapAuthError si
    SAP refuse ou est injoignable.
    """
    effective_base = (base_url or _DEFAULT_BASE_URL or "").rstrip("/")
    if not effective_base:
        raise SapAuthError("SAP_REST_BASE_URL non configurée", 500)

    payload: dict[str, object] = {
        "CompanyDB": company_db,
        "UserName": user_name,
        "Password": password,
    }
    # Language n'est inclus que si SAP_LANG est un code numérique entier.
    try:
        payload["Language"] = int(_SAP_LANG)
    except (TypeError, ValueError):
        pass

    try:
        async with httpx.AsyncClient(verify=SAP_VERIFY, timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{effective_base}/Login", json=payload)
    except httpx.HTTPError as err:
        raise SapAuthError(f"Impossible de joindre SAP B1 : {err}", 502) from err

    if response.status_code >= 400:
        detail = "Identifiants incorrects ou accès refusé"
        try:
            body = response.json()
            err_obj = body.get("error") if isinstance(body, dict) else None
            msg_obj = err_obj.get("message") if isinstance(err_obj, dict) else None
            if isinstance(msg_obj, dict) and isinstance(msg_obj.get("value"), str):
                detail = msg_obj["value"]
        except Exception:
            pass
        code = 401 if response.status_code in (401, 403) else 400
        raise SapAuthError(detail, code)

    sap_cookie_header = _extract_sap_cookie_header(response)
    b1_session = _extract_cookie_value(sap_cookie_header, "B1SESSION") if sap_cookie_header else None
    if not sap_cookie_header or not b1_session:
        raise SapAuthError("Réponse SAP invalide : B1SESSION absent", 502)

    timeout_minutes = 30
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("SessionTimeout"), (int, float)):
            timeout_minutes = int(body["SessionTimeout"])
    except Exception:
        pass

    return SapLoginResult(
        b1_session=b1_session,
        sap_cookie_header=sap_cookie_header,
        session_timeout_minutes=timeout_minutes,
    )


async def sap_logout(sap_cookie_header: str, *, base_url: Optional[str] = None) -> None:
    """Best-effort logout SAP. Si SAP est injoignable, la session expirera côté SAP."""
    effective_base = (base_url or _DEFAULT_BASE_URL or "").rstrip("/")
    if not effective_base:
        return
    try:
        async with httpx.AsyncClient(verify=SAP_VERIFY, timeout=_TIMEOUT_SECONDS) as client:
            await client.post(
                f"{effective_base}/Logout",
                headers={"Cookie": normalize_sap_cookie_header(sap_cookie_header)},
            )
    except httpx.HTTPError as err:
        logger.warning("sap_logout best-effort failed: %s", err)


async def sap_ping(sap_cookie_header: str, *, base_url: Optional[str] = None) -> bool:
    """Ping léger pour maintenir/valider la session SAP."""
    effective_base = (base_url or _DEFAULT_BASE_URL or "").rstrip("/")
    if not effective_base:
        return False
    try:
        async with httpx.AsyncClient(verify=SAP_VERIFY, timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{effective_base}/CompanyService_GetCompanyInfo",
                headers={
                    "Cookie": normalize_sap_cookie_header(sap_cookie_header),
                    "Content-Type": "application/json",
                },
                content="{}",
            )
        return response.status_code < 400
    except httpx.HTTPError:
        return False
