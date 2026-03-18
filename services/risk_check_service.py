"""
Risk Check Service — Vérification solvabilité / risque client via Pappers.

Intégré dans le pipeline email APRÈS identification client (Phase 4).
Ne bloque jamais le pipeline : toujours FAIL-SAFE.

Statuts retournés :
  OK       → entreprise saine
  WARNING  → redressement judiciaire ou sauvegarde
  BLOCKED  → liquidation judiciaire
  UNKNOWN  → API indisponible ou erreur
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PAPPERS_BASE_URL = os.getenv("PAPPERS_URL", "https://api.pappers.fr/v2").rstrip("/")
_PAPPERS_API_KEY = os.getenv("PAPPERS_API_KEY", os.getenv("PAPPERS_API", ""))

_TIMEOUT_S = 4.0  # < 500 ms budget impossible sur réseau externe : 4 s est le compromis raisonnable

# Types de procédures collectives Pappers → niveau de risque
_LIQUIDATION_TYPES = {
    "liquidation judiciaire",
    "liquidation judiciaire simplifiée",
    "clôture pour insuffisance d'actif",
    "clôture de liquidation judiciaire",
}
_WARNING_TYPES = {
    "redressement judiciaire",
    "sauvegarde",
    "sauvegarde financière accélérée",
    "sauvegarde accélérée",
}


def _classify_procedures(procedures: list) -> tuple[str, str]:
    """
    Analyse la liste des procédures collectives Pappers.

    Returns:
        (status, reason) avec status = OK | WARNING | BLOCKED
    """
    if not procedures:
        return "OK", "Aucune procédure collective"

    for proc in procedures:
        type_proc = (proc.get("type", "") or "").lower().strip()

        if any(liq in type_proc for liq in _LIQUIDATION_TYPES):
            date_info = proc.get("date_jugement") or proc.get("date_ouverture", "")
            return (
                "BLOCKED",
                f"Liquidation judiciaire{' depuis le ' + date_info if date_info else ''}"
            )

    for proc in procedures:
        type_proc = (proc.get("type", "") or "").lower().strip()
        if any(warn in type_proc for warn in _WARNING_TYPES):
            date_info = proc.get("date_jugement") or proc.get("date_ouverture", "")
            return (
                "WARNING",
                f"Procédure collective : {proc.get('type', type_proc)}"
                f"{' depuis le ' + date_info if date_info else ''}"
            )

    return "OK", f"{len(procedures)} procédure(s) ancienne(s) clôturée(s)"


_LABELS = {
    "OK":      "Client vérifié",
    "WARNING": "Risque détecté",
    "BLOCKED": "Client bloqué",
    "UNKNOWN": "Vérification indisponible",
}


async def get_company_risk(
    company_name: Optional[str] = None,
    siren: Optional[str] = None,
) -> dict:
    """
    Vérifie le risque financier d'une entreprise via l'API Pappers.

    Args:
        company_name: Nom de l'entreprise (utilisé si SIREN absent)
        siren: Numéro SIREN (9 chiffres, prioritaire sur le nom)

    Returns:
        dict avec clés :
            status      → "OK" | "WARNING" | "BLOCKED" | "UNKNOWN"
            label       → texte court pour affichage UI
            reason      → explication lisible
            source      → "pappers"
            checked_at  → ISO datetime de la vérification
            country     → "FR" si SIREN présent ou trouvé dans Pappers, "OTHER" sinon
            raw         → réponse brute Pappers (ou {})
    """
    country = "FR" if siren else "OTHER"

    if not company_name and not siren:
        return _unknown("Aucun identifiant fourni (name/siren)", country)

    if not _PAPPERS_API_KEY:
        logger.warning("risk_check: PAPPERS_API_KEY absent — vérification impossible")
        return _unknown("Clé API Pappers non configurée", country)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, verify=False) as client:
            if siren:
                result = await _check_by_siren(client, siren)
            else:
                result = await _check_by_name(client, company_name)

        result = _enrich(result, country)
        logger.info(
            "event=client_risk_check client=%s siren=%s risk_status=%s reason=%s",
            company_name, siren, result["status"], result["reason"]
        )
        return result

    except httpx.TimeoutException:
        logger.warning("risk_check: timeout après %.1fs pour %s/%s", _TIMEOUT_S, company_name, siren)
        return _unknown("Timeout API Pappers", country)
    except Exception as exc:
        logger.warning("risk_check: erreur inattendue pour %s/%s : %s", company_name, siren, exc)
        return _unknown(f"Erreur API : {exc}", country)


async def _check_by_siren(client: httpx.AsyncClient, siren: str) -> dict:
    """Appel Pappers GET /entreprise?q={siren}."""
    clean_siren = siren.replace(" ", "").replace(".", "")[:9]
    url = f"{_PAPPERS_BASE_URL}/entreprise"
    params = {
        "api_token": _PAPPERS_API_KEY,
        "q": clean_siren,
        "procedures_collectives": 1,
    }
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    # Statut RCS (radiée, active…)
    statut_rcs = (data.get("statut_rcs") or "").lower()
    if "radiée" in statut_rcs or "radiee" in statut_rcs:
        return {
            "status": "BLOCKED",
            "reason": f"Entreprise radiée du RCS ({data.get('statut_rcs', '')})",
            "source": "pappers",
            "raw": data,
        }

    procedures = data.get("procedures_collectives") or []
    status, reason = _classify_procedures(procedures)
    return {"status": status, "reason": reason, "source": "pappers", "raw": data}


async def _check_by_name(client: httpx.AsyncClient, name: str) -> dict:
    """Recherche par nom puis vérification du premier résultat."""
    url = f"{_PAPPERS_BASE_URL}/recherche"
    params = {
        "api_token": _PAPPERS_API_KEY,
        "q": name,
        "longueur": 1,
        "procedures_collectives": 1,
    }
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    resultats = data.get("resultats") or []
    if not resultats:
        return {
            "status": "UNKNOWN",
            "reason": f"Entreprise '{name}' introuvable dans Pappers",
            "source": "pappers",
            "raw": data,
        }

    entreprise = resultats[0]
    procedures = entreprise.get("procedures_collectives") or []
    statut_rcs = (entreprise.get("statut_rcs") or "").lower()

    if "radiée" in statut_rcs or "radiee" in statut_rcs:
        return {
            "status": "BLOCKED",
            "reason": f"Entreprise radiée du RCS ({entreprise.get('statut_rcs', '')})",
            "source": "pappers",
            "country": "FR",  # Pappers = registre français uniquement
            "raw": entreprise,
        }

    status, reason = _classify_procedures(procedures)
    # Pappers est un registre exclusivement français : si l'entreprise est trouvée, elle est FR
    return {"status": status, "reason": reason, "source": "pappers", "country": "FR", "raw": entreprise}


def _enrich(result: dict, country: str) -> dict:
    """Ajoute label, checked_at et country au résultat.
    Si le résultat contient déjà un country (ex: trouvé dans Pappers par nom → FR),
    on le conserve plutôt que d'écraser avec la valeur par défaut.
    """
    from datetime import datetime
    result["label"] = _LABELS.get(result["status"], "Inconnu")
    result["checked_at"] = datetime.utcnow().isoformat() + "Z"
    if "country" not in result:
        result["country"] = country
    return result


def _unknown(reason: str, country: str = "OTHER") -> dict:
    from datetime import datetime
    return {
        "status": "UNKNOWN",
        "label": _LABELS["UNKNOWN"],
        "reason": reason,
        "source": "pappers",
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "country": country,
        "raw": {},
    }


def is_blocked(risk: dict) -> bool:
    """Retourne True si le risque est BLOCKED (liquidation judiciaire)."""
    return risk.get("status") == "BLOCKED"


def is_risky(risk: dict) -> bool:
    """Retourne True si le risque est WARNING ou BLOCKED."""
    return risk.get("status") in ("WARNING", "BLOCKED")
