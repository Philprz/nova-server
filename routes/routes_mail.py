"""
Routes API Mail-to-Biz RONDOT - Persistance SAP stricte.

Endpoints:
1. POST /api/mail/incoming - Traitement initial email (IDEMPOTENT)
2. GET /api/quote_draft/{id} - Lecture seule (ZERO requête SAP)
3. POST /api/quote_draft/{id}/line/{line_id}/retry - Retry ligne isolée

Garanties:
- Idempotence via mail_id UNIQUE
- AUCUNE requête SAP aux GET
- Logs complets dans mail_processing_log
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== Modèles Pydantic =====

class MailIncomingRequest(BaseModel):
    """
    Body pour POST /api/mail/incoming

    mail_id: ID email Microsoft (unique, idempotence)
    email_payload: Données complètes email
    """
    mail_id: str
    email_payload: Dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "mail_id": "AAMkAGE2NjY4ZGYyLTk1MjQtNGU1Yi1hODQwLTJlZjg4OGY3YzRmYgBGAAAAAADv6jCjC8xlQ6yxSw4yBqvnBwAgPpLrqOV7SKabqIMvqW3NAAAAAAEMAAAgPpLrqOV7SKabqIMvqW3NAAABQjSoAAA=",
                "email_payload": {
                    "subject": "Demande devis urgent",
                    "body": "Bonjour, merci de nous faire un devis pour...",
                    "from_address": "contact@marmaracam.com",
                    "from_name": "Marmara Cam",
                    "pdf_contents": []
                }
            }
        }


class RetryLineRequest(BaseModel):
    """
    Body pour POST /api/quote_draft/{id}/line/{line_id}/retry

    manual_code: Code RONDOT saisi manuellement (optionnel)
    """
    manual_code: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "manual_code": "TRI-037-NEW"
            }
        }


# ===== Endpoints =====

@router.post("/mail/incoming")
async def mail_incoming(request: MailIncomingRequest):
    """
    Traitement initial email (IDEMPOTENT).

    Workflow:
    1. Check si mail_id existe déjà (idempotence)
    2. Si OUI → Return 200 (already_processed)
    3. Si NON → Process complet via mail_processor
    4. Return 201 (created)

    Garantie idempotence:
    UNIQUE constraint sur mail_id - double webhook safe.

    Response 200 (déjà traité):
    {
        "status": "already_processed",
        "quote_id": "550e8400-...",
        "message": "Email déjà traité"
    }

    Response 201 (nouveau):
    {
        "status": "created",
        "quote_id": "550e8400-...",
        "client_status": "FOUND",
        "lines_count": 3
    }
    """
    from services.quote_repository import get_quote_repository
    from services.mail_processor import get_mail_processor

    mail_id = request.mail_id
    email_payload = request.email_payload

    logger.info(f"📥 Incoming mail: {mail_id[:20]}...")

    # 1. Check idempotence
    quote_repo = get_quote_repository()

    if quote_repo.check_mail_id_exists(mail_id):
        # Email déjà traité
        existing_quote = quote_repo.get_quote_by_mail_id(mail_id)

        logger.info(f"✅ Email {mail_id[:20]}... déjà traité (quote {existing_quote.id})")

        return JSONResponse(
            status_code=200,
            content={
                "status": "already_processed",
                "quote_id": existing_quote.id,
                "message": "Email déjà traité"
            }
        )

    # 2. Nouveau traitement
    mail_processor = get_mail_processor()

    try:
        quote_draft = await mail_processor.process_incoming_email(
            mail_id=mail_id,
            email_payload=email_payload
        )

        logger.info(
            f"✅ Email {mail_id[:20]}... traité → quote {quote_draft.id} "
            f"(client: {quote_draft.client_status}, lignes: {len(quote_draft.lines)})"
        )

        return JSONResponse(
            status_code=201,
            content={
                "status": "created",
                "quote_id": quote_draft.id,
                "client_status": quote_draft.client_status,
                "lines_count": len(quote_draft.lines)
            }
        )

    except Exception as e:
        logger.error(f"❌ Error processing email {mail_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing email: {str(e)}"
        )


@router.get("/quote_draft/{quote_id}")
async def get_quote_draft(quote_id: str):
    """
    Récupère un quote_draft (LECTURE SEULE - AUCUNE requête SAP).

    Garantie ZERO requête SAP:
    - Lecture directe SQLite uniquement (~50ms)
    - Pas de cache mémoire
    - Données SAP figées lors de traitement initial

    Response 200:
    {
        "id": "550e8400-...",
        "mail_id": "AAMk...abc123",
        "client_code": "C00042",
        "client_status": "FOUND",
        "status": "ANALYZED",
        "lines": [
            {
                "line_id": "uuid-1",
                "supplier_code": "HST-117-03",
                "description": "SIZE 3 PUSHER BLADE",
                "quantity": 50,
                "sap_item_code": "C315-6305RS",
                "sap_status": "FOUND",
                "sap_price": 125.50,
                "search_metadata": {
                    "search_type": "EXACT",
                    "match_score": 100
                }
            }
        ],
        "created_at": "2026-02-13T10:30:00Z",
        "updated_at": "2026-02-13T10:30:05Z"
    }

    Response 404:
    {
        "detail": "Quote draft not found"
    }
    """
    from services.quote_repository import get_quote_repository

    quote_repo = get_quote_repository()

    quote_draft = quote_repo.get_quote_draft(quote_id)

    if not quote_draft:
        raise HTTPException(
            status_code=404,
            detail="Quote draft not found"
        )

    logger.info(f"📖 Quote {quote_id} retrieved (lignes: {len(quote_draft.lines)})")

    # Retourner dictionnaire pour sérialisation JSON
    return quote_draft.dict()


@router.post("/quote_draft/{quote_id}/line/{line_id}/retry")
async def retry_line_search(
    quote_id: str,
    line_id: str,
    body: RetryLineRequest
):
    """
    Relance SAP pour ligne uniquement.

    Workflow:
    1. Récupérer quote_draft
    2. Identifier ligne à relancer
    3. Si manual_code fourni → Chercher SAP avec code exact
    4. Sinon → Relancer fuzzy search
    5. Calculer prix si trouvé
    6. Update ligne dans DB (UNIQUEMENT celle-ci)
    7. Log RETRY_LINE_SEARCH

    Cas d'usage:
    - Utilisateur clique "Relancer" dans UI
    - Utilisateur saisit code RONDOT manuellement

    Body:
    {
        "manual_code": "NEW-CODE-123"  // Optionnel
    }

    Response 200:
    {
        "success": true,
        "sap_item_code": "NEW-CODE-123",
        "sap_status": "FOUND",
        "sap_price": 150.00,
        "updated_at": "2026-02-13T11:00:00Z"
    }

    Response 404:
    {
        "detail": "Quote or line not found"
    }
    """
    from services.retry_service import get_retry_service

    retry_service = get_retry_service()

    logger.info(
        f"🔄 Retry line {line_id[:8]}... in quote {quote_id} "
        f"(manual_code={body.manual_code or 'auto'})"
    )

    try:
        result = await retry_service.retry_line_search(
            quote_id=quote_id,
            line_id=line_id,
            manual_code=body.manual_code
        )

        logger.info(
            f"✅ Line {line_id[:8]}... retry complete: "
            f"sap_status={result.sap_status}, price={result.sap_price}"
        )

        return result.dict()

    except ValueError as e:
        # Quote ou ligne non trouvée
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"❌ Error retrying line {line_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrying line: {str(e)}"
        )


@router.get("/quote_draft/{quote_id}/logs")
async def get_quote_logs(quote_id: str):
    """
    Récupère les logs de traitement d'un quote_draft.

    Utile pour debug UI - afficher timeline complète.

    Response 200:
    [
        {
            "id": "uuid",
            "step": "WEBHOOK_RECEIVED",
            "status": "SUCCESS",
            "details": null,
            "timestamp": "2026-02-13T10:30:00Z"
        },
        {
            "id": "uuid",
            "step": "LLM_ANALYSIS_COMPLETE",
            "status": "SUCCESS",
            "details": "is_quote_request=true",
            "timestamp": "2026-02-13T10:30:03Z"
        },
        ...
    ]

    Response 404:
    {
        "detail": "Quote draft not found"
    }
    """
    from services.quote_repository import get_quote_repository
    from services.mail_processing_log_service import get_mail_processing_log_service

    quote_repo = get_quote_repository()
    log_service = get_mail_processing_log_service()

    # Vérifier que quote existe
    quote_draft = quote_repo.get_quote_draft(quote_id)
    if not quote_draft:
        raise HTTPException(
            status_code=404,
            detail="Quote draft not found"
        )

    # Récupérer logs via mail_id
    logs = log_service.get_logs_for_mail(quote_draft.mail_id)

    logger.info(f"📝 Retrieved {len(logs)} logs for quote {quote_id}")

    return logs
