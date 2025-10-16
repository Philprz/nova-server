# core/logging.py - Système de logging structuré JSON pour MFA

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """
    Formatter pour logs structurés au format JSON.
    Facilite l'indexation dans des systèmes comme ELK, Datadog, etc.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Ajouter les champs personnalisés (via extra={})
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "ip_address"):
            log_data["ip_address"] = record.ip_address
        if hasattr(record, "user_agent"):
            log_data["user_agent"] = record.user_agent
        if hasattr(record, "mfa_event"):
            log_data["mfa_event"] = record.mfa_event
        if hasattr(record, "mfa_method"):
            log_data["mfa_method"] = record.mfa_method
        if hasattr(record, "result"):
            log_data["result"] = record.result

        # Exception si présente
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


def setup_mfa_logger(name: str = "nova.mfa", log_file: Optional[str] = None) -> logging.Logger:
    """
    Configure un logger structuré pour les événements MFA.

    Args:
        name: Nom du logger (hiérarchie: nova.mfa.totp, nova.mfa.sms, etc.)
        log_file: Chemin optionnel vers un fichier de logs dédié MFA

    Returns:
        Logger configuré avec JSON formatter

    Usage:
        logger = setup_mfa_logger("nova.mfa.totp")
        logger.info(
            "TOTP verification attempt",
            extra={
                "user_id": user.id,
                "ip_address": client_ip,
                "mfa_event": "totp_verify",
                "result": "success"
            }
        )
    """
    logger = logging.getLogger(name)

    # Éviter duplication si déjà configuré
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Handler console (JSON)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)

    # Handler fichier (JSON) si spécifié
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

    return logger


# Logger MFA global
mfa_logger = setup_mfa_logger("nova.mfa", log_file="logs/mfa.log")


def log_mfa_event(
    event: str,
    user_id: Optional[int] = None,
    result: str = "unknown",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    mfa_method: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Helper pour logger les événements MFA de manière standardisée.

    Args:
        event: Type d'événement (totp_enroll, totp_verify, sms_send, etc.)
        user_id: ID utilisateur
        result: success, failure, error, rate_limited, locked
        ip_address: IP du client
        user_agent: User-Agent HTTP
        mfa_method: totp, sms, recovery
        extra_data: Données supplémentaires (sans secrets!)

    Exemples:
        log_mfa_event("totp_enroll_start", user_id=42, result="success", ip_address="1.2.3.4")
        log_mfa_event("totp_verify", user_id=42, result="failure", mfa_method="totp")
        log_mfa_event("sms_sent", user_id=42, result="success", mfa_method="sms")
    """
    log_context = {
        "user_id": user_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "mfa_event": event,
        "mfa_method": mfa_method,
        "result": result,
    }

    if extra_data:
        log_context.update(extra_data)

    # Filtrer les None
    log_context = {k: v for k, v in log_context.items() if v is not None}

    level = logging.INFO
    if result in ("failure", "error", "locked"):
        level = logging.WARNING
    elif result == "rate_limited":
        level = logging.ERROR

    mfa_logger.log(level, f"MFA event: {event}", extra=log_context)


def log_mfa_metrics(metric_name: str, value: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
    """
    Log métrique MFA simple (compteur).

    Args:
        metric_name: Nom de la métrique (mfa_totp_success, mfa_sms_sent, etc.)
        value: Valeur (par défaut 1 pour compteur)
        labels: Labels additionnels (method=totp, result=success)

    Peut être intégré avec Prometheus, StatsD, etc.
    """
    metric_data = {
        "metric": metric_name,
        "value": value,
        "labels": labels or {},
    }

    mfa_logger.info(f"Metric: {metric_name}", extra={"metric_data": metric_data})
