"""
API Routes - Création de devis SAP B1 depuis NOVA.

Endpoint principal :
    POST /api/sap/quotation  →  Crée un devis dans SAP Business One

Ce endpoint est appelé depuis :
  - Le frontend mail-to-biz (bouton "Envoyer dans SAP")
  - Le pipeline webhook automatique (traitement en background)
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.sap_quotation_service import (
    QuotationPayload,
    QuotationResult,
    get_sap_quotation_service,
)

logger = logging.getLogger(__name__)

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
    # Payload SAP envoyé (utile pour debug, peut être supprimé en prod)
    sap_payload: Optional[dict] = None


# ============================================================
# ENDPOINTS
# ============================================================


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

    return QuotationResponse(
        success=result.success,
        doc_entry=result.doc_entry,
        doc_num=result.doc_num,
        doc_total=result.doc_total,
        doc_date=result.doc_date,
        card_code=result.card_code,
        card_name=result.card_name,
        message=result.message,
        sap_payload=result.sap_payload,
    )


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
