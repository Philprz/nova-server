"""
API Routes - Création de devis SAP B1 depuis NOVA.

Endpoints :
    POST /api/sap/quotation          →  Crée un devis dans SAP Business One
    POST /api/sap/quotation/preview  →  Prévisualise le payload SAP sans l'envoyer

Ce router est appelé depuis :
  - Le frontend mail-to-biz (bouton "Créer le devis SAP" + modale preview)
  - Le pipeline webhook automatique (traitement en background)
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.sap_quotation_service import (
    QuotationPayload,
    QuotationResult,
    get_sap_quotation_service,
)

logger = logging.getLogger(__name__)

# ============================================================
# LOGGING DEVIS — table quote_generation_log (email_analysis.db)
# ============================================================

_DB_PATH = str(Path(__file__).parent.parent / "email_analysis.db")


def _init_quote_log_db() -> None:
    """Crée la table quote_generation_log si elle n'existe pas."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quote_generation_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_code TEXT    NOT NULL,
                total_ht    REAL,
                marge       REAL,
                created_by  TEXT    DEFAULT 'mail-to-biz',
                sap_doc_entry INTEGER,
                sap_doc_num   INTEGER,
                status      TEXT    DEFAULT 'created',
                email_id    TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("quote_generation_log init warning: %s", exc)


def _log_quote_creation(
    client_code: str,
    total_ht: Optional[float],
    sap_doc_entry: Optional[int],
    sap_doc_num: Optional[int],
    email_id: Optional[str],
    status: str = "created",
) -> None:
    """Insère une ligne dans quote_generation_log."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            """
            INSERT INTO quote_generation_log
              (client_code, total_ht, sap_doc_entry, sap_doc_num, status, email_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (client_code, total_ht, sap_doc_entry, sap_doc_num, status, email_id,
             datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning("quote_generation_log insert warning: %s", exc)


# Initialisation au chargement du module
_init_quote_log_db()

router = APIRouter(prefix="/api/sap", tags=["SAP Quotation"])


# ============================================================
# MODÈLES RÉPONSE
# ============================================================


class QuotationResponse(BaseModel):
    """Réponse standardisée de l'endpoint création devis."""
    success: bool
    doc_entry: Optional[int] = None
    doc_num: Optional[int] = None
    doc_total: Optional[float] = None
    doc_date: Optional[str] = None
    card_code: Optional[str] = None
    card_name: Optional[str] = None
    message: str
    error_code: Optional[str] = None
    retried: bool = False
    retry_reason: Optional[str] = None
    # Payload SAP envoyé (utile pour debug, peut être supprimé en prod)
    sap_payload: Optional[dict] = None


# ============================================================
# ENDPOINTS
# ============================================================


@router.post("/quotation/preview")
async def preview_sap_quotation(payload: QuotationPayload):
    """
    Prévisualise le payload SAP qui sera envoyé à SAP Business One.

    Ne crée aucun document dans SAP — retourne uniquement la structure JSON
    qui sera utilisée lors de la confirmation, permettant une validation humaine.

    **Utilisation** : appelé par le frontend avant d'afficher la modale de confirmation.
    """
    service = get_sap_quotation_service()
    sap_payload = service._build_sap_payload(payload)

    total_ht = sum(
        line.Quantity * (line.UnitPrice or 0.0)
        for line in payload.DocumentLines
    )

    logger.info(
        "👁 POST /api/sap/quotation/preview | CardCode=%s | Lignes=%d | TotalHT=%.2f",
        payload.CardCode,
        len(payload.DocumentLines),
        total_ht,
    )

    return {
        "validation_status": "ready_for_sap",
        "client": {"CardCode": payload.CardCode},
        "lines": [line.model_dump() for line in payload.DocumentLines],
        "totals": {
            "subtotal": round(total_ht, 2),
            "lines_count": len(payload.DocumentLines),
        },
        "currency": "EUR",
        "sap_payload": sap_payload,
    }


@router.post("/quotation", response_model=QuotationResponse)
async def create_sap_quotation(payload: QuotationPayload):
    """
    Crée un devis (Sales Quotation) dans SAP Business One.

    **Champs obligatoires** :
    - `CardCode` : Code client SAP (ex: `"C00042"`)
    - `DocumentLines` : Au moins une ligne avec `ItemDescription` et `Quantity`

    **Champs optionnels** :
    - `DocDate` / `DocDueDate` : dates au format `"YYYY-MM-DD"` (défaut = aujourd'hui)
    - `Comments` : Commentaires libres (ex: objet de l'email)
    - `NumAtCard` : Référence client
    - `email_id` / `email_subject` : Traçabilité source email (non transmis à SAP)

    **Codes d'erreur possibles** :
    - `SAP_LOGIN_FAILED` : Impossible de s'authentifier auprès de SAP
    - `SAP_TIMEOUT` : Timeout 10s dépassé
    - `SAP_ERROR` : Erreur métier SAP (ex: CardCode inconnu, ItemCode invalide)
    - `INTERNAL_ERROR` : Erreur inattendue NOVA

    **Exemple minimal** :
    ```json
    {
      "CardCode": "C00042",
      "DocumentLines": [
        {
          "ItemDescription": "Piston hydraulique 50mm",
          "Quantity": 10,
          "UnitPrice": 45.50
        }
      ],
      "Comments": "Devis suite email du 20/02/2026",
      "email_id": "AAMkAGIx..."
    }
    ```
    """
    # ── Garde anti-doublons : refuser si cet email a déjà généré un devis ──
    if payload.email_id:
        try:
            conn = sqlite3.connect(_DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, sap_doc_num, created_at FROM quote_generation_log "
                "WHERE email_id = ? ORDER BY created_at DESC LIMIT 1",
                (payload.email_id,),
            ).fetchone()
            conn.close()
            if row:
                logger.warning(
                    "⚠️ Devis déjà créé pour email %s → DocNum=%s le %s — requête bloquée",
                    payload.email_id, row["sap_doc_num"], row["created_at"],
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "success": False,
                        "message": (
                            f"Un devis SAP a déjà été créé pour cet email "
                            f"(DocNum={row['sap_doc_num']}, le {row['created_at'][:10]}). "
                            "Supprimez-le dans SAP avant de recréer."
                        ),
                        "error_code": "DUPLICATE_QUOTE",
                        "existing_doc_num": row["sap_doc_num"],
                        "created_at": row["created_at"],
                    },
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Erreur vérification anti-doublons : %s", exc)

    service = get_sap_quotation_service()

    logger.info(
        "📥 POST /api/sap/quotation | CardCode=%s | Lignes=%d | EmailId=%s",
        payload.CardCode,
        len(payload.DocumentLines),
        payload.email_id or "N/A",
    )

    result: QuotationResult = await service.create_sales_quotation(payload)

    if not result.success:
        # On retourne 422 pour erreurs métier SAP, 503 pour problème de connexion
        status_code = 503 if result.error_code in ("SAP_LOGIN_FAILED", "SAP_TIMEOUT") else 422
        raise HTTPException(
            status_code=status_code,
            detail={
                "success": False,
                "message": result.message,
                "error_code": result.error_code,
            },
        )

    # Journalisation dans quote_generation_log
    _log_quote_creation(
        client_code=payload.CardCode,
        total_ht=result.doc_total,
        sap_doc_entry=result.doc_entry,
        sap_doc_num=result.doc_num,
        email_id=payload.email_id,
        status="created",
    )

    return QuotationResponse(
        success=result.success,
        doc_entry=result.doc_entry,
        doc_num=result.doc_num,
        doc_total=result.doc_total,
        doc_date=result.doc_date,
        card_code=result.card_code,
        card_name=result.card_name,
        message=result.message,
        retried=result.retried,
        retry_reason=result.retry_reason,
        sap_payload=result.sap_payload,
    )


@router.get("/quotation/by-email/{email_id}")
async def get_quotation_by_email(email_id: str):
    """
    Vérifie si un devis SAP a déjà été créé pour cet email.
    Permet d'éviter les doublons côté frontend.
    """
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, client_code, total_ht, sap_doc_entry, sap_doc_num, status, created_at
            FROM quote_generation_log
            WHERE email_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (email_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"found": False}

        return {
            "found": True,
            "id": row["id"],
            "client_code": row["client_code"],
            "total_ht": row["total_ht"],
            "sap_doc_entry": row["sap_doc_entry"],
            "sap_doc_num": row["sap_doc_num"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
    except Exception as exc:
        logger.warning("get_quotation_by_email error: %s", exc)
        return {"found": False}


@router.get("/quotation/status")
async def get_quotation_service_status():
    """
    Vérifie l'état du service de création de devis SAP.
    Utile pour les health checks et le debugging.
    """
    service = get_sap_quotation_service()
    is_configured = bool(service.base_url and service.username and service.company_db)
    has_session = bool(service.session_id)

    return {
        "configured": is_configured,
        "has_active_session": has_session,
        "company_db": service.company_db,
        "base_url": service.base_url,
        "session_expires": service.session_timeout.isoformat() if service.session_timeout else None,
    }
