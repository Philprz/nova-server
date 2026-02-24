# routes/routes_graph.py
"""
Routes API pour Microsoft Graph (connexion Office 365 / emails)
"""

import os
import logging
import base64
import httpx
import asyncio
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv

from services.graph_service import get_graph_service, GraphEmail, GraphAttachment, GraphEmailsResponse, GraphAPIError
from services.email_analyzer import get_email_analyzer, extract_pdf_text, EmailAnalysisResult, ExtractedQuoteData, ExtractedProduct
from services.email_matcher import get_email_matcher
from services.duplicate_detector import get_duplicate_detector, DuplicateType, QuoteStatus

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache simple pour les résultats d'analyse (en production, utiliser Redis)
_analysis_cache: dict = {}
_backend_start_time = datetime.now()  # Pour invalider le cache au redémarrage


class ConnectionTestDetails(BaseModel):
    tenantId: bool = False
    clientId: bool = False
    clientSecret: bool = False
    mailboxAddress: bool = False
    tokenAcquired: bool = False
    mailboxAccessible: bool = False


class MailboxInfo(BaseModel):
    displayName: str
    mail: str


class ConnectionTestResult(BaseModel):
    success: bool
    step: str
    details: ConnectionTestDetails
    error: Optional[str] = None
    mailboxInfo: Optional[MailboxInfo] = None


class GraphCredentials(BaseModel):
    tenantId: Optional[str] = None
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    mailboxAddress: Optional[str] = None


@router.get("/test-connection", response_model=ConnectionTestResult)
async def test_graph_connection():
    """
    Teste la connexion Microsoft Graph avec les credentials du .env
    """
    tenant_id = os.getenv("MS_TENANT_ID")
    client_id = os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("MS_CLIENT_SECRET")
    mailbox_address = os.getenv("MS_MAILBOX_ADDRESS")

    result = ConnectionTestResult(
        success=False,
        step="checking_credentials",
        details=ConnectionTestDetails(
            tenantId=bool(tenant_id),
            clientId=bool(client_id),
            clientSecret=bool(client_secret),
            mailboxAddress=bool(mailbox_address),
        )
    )

    # Step 1: Check all credentials are present
    if not all([tenant_id, client_id, client_secret, mailbox_address]):
        missing = []
        if not tenant_id:
            missing.append("MS_TENANT_ID")
        if not client_id:
            missing.append("MS_CLIENT_ID")
        if not client_secret:
            missing.append("MS_CLIENT_SECRET")
        if not mailbox_address:
            missing.append("MS_MAILBOX_ADDRESS")
        result.error = f"Missing credentials: {', '.join(missing)}"
        return result

    # Step 2: Acquire access token
    result.step = "acquiring_token"
    logger.info("Testing token acquisition...")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "scope": "https://graph.microsoft.com/.default",
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if token_response.status_code != 200:
                error_data = token_response.json()
                error_message = error_data.get("error_description", f"Token acquisition failed ({token_response.status_code})")
                result.error = error_message
                logger.error(f"Token error: {error_message}")
                return result

            token_json = token_response.json()
            access_token = token_json.get("access_token")
            result.details.tokenAcquired = True
            logger.info("Token acquired successfully")

            # Step 3: Test mailbox access
            result.step = "testing_mailbox"
            logger.info(f"Testing mailbox access for: {mailbox_address}")

            user_url = f"https://graph.microsoft.com/v1.0/users/{mailbox_address}"
            user_response = await client.get(
                user_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )

            if user_response.status_code != 200:
                error_data = user_response.json()
                error_message = error_data.get("error", {}).get("message", f"Mailbox access failed ({user_response.status_code})")
                result.error = error_message
                logger.error(f"Mailbox access error: {error_message}")
                return result

            user_data = user_response.json()
            result.details.mailboxAccessible = True
            result.mailboxInfo = MailboxInfo(
                displayName=user_data.get("displayName", "Unknown"),
                mail=user_data.get("mail", mailbox_address)
            )

            # All tests passed
            result.success = True
            result.step = "complete"
            logger.info(f"Connection test successful: {result.mailboxInfo}")

            return result

    except httpx.RequestError as e:
        result.error = f"Network error: {str(e)}"
        logger.error(f"Connection test error: {e}")
        return result
    except Exception as e:
        result.error = f"Unexpected error: {str(e)}"
        logger.error(f"Connection test error: {e}")
        return result


@router.post("/update-credentials")
async def update_credentials(credentials: GraphCredentials):
    """
    Met a jour les credentials Microsoft Graph dans le .env
    Note: Cette route met a jour le fichier .env mais necessite un redemarrage pour prendre effet
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        updates = {}
        if credentials.tenantId:
            updates["MS_TENANT_ID"] = credentials.tenantId
        if credentials.clientId:
            updates["MS_CLIENT_ID"] = credentials.clientId
        if credentials.clientSecret:
            updates["MS_CLIENT_SECRET"] = credentials.clientSecret
        if credentials.mailboxAddress:
            updates["MS_MAILBOX_ADDRESS"] = credentials.mailboxAddress

        new_lines = []
        updated_keys = set()

        for line in lines:
            key = line.split("=")[0].strip() if "=" in line else None
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)

        # Add any new keys that weren't in the file
        for key, value in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Reload environment variables
        load_dotenv(override=True)

        return {"success": True, "message": "Credentials updated. Restart may be required."}

    except Exception as e:
        logger.error(f"Failed to update credentials: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/credentials-status")
async def get_credentials_status():
    """
    Retourne le statut des credentials (configures ou non, sans les valeurs)
    """
    return {
        "tenantId": bool(os.getenv("MS_TENANT_ID")),
        "clientId": bool(os.getenv("MS_CLIENT_ID")),
        "clientSecret": bool(os.getenv("MS_CLIENT_SECRET")),
        "mailboxAddress": bool(os.getenv("MS_MAILBOX_ADDRESS")),
        "mailboxAddressValue": os.getenv("MS_MAILBOX_ADDRESS", "")
    }


# ===========================================
# NOUVEAUX ENDPOINTS POUR LES EMAILS
# ===========================================

@router.get("/emails", response_model=GraphEmailsResponse)
async def get_emails(
    top: int = Query(default=50, le=50, description="Nombre d'emails à récupérer"),
    skip: int = Query(default=0, ge=0, description="Nombre d'emails à sauter"),
    unread_only: bool = Query(default=False, description="Filtrer les non-lus uniquement")
):
    """
    Récupère les emails de la boîte de réception Microsoft 365.
    """
    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        result = await graph_service.get_emails(
            top=top,
            skip=skip,
            unread_only=unread_only
        )
        # Enrichir chaque email avec is_quote_by_subject (sujet contient "chiffrage", "devis", etc.)
        analyzer = get_email_analyzer()
        enriched_emails = []
        for email in result.emails:
            quick = analyzer.quick_classify(email.subject, email.body_preview or "")
            enriched_emails.append(
                email.model_copy(update={"is_quote_by_subject": quick["likely_quote"]})
            )
        return GraphEmailsResponse(
            emails=enriched_emails,
            total_count=result.total_count,
            next_link=result.next_link,
        )

    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ROUTES STATIQUES (doivent être déclarées AVANT /emails/{message_id}
# car FastAPI matche dans l'ordre de déclaration)
# ============================================================

@router.get("/emails/debug-id")
async def debug_email_id(id: str = Query(None)):
    """Endpoint de debug temporaire pour vérifier la valeur reçue."""
    return {"received_id": id, "length": len(id) if id else 0, "last5": id[-5:] if id else None}


@router.get("/emails/body")
async def get_email_body(id: str = Query(..., description="Microsoft Graph message ID")):
    """
    Retourne le corps HTML de l'email.
    Utilise un query param ?id=... pour éviter les problèmes de routage avec les IDs
    Graph qui contiennent des caractères spéciaux (/, =, +).
    """
    from fastapi.responses import HTMLResponse, PlainTextResponse

    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    logger.info(
        "EMAIL_BODY_REQUEST message_id_len=%d mailbox=%s",
        len(id), graph_service.mailbox_address
    )

    try:
        email = await graph_service.get_email(id, include_attachments=False)

        logger.info(
            "EMAIL_BODY_OK subject=%r body_type=%s body_len=%d",
            email.subject,
            email.body_content_type,
            len(email.body_content or "")
        )

        if email.body_content_type and email.body_content_type.lower() == "html":
            return HTMLResponse(content=email.body_content or "", status_code=200)
        else:
            return PlainTextResponse(content=email.body_content or email.body_preview or "", status_code=200)

    except GraphAPIError as e:
        logger.error("EMAIL_BODY_GRAPH_ERROR status=%d detail=%s", e.status_code, e.detail)
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.exception("EMAIL_BODY_UNEXPECTED_ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/stored-attachments")
async def list_stored_attachments(email_id: str = Query(..., description="Microsoft Graph message ID")):
    """
    Liste les pièces jointes stockées localement pour un email.
    Utilise ?email_id=... pour éviter les problèmes de routage avec les IDs spéciaux.
    """
    logger.info("LIST_STORED_ATTACHMENTS email_id_len=%d", len(email_id))
    try:
        from services.attachment_storage_service import get_attachment_storage
        storage = get_attachment_storage()
        attachments = storage.get_stored_attachments(email_id)
        logger.info("LIST_STORED_ATTACHMENTS_OK count=%d", len(attachments))
        return {
            "email_id": email_id,
            "count": len(attachments),
            "attachments": [a.to_dict() for a in attachments],
        }
    except Exception as e:
        logger.exception("LIST_STORED_ATTACHMENTS_ERROR")
        raise HTTPException(status_code=500, detail=f"Erreur lecture stockage: {e}")


@router.get("/emails/corrections")
async def get_corrections(email_id: str = Query(..., description="Microsoft Graph message ID")):
    """Récupère les corrections manuelles appliquées à un devis."""
    from services.quote_corrections_db import get_quote_corrections_db
    db = get_quote_corrections_db()
    corrections = db.get_corrections(email_id)
    return {
        "email_id": email_id,
        "count": len(corrections),
        "corrections": [c.to_dict() for c in corrections],
    }


# ============================================================

@router.get("/emails/{message_id}")  # response_model retiré temporairement – évite la validation Pydantic post-retour
async def get_email(message_id: str):
    """
    Récupère un email complet avec son body et ses pièces jointes.
    """
    # ── STEP 1 : entrée endpoint ─────────────────────────────────────────
    logger.info("STEP_1 GET_EMAIL_ENTER message_id_len=%d", len(message_id))

    graph_service = get_graph_service()

    # ── STEP 2 : vérification dépendances ───────────────────────────────
    logger.info(
        "STEP_2 GET_EMAIL_DEPS token_type=application mailbox_present=%s message_id_present=%s",
        bool(graph_service.mailbox_address), bool(message_id)
    )

    if not graph_service.is_configured():
        logger.error("STEP_2_FAIL GET_EMAIL credentials not configured")
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        # ── STEP 3 : avant appel Graph ───────────────────────────────────
        logger.info(
            "STEP_3 GET_EMAIL_BEFORE_GRAPH mailbox=%s",
            graph_service.mailbox_address
        )

        email = await graph_service.get_email(message_id, include_attachments=True)

        # ── STEP 4 : après appel Graph ───────────────────────────────────
        logger.info(
            "STEP_4 GET_EMAIL_AFTER_GRAPH subject=%r body_type=%s body_len=%d attachments=%d",
            email.subject,
            email.body_content_type,
            len(email.body_content or ""),
            len(email.attachments)
        )

        # ── STEP 5 : avant sérialisation JSON ───────────────────────────
        logger.info("STEP_5 GET_EMAIL_BEFORE_SERIALIZE")
        result = email.model_dump()

        # ── STEP 6 : avant retour ────────────────────────────────────────
        logger.info("STEP_6 GET_EMAIL_BEFORE_RETURN result_keys=%s", list(result.keys()))
        return result

    except GraphAPIError as e:
        logger.error(
            "GET_EMAIL_GRAPH_ERROR status=%d detail=%s",
            e.status_code, e.detail
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        # STEP_ERR : stacktrace complète pour localiser la ligne exacte
        logger.exception("GET_EMAIL_FULL_STACKTRACE message_id_len=%d error=%s", len(message_id), str(e))
        raise HTTPException(status_code=500, detail=f"[GET_EMAIL] {type(e).__name__}: {e}")


@router.get("/emails/{message_id}/attachments")  # response_model retiré temporairement
async def get_email_attachments(message_id: str):
    """
    Récupère la liste des pièces jointes d'un email.
    """
    # ── STEP 1 ─────────────────────────────────────────────────────────
    logger.info("STEP_1 GET_ATTACHMENTS_ENTER message_id_len=%d", len(message_id))

    graph_service = get_graph_service()

    # ── STEP 2 ─────────────────────────────────────────────────────────
    logger.info(
        "STEP_2 GET_ATTACHMENTS_DEPS mailbox_present=%s message_id_present=%s",
        bool(graph_service.mailbox_address), bool(message_id)
    )

    if not graph_service.is_configured():
        logger.error("STEP_2_FAIL GET_ATTACHMENTS credentials not configured")
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        # ── STEP 3 : avant appel Graph ───────────────────────────────────
        logger.info("STEP_3 GET_ATTACHMENTS_BEFORE_GRAPH mailbox=%s", graph_service.mailbox_address)

        attachments = await graph_service.get_attachments(message_id)

        # ── STEP 4 : après appel Graph ───────────────────────────────────
        logger.info("STEP_4 GET_ATTACHMENTS_AFTER_GRAPH count=%d", len(attachments))

        # ── STEP 5 : sérialisation ───────────────────────────────────────
        logger.info("STEP_5 GET_ATTACHMENTS_BEFORE_SERIALIZE")
        result = [a.model_dump() for a in attachments]

        # ── STEP 6 ───────────────────────────────────────────────────────
        logger.info("STEP_6 GET_ATTACHMENTS_BEFORE_RETURN count=%d", len(result))
        return result

    except GraphAPIError as e:
        logger.error(
            "GET_ATTACHMENTS_GRAPH_ERROR status=%d detail=%s",
            e.status_code, e.detail
        )
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.exception("GET_ATTACHMENTS_FULL_STACKTRACE message_id_len=%d error=%s", len(message_id), str(e))
        raise HTTPException(status_code=500, detail=f"[GET_ATTACHMENTS] {type(e).__name__}: {e}")


class AttachmentContentResponse(BaseModel):
    content_base64: str
    content_type: str
    filename: str
    size: int


@router.get("/emails/{message_id}/attachments/{attachment_id}/content", response_model=AttachmentContentResponse)
async def get_attachment_content(message_id: str, attachment_id: str):
    """
    Récupère le contenu d'une pièce jointe en base64.
    """
    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        # Récupérer d'abord les métadonnées de la pièce jointe
        attachments = await graph_service.get_attachments(message_id)
        attachment_info = next((a for a in attachments if a.id == attachment_id), None)

        if not attachment_info:
            raise HTTPException(status_code=404, detail="Attachment not found")

        # Récupérer le contenu
        content_bytes = await graph_service.get_attachment_content(message_id, attachment_id)

        return AttachmentContentResponse(
            content_base64=base64.b64encode(content_bytes).decode('utf-8'),
            content_type=attachment_info.content_type,
            filename=attachment_info.name,
            size=len(content_bytes)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching attachment content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/{message_id}/attachments/{attachment_id}/stream")
async def stream_attachment(message_id: str, attachment_id: str):
    """
    Stream une pièce jointe directement (sans base64).
    Utilisable comme src dans une iframe ou un lien de téléchargement.
    """
    from fastapi.responses import StreamingResponse
    import io

    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        # Récupérer les métadonnées pour le nom et le content-type
        attachments = await graph_service.get_attachments(message_id)
        attachment_info = next((a for a in attachments if a.id == attachment_id), None)

        content_type = attachment_info.content_type if attachment_info else "application/octet-stream"
        filename = attachment_info.name if attachment_info else "attachment"

        # Récupérer le contenu binaire
        content_bytes = await graph_service.get_attachment_content(message_id, attachment_id)

        # Encoder le nom de fichier pour l'en-tête (RFC 5987)
        safe_name = filename.encode('ascii', errors='replace').decode('ascii')

        return StreamingResponse(
            io.BytesIO(content_bytes),
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{safe_name}"',
                "Content-Length": str(len(content_bytes)),
                "Cache-Control": "no-store"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming attachment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/{message_id}/analyze", response_model=EmailAnalysisResult)
async def analyze_email(message_id: str, force: bool = False):
    """
    Analyse un email avec l'IA pour déterminer s'il s'agit d'une demande de devis.
    Le résultat est mis en cache ET persisté en base de données.

    Args:
        message_id: ID de l'email
        force: Si True, force la ré-analyse même si le résultat est en cache (défaut: False pour utiliser le cache)
    """
    global _analysis_cache, _backend_start_time

    # ✨ NOUVEAU : Vérifier la base de données persistante EN PREMIER (sauf si force=True)
    if not force:
        from services.email_analysis_db import get_email_analysis_db
        analysis_db = get_email_analysis_db()

        existing_analysis = analysis_db.get_analysis(message_id)
        if existing_analysis:
            logger.info(f"📦 Analysis loaded from DB for {message_id} (NO RECOMPUTE)")

            # Mettre en cache mémoire pour accès rapide
            _analysis_cache[message_id] = {
                'data': EmailAnalysisResult(**existing_analysis),
                'timestamp': datetime.now()
            }

            return EmailAnalysisResult(**existing_analysis)

    # Vérifier le cache mémoire (sauf si force=True)
    # Invalider le cache s'il date d'avant le démarrage du backend
    if not force and message_id in _analysis_cache:
        cached_entry = _analysis_cache[message_id]
        # Vérifier si l'entrée a un timestamp et si elle est toujours valide
        if isinstance(cached_entry, dict) and 'timestamp' in cached_entry:
            cache_time = cached_entry['timestamp']
            if cache_time < _backend_start_time:
                logger.info(f"Cache invalidé (plus ancien que le démarrage) pour {message_id}")
                del _analysis_cache[message_id]
            else:
                logger.info(f"Returning cached analysis for {message_id}")
                return cached_entry['data']
        else:
            # Ancien format de cache sans timestamp - invalider
            logger.info(f"Cache invalide (format ancien) pour {message_id}")
            del _analysis_cache[message_id]

    if force:
        logger.info(f"Forcing new analysis for {message_id}")

    t_total = time.time()
    graph_service = get_graph_service()
    email_analyzer = get_email_analyzer()
    matcher = get_email_matcher()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        # Phase 1: Récupérer l'email + pré-charger le cache matcher en parallèle
        t_phase = time.time()
        email, _ = await asyncio.gather(
            graph_service.get_email(message_id, include_attachments=True),
            matcher.ensure_cache()
        )
        logger.info(f"⚡ Phase 1 - Email fetch + cache warm: {(time.time()-t_phase)*1000:.0f}ms")

        # Phase 2: Extraire le contenu des PDFs si présents
        t_phase = time.time()
        pdf_contents = []
        MAX_PDF_SIZE = 5 * 1024 * 1024  # 5 MB max par PDF
        MAX_PDF_PROCESSING_TIME = 30  # 30 secondes max par PDF

        for attachment in email.attachments:
            if attachment.content_type == "application/pdf":
                # Vérifier la taille avant de télécharger
                if attachment.size > MAX_PDF_SIZE:
                    logger.warning(f"PDF {attachment.name} trop gros ({attachment.size / 1024 / 1024:.1f} MB), skip")
                    continue

                try:
                    # Télécharger avec timeout
                    content_bytes = await asyncio.wait_for(
                        graph_service.get_attachment_content(message_id, attachment.id),
                        timeout=MAX_PDF_PROCESSING_TIME
                    )

                    # Parser avec timeout
                    text = await asyncio.wait_for(
                        extract_pdf_text(content_bytes),
                        timeout=MAX_PDF_PROCESSING_TIME
                    )

                    if text:
                        pdf_contents.append(text)
                        logger.info(f"PDF {attachment.name} extrait avec succès ({len(text)} chars)")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout lors du traitement du PDF {attachment.name}, skip")
                except Exception as e:
                    logger.warning(f"Could not extract PDF {attachment.name}: {e}")

        # Préparer le body text
        if email.body_content and len(email.body_content.strip()) > 0:
            body_text = email.body_content
            logger.info(f"Using full body_content ({len(body_text)} chars)")
        else:
            body_text = email.body_preview
            logger.warning(f"body_content empty/missing, using body_preview ({len(body_text)} chars) - may be truncated!")

        logger.info(f"⚡ Phase 2 - PDF extraction: {(time.time()-t_phase)*1000:.0f}ms")

        # Phase 3: LLM analysis + SAP matching EN PARALLÈLE
        t_phase = time.time()

        # Préparer le texte nettoyé pour le matching (rapide, sync)
        clean_text = email_analyzer._clean_html(body_text)
        if pdf_contents:
            clean_text += " " + " ".join(pdf_contents)

        # Lancer LLM et matching en parallèle (les 2 opérations sont indépendantes)
        llm_task = email_analyzer.analyze_email(
            subject=email.subject,
            body=body_text,
            sender_email=email.from_address,
            sender_name=email.from_name,
            pdf_contents=pdf_contents
        )
        match_task = matcher.match_email(
            body=clean_text,
            sender_email=email.from_address,
            subject=email.subject
        )

        parallel_results = await asyncio.gather(llm_task, match_task, return_exceptions=True)

        # Récupérer le résultat LLM (obligatoire)
        result = parallel_results[0]
        if isinstance(result, Exception):
            raise result

        # Récupérer le résultat matching (optionnel, non-bloquant)
        match_result = parallel_results[1] if not isinstance(parallel_results[1], Exception) else None
        if isinstance(parallel_results[1], Exception):
            logger.warning(f"SAP matching failed (non-blocking): {parallel_results[1]}")

        logger.info(f"⚡ Phase 3 - LLM + SAP matching (parallel): {(time.time()-t_phase)*1000:.0f}ms")

        # Phase 4: Enrichissement avec les résultats du matching SAP
        t_phase = time.time()

        try:
            if match_result is None:
                raise Exception("Matching skipped due to earlier error")

            # Enrichir extracted_data avec les résultats du matching SAP
            if match_result.best_client or match_result.products:
                if result.extracted_data is None:
                    result.extracted_data = ExtractedQuoteData()

                # Client matché : priorité sur l'extraction LLM/regex
                if match_result.best_client:
                    result.extracted_data.client_name = match_result.best_client.card_name
                    result.extracted_data.client_card_code = match_result.best_client.card_code
                    if match_result.best_client.email_address:
                        result.extracted_data.client_email = match_result.best_client.email_address
                    logger.info(f"SAP match client: {match_result.best_client.card_name} "
                                f"({match_result.best_client.card_code}) score={match_result.best_client.score}")

                # Produits matchés : remplacent les produits LLM si trouvés
                if match_result.products:
                    result.extracted_data.products = [
                        ExtractedProduct(
                            description=f"{p.item_name}" if p.item_name else f"Article {p.item_code}",
                            quantity=p.quantity,
                            unit="pcs",
                            reference=p.item_code
                        )
                        for p in match_result.products
                    ]
                    logger.info(f"SAP match produits: {len(match_result.products)} article(s)")

                # S'assurer que c'est marqué comme demande de devis si on a trouvé des produits
                if match_result.products and not result.is_quote_request:
                    result.is_quote_request = True
                    result.classification = "QUOTE_REQUEST"

            # === GESTION MATCHES MULTIPLES & AUTO-VALIDATION ===

            # Stocker tous les matches (pour choix utilisateur si nécessaire)
            result.client_matches = [c.dict() for c in match_result.clients]  # Convertir en dict pour JSON
            result.product_matches = [p.dict() for p in match_result.products]

            # --- AUTO-VALIDATION CLIENT ---
            if match_result.clients:
                # Si 1 seul client ET score ≥ 95 → AUTO-VALIDÉ
                if len(match_result.clients) == 1 and match_result.clients[0].score >= 95:
                    result.client_auto_validated = True
                    logger.info(f"✅ Client AUTO-VALIDÉ: {match_result.clients[0].card_name} (score={match_result.clients[0].score})")

                # Si plusieurs clients OU score < 95 → CHOIX REQUIS
                elif len(match_result.clients) > 1:
                    result.requires_user_choice = True
                    result.user_choice_reason = f"{len(match_result.clients)} clients possibles - Choix requis"
                    logger.info(f"⚠️ CHOIX UTILISATEUR requis: {len(match_result.clients)} clients matchés")

                elif match_result.clients[0].score < 95:
                    result.requires_user_choice = True
                    result.user_choice_reason = f"Client score < 95 ({match_result.clients[0].score}) - Confirmation requise"
                    logger.info(f"⚠️ CONFIRMATION requise: Client score={match_result.clients[0].score} < 95")

            # --- AUTO-VALIDATION PRODUITS ---
            if match_result.products:
                # Si TOUS les produits ont score = 100 (match exact code) → AUTO-VALIDÉ
                all_exact_match = all(p.score == 100 for p in match_result.products)

                if all_exact_match:
                    result.products_auto_validated = True
                    logger.info(f"✅ Produits AUTO-VALIDÉS: {len(match_result.products)} produit(s) match exact")

                # Si au moins 1 produit score < 100 → CHOIX REQUIS
                else:
                    result.requires_user_choice = True
                    ambiguous_products = [p for p in match_result.products if p.score < 100]
                    result.user_choice_reason = (
                        result.user_choice_reason or ""
                    ) + f" | {len(ambiguous_products)} produit(s) ambigus (score < 100)"
                    logger.info(f"⚠️ CHOIX UTILISATEUR requis: {len(ambiguous_products)} produits avec score < 100")

            # Si aucun client trouvé → CRÉATION REQUISE
            if not match_result.clients and result.extracted_data and result.extracted_data.client_name:
                result.requires_user_choice = True
                result.user_choice_reason = "Client non trouvé - Création nécessaire"
                logger.info("⚠️ CRÉATION CLIENT requise: aucun match SAP")

            # Si aucun produit trouvé → CRÉATION REQUISE
            if not match_result.products and result.extracted_data and result.extracted_data.products:
                result.requires_user_choice = True
                result.user_choice_reason = (
                    result.user_choice_reason or ""
                ) + " | Produit(s) non trouvé(s) - Vérification fichiers fournisseurs requise"
                logger.info("⚠️ VÉRIFICATION PRODUITS requise: aucun match SAP")

        except Exception as e:
            logger.warning(f"SAP matching/enrichment failed (non-blocking): {e}")

        logger.info(f"⚡ Phase 4 - Enrichissement: {(time.time()-t_phase)*1000:.0f}ms")

        # === NOUVELLE PHASE 5 : CALCUL AUTOMATIQUE DES PRIX ===
        t_phase = time.time()

        try:
            # Vérifier si pricing engine est activé
            pricing_enabled = os.getenv("PRICING_ENGINE_ENABLED", "false").lower() == "true"

            if pricing_enabled and match_result and match_result.products:
                logger.info(f"💰 Calcul pricing pour {len(match_result.products)} produits...")

                from services.pricing_engine import get_pricing_engine
                from services.pricing_models import PricingContext

                pricing_engine = get_pricing_engine()

                # Récupérer CardCode client (nécessaire pour pricing)
                card_code = "UNKNOWN"
                if match_result.best_client:
                    card_code = match_result.best_client.card_code
                elif result.extracted_data and result.extracted_data.client_card_code:
                    card_code = result.extracted_data.client_card_code

                # Préparer contextes pricing pour tous les produits
                pricing_contexts = []
                for product in match_result.products:
                    # Skip si produit non trouvé dans SAP
                    if product.not_found_in_sap:
                        continue

                    context = PricingContext(
                        item_code=product.item_code,
                        card_code=card_code,
                        quantity=product.quantity,
                        supplier_price=None,  # Sera récupéré automatiquement
                        apply_margin=float(os.getenv("PRICING_DEFAULT_MARGIN", "45.0")),
                        force_recalculate=False
                    )
                    pricing_contexts.append((product, context))

                # Calcul parallèle des prix (gain performance 80%)
                pricing_tasks = [
                    pricing_engine.calculate_price(ctx)
                    for _, ctx in pricing_contexts
                ]

                pricing_results = await asyncio.gather(*pricing_tasks, return_exceptions=True)

                # Enrichir produits avec résultats pricing
                enriched_products = []
                pricing_success_count = 0

                for i, (product, context) in enumerate(pricing_contexts):
                    pricing_result = pricing_results[i]

                    # Gestion erreurs gracieuse (non-bloquant)
                    if isinstance(pricing_result, Exception):
                        logger.error(f"Pricing error for {product.item_code}: {pricing_result}")
                        enriched_products.append(product)
                        continue

                    if pricing_result.success and pricing_result.decision:
                        decision = pricing_result.decision

                        # Créer produit enrichi avec pricing
                        enriched_dict = product.dict()
                        # Sérialiser historical_sales (objets Pydantic → dicts)
                        historical_sales_data = []
                        if decision.historical_sales:
                            for sale in decision.historical_sales:
                                try:
                                    historical_sales_data.append(sale.dict() if hasattr(sale, 'dict') else dict(sale))
                                except Exception:
                                    pass

                        is_new_product = (
                            product.item_code is None
                            and decision.supplier_price is None
                            and not decision.historical_sales
                        )
                        logger.info(
                            "Product classification — item_code=%s case=%s "
                            "found_in_sap=%s is_truly_new=%s",
                            product.item_code,
                            decision.case_type.value,
                            not product.not_found_in_sap,
                            is_new_product,
                        )

                        enriched_dict.update({
                            "unit_price": decision.calculated_price,
                            "line_total": decision.calculated_price * product.quantity,
                            "pricing_case": decision.case_type.value,
                            "pricing_justification": decision.justification,
                            "requires_validation": decision.requires_validation,
                            "validation_reason": decision.validation_reason,
                            "supplier_price": decision.supplier_price,
                            "margin_applied": decision.margin_applied,
                            "confidence_score": decision.confidence_score,
                            "alerts": decision.alerts,
                            "decision_id": decision.decision_id,
                            "historical_sales": historical_sales_data,
                            "last_sale_price": decision.last_sale_price,
                            "last_sale_date": str(decision.last_sale_date) if decision.last_sale_date else None,
                            "average_price_others": decision.average_price_others,
                        })

                        # Ajouter prix SAP moyen (AvgStdPrice) pour transparence
                        try:
                            from services.sap_cache_db import get_sap_cache_db
                            import sqlite3 as _sqlite3
                            _sap_cache = get_sap_cache_db()
                            _conn = _sqlite3.connect(_sap_cache.db_path)
                            _cur = _conn.cursor()
                            _cur.execute("SELECT Price FROM sap_items WHERE ItemCode = ?", (product.item_code,))
                            _row = _cur.fetchone()
                            _conn.close()
                            if _row and _row[0]:
                                enriched_dict["sap_avg_price"] = _row[0]
                        except Exception:
                            pass

                        from services.email_matcher import MatchedProduct
                        enriched_product = MatchedProduct(**enriched_dict)
                        enriched_products.append(enriched_product)

                        pricing_success_count += 1

                        logger.info(
                            f"  ✓ {decision.case_type.value}: {product.item_code} → "
                            f"{decision.calculated_price:.2f} EUR (marge {decision.margin_applied:.0f}%)"
                        )
                    else:
                        # Fallback: garder produit sans pricing
                        enriched_products.append(product)

                # Ajouter produits non trouvés dans SAP (sans pricing)
                for product in match_result.products:
                    if product.not_found_in_sap:
                        enriched_products.append(product)

                # Remplacer produits par versions enrichies
                result.product_matches = [p.dict() for p in enriched_products]

                logger.info(
                    f"⚡ Phase 5 - Pricing: {(time.time()-t_phase)*1000:.0f}ms "
                    f"({pricing_success_count}/{len(match_result.products)} succès)"
                )

        except Exception as e:
            # Fallback gracieux: continuer sans pricing
            logger.warning(f"Phase 5 pricing failed (non-blocking): {e}")

        # === DÉTECTION DES DOUBLONS ===
        try:
            detector = get_duplicate_detector()

            # Extraire les codes produits identifiés
            product_codes = []
            if result.extracted_data and result.extracted_data.products:
                product_codes = [p.reference for p in result.extracted_data.products if p.reference]

            # Vérifier les doublons
            duplicate_check = detector.check_duplicate(
                email_id=message_id,
                sender_email=email.from_address,
                subject=email.subject,
                client_card_code=result.extracted_data.client_card_code if result.extracted_data else None,
                product_codes=product_codes if product_codes else None
            )

            # Enrichir le résultat avec les infos de doublon
            result.is_duplicate = duplicate_check.is_duplicate
            result.duplicate_type = duplicate_check.duplicate_type.value
            result.duplicate_confidence = duplicate_check.confidence

            if duplicate_check.existing_quote:
                result.existing_quote_id = duplicate_check.existing_quote.quote_id
                result.existing_quote_status = duplicate_check.existing_quote.status

                logger.warning(
                    f"Doublon détecté ({duplicate_check.duplicate_type.value}) "
                    f"pour email {message_id} - Devis existant: {duplicate_check.existing_quote.quote_id}"
                )

            # Si pas de doublon, enregistrer cet email comme traité
            if not duplicate_check.is_duplicate and result.is_quote_request:
                detector.register_email(
                    email_id=message_id,
                    sender_email=email.from_address,
                    subject=email.subject,
                    client_card_code=result.extracted_data.client_card_code if result.extracted_data else None,
                    client_name=result.extracted_data.client_name if result.extracted_data else None,
                    product_codes=product_codes,
                    status=QuoteStatus.PENDING,
                    notes=f"Auto-enregistré lors de l'analyse"
                )

        except Exception as e:
            logger.error(f"Erreur détection doublon (non-bloquant): {e}")
            # Ne pas bloquer le traitement en cas d'erreur de détection

        logger.info(f"✅ Analyse complète en {(time.time()-t_total)*1000:.0f}ms pour {message_id}")

        # Mettre en cache (limiter à 100 entrées)
        if len(_analysis_cache) > 100:
            oldest_keys = list(_analysis_cache.keys())[:20]
            for key in oldest_keys:
                del _analysis_cache[key]

        # Stocker avec timestamp pour invalidation au redémarrage
        _analysis_cache[message_id] = {
            'timestamp': datetime.now(),
            'data': result
        }

        # ✨ NOUVEAU : Persister en base de données pour consultation ultérieure
        try:
            from services.email_analysis_db import get_email_analysis_db
            analysis_db = get_email_analysis_db()

            analysis_db.save_analysis(
                email_id=message_id,
                subject=email.subject,
                from_address=email.from_address,
                analysis_result=result.dict()
            )

            logger.info(f"💾 Analysis persisted to DB for {message_id}")
        except Exception as e:
            logger.warning(f"Could not persist analysis to DB (non-critical): {e}")

        # Stocker les pièces jointes en arrière-plan (non bloquant)
        if email.has_attachments:
            try:
                from services.attachment_storage_service import get_attachment_storage
                attachment_storage = get_attachment_storage()
                asyncio.create_task(
                    attachment_storage.download_and_store_all(message_id, message_id, graph_service)
                )
                logger.info(f"Stockage PJ lancé en arrière-plan pour {message_id}")
            except Exception as e:
                logger.warning(f"Stockage PJ non lancé (non-critique): {e}")

        return result

    except Exception as e:
        logger.error(f"Error analyzing email {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/{message_id}/analysis", response_model=Optional[EmailAnalysisResult])
async def get_email_analysis(message_id: str):
    """
    Récupère le résultat d'analyse en cache pour un email.
    Retourne null si l'email n'a pas encore été analysé.
    """
    global _analysis_cache

    # Vérifier cache mémoire
    if message_id in _analysis_cache:
        cached_entry = _analysis_cache[message_id]
        # Gérer le nouveau format avec timestamp
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            return cached_entry['data']
        # Ancien format (rétrocompatibilité)
        return cached_entry

    # Si pas en cache mémoire, vérifier la base de données persistante
    from services.email_analysis_db import get_email_analysis_db
    analysis_db = get_email_analysis_db()

    existing_analysis = analysis_db.get_analysis(message_id)
    if existing_analysis:
        logger.info(f"📦 Analysis loaded from DB for GET endpoint: {message_id}")

        # Mettre en cache mémoire pour accès rapide futur
        _analysis_cache[message_id] = {
            'data': EmailAnalysisResult(**existing_analysis),
            'timestamp': datetime.now()
        }

        return EmailAnalysisResult(**existing_analysis)

    return None


@router.delete("/emails/{message_id}/cache")
async def clear_email_cache(message_id: str):
    """
    Vide le cache d'analyse pour un email spécifique.
    La prochaine analyse (avec ?force=true) recalculera tout depuis zéro.
    """
    global _analysis_cache

    cleared_memory = message_id in _analysis_cache
    if cleared_memory:
        del _analysis_cache[message_id]

    # Vider aussi la base de données persistante
    cleared_db = False
    try:
        from services.email_analysis_db import get_email_analysis_db
        analysis_db = get_email_analysis_db()
        analysis_db.delete_analysis(message_id)
        cleared_db = True
    except Exception:
        pass

    logger.info(f"Cache vidé pour {message_id} (mémoire={cleared_memory}, DB={cleared_db})")

    return {
        "success": True,
        "message_id": message_id,
        "cleared_memory": cleared_memory,
        "cleared_db": cleared_db
    }


@router.post("/emails/{message_id}/mark-read")
async def mark_email_as_read(message_id: str):
    """
    Marque un email comme lu.
    """
    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        success = await graph_service.mark_as_read(message_id)
        return {"success": success}

    except Exception as e:
        logger.error(f"Error marking email as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ENDPOINTS PHASE B - VALIDATION CHOIX MULTIPLES
# ==========================================


class ClientChoiceRequest(BaseModel):
    """Requête de confirmation du choix client."""
    card_code: str  # Code client SAP choisi
    card_name: str
    create_new: bool = False  # True si création d'un nouveau client


class ProductChoiceRequest(BaseModel):
    """Requête de confirmation des choix produits."""
    selected_products: List[dict]  # Liste des produits choisis avec item_code, quantity
    create_new_products: List[dict] = []  # Produits à créer (si non trouvés dans SAP)


class ExcludeProductRequest(BaseModel):
    """Requête pour exclure un produit du devis."""
    reason: Optional[str] = None  # Raison de l'exclusion (optionnel)


class ManualCodeRequest(BaseModel):
    """Requête pour saisir manuellement un code article RONDOT."""
    rondot_code: str  # Code article RONDOT saisi manuellement


class RetrySearchRequest(BaseModel):
    """Requête pour relancer la recherche SAP d'un article."""
    search_query: Optional[str] = None  # Nouvelle requête de recherche (optionnel)


@router.post("/emails/{message_id}/confirm-client")
async def confirm_client_choice(message_id: str, choice: ClientChoiceRequest):
    """
    L'utilisateur confirme son choix de client parmi les matches.

    Args:
        message_id: ID de l'email
        choice: Client choisi ou demande de création

    Returns:
        Confirmation du choix avec mise à jour du cache
    """
    global _analysis_cache

    try:
        # Récupérer l'analyse en cache
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Email analysis not found in cache")

        cached_entry = _analysis_cache[message_id]
        # Gérer le nouveau format avec timestamp
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            result = cached_entry['data']
        else:
            result = cached_entry

        # Mettre à jour les données extraites avec le choix utilisateur
        if result.extracted_data is None:
            result.extracted_data = ExtractedQuoteData()

        if choice.create_new:
            # Création d'un nouveau client demandée
            result.extracted_data.client_name = choice.card_name
            result.extracted_data.client_card_code = None  # Sera créé dans SAP
            logger.info(f"Création nouveau client demandée: {choice.card_name}")

            return {
                "success": True,
                "action": "create_client",
                "client_name": choice.card_name,
                "message": f"Nouveau client '{choice.card_name}' sera créé dans SAP"
            }

        else:
            # Client existant choisi
            result.extracted_data.client_name = choice.card_name
            result.extracted_data.client_card_code = choice.card_code

            # Trouver le match complet pour récupérer l'email
            selected_match = next(
                (c for c in result.client_matches if c['card_code'] == choice.card_code),
                None
            )
            if selected_match and selected_match.get('email_address'):
                result.extracted_data.client_email = selected_match['email_address']

            # Marquer comme validé
            result.client_auto_validated = True
            result.requires_user_choice = False  # Choix effectué

            logger.info(f"Client choisi par utilisateur: {choice.card_name} ({choice.card_code})")

            return {
                "success": True,
                "action": "client_confirmed",
                "card_code": choice.card_code,
                "card_name": choice.card_name,
                "message": f"Client {choice.card_name} ({choice.card_code}) confirmé"
            }

    except Exception as e:
        logger.error(f"Error confirming client choice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/{message_id}/confirm-products")
async def confirm_products_choice(message_id: str, choice: ProductChoiceRequest):
    """
    L'utilisateur confirme son choix de produits parmi les matches.

    Args:
        message_id: ID de l'email
        choice: Produits choisis et produits à créer

    Returns:
        Confirmation des choix avec mise à jour du cache
    """
    global _analysis_cache

    try:
        # Récupérer l'analyse en cache
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Email analysis not found in cache")

        cached_entry = _analysis_cache[message_id]
        # Gérer le nouveau format avec timestamp
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            result = cached_entry['data']
        else:
            result = cached_entry

        # Mettre à jour les données extraites avec les choix utilisateur
        if result.extracted_data is None:
            result.extracted_data = ExtractedQuoteData()

        # Produits existants choisis
        confirmed_products = []
        for selected in choice.selected_products:
            confirmed_products.append(ExtractedProduct(
                description=selected.get('description', f"Article {selected['item_code']}"),
                quantity=selected.get('quantity', 1),
                reference=selected['item_code'],
                unit="pcs"
            ))

        # Produits à créer
        new_products = []
        for new_prod in choice.create_new_products:
            new_products.append(ExtractedProduct(
                description=new_prod.get('description', 'Nouveau produit'),
                quantity=new_prod.get('quantity', 1),
                reference=new_prod.get('reference', ''),
                unit="pcs"
            ))

        # Combiner les produits
        result.extracted_data.products = confirmed_products + new_products

        # Marquer comme validé
        result.products_auto_validated = True
        if not result.requires_user_choice or result.client_auto_validated:
            result.requires_user_choice = False  # Tout est validé

        logger.info(
            f"Produits confirmés par utilisateur: "
            f"{len(confirmed_products)} existants, {len(new_products)} à créer"
        )

        return {
            "success": True,
            "action": "products_confirmed",
            "confirmed_count": len(confirmed_products),
            "new_count": len(new_products),
            "message": f"{len(confirmed_products)} produit(s) confirmé(s), {len(new_products)} à créer"
        }

    except Exception as e:
        logger.error(f"Error confirming products choice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/{message_id}/validation-status")
async def get_validation_status(message_id: str):
    """
    Récupère le statut de validation de l'email (pour UI).

    Returns:
        Statut détaillé des validations requises
    """
    global _analysis_cache

    try:
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Email analysis not found in cache")

        result = _analysis_cache[message_id]

        return {
            "requires_user_choice": result.requires_user_choice,
            "client_auto_validated": result.client_auto_validated,
            "products_auto_validated": result.products_auto_validated,
            "user_choice_reason": result.user_choice_reason,
            "client_matches_count": len(result.client_matches),
            "product_matches_count": len(result.product_matches),
            "is_duplicate": result.is_duplicate,
            "duplicate_type": result.duplicate_type,
            "ready_for_quote_generation": (
                result.client_auto_validated and
                result.products_auto_validated and
                not result.requires_user_choice and
                not result.is_duplicate
            )
        }

    except Exception as e:
        logger.error(f"Error getting validation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === ENDPOINTS ACTIONS PRODUITS NON TROUVÉS ===

@router.post("/emails/{message_id}/products/{item_code}/exclude")
async def exclude_product_from_quote(
    message_id: str,
    item_code: str,
    request: ExcludeProductRequest
):
    """
    Exclut un article du devis.
    Trace l'action pour audit et apprentissage futur.
    """
    global _analysis_cache

    try:
        # 1. Récupérer analyse en cache
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Analyse non trouvée")

        cached_entry = _analysis_cache[message_id]
        # Gérer le nouveau format avec timestamp
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            result = cached_entry['data']
        else:
            result = cached_entry

        # 2. Retirer le produit de la liste
        if result.product_matches:
            original_count = len(result.product_matches)
            result.product_matches = [
                p for p in result.product_matches
                if p.get("item_code") != item_code
            ]
            removed_count = original_count - len(result.product_matches)

            if removed_count == 0:
                logger.warning(f"Produit {item_code} non trouvé dans l'analyse {message_id}")

        # 3. Tracer l'action (audit + apprentissage)
        try:
            from services.product_mapping_db import get_product_mapping_db
            mapping_db = get_product_mapping_db()
            mapping_db.log_exclusion(
                item_code=item_code,
                email_id=message_id,
                reason=request.reason or "Excluded by user"
            )
        except Exception as e:
            logger.warning(f"Could not log exclusion (non-critical): {e}")

        logger.info(f"Produit {item_code} exclu du devis {message_id}")

        return {
            "success": True,
            "item_code": item_code,
            "action": "excluded",
            "remaining_products": len(result.product_matches) if result.product_matches else 0
        }

    except Exception as e:
        logger.error(f"Exclusion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/{message_id}/products/{item_code}/manual-code")
async def set_manual_product_code(
    message_id: str,
    item_code: str,  # Code original (non trouvé)
    request: ManualCodeRequest
):
    """
    Remplace un code article non trouvé par un code RONDOT saisi manuellement.
    Enregistre le mapping pour apprentissage automatique futur.
    """
    global _analysis_cache

    try:
        # 1. Récupérer analyse en cache
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Analyse non trouvée")

        cached_entry = _analysis_cache[message_id]
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            result = cached_entry['data']
        else:
            result = cached_entry

        # 2. Vérifier que le code RONDOT existe dans SAP
        from services.sap_business_service import get_sap_business_service
        sap_service = get_sap_business_service()

        sap_items = await sap_service.search_items(request.rondot_code, limit=1)

        if not sap_items:
            raise HTTPException(
                status_code=404,
                detail=f"Code RONDOT '{request.rondot_code}' non trouvé dans SAP"
            )

        sap_item = sap_items[0]

        # 3. Mettre à jour le produit dans l'analyse
        product_updated = False
        if result.product_matches:
            for product in result.product_matches:
                if product.get("item_code") == item_code:
                    product["item_code"] = sap_item.item_code
                    product["item_name"] = sap_item.item_name
                    product["not_found_in_sap"] = False
                    product["match_reason"] = "Code RONDOT saisi manuellement"
                    product["score"] = 100
                    product_updated = True
                    break

        # 4. Enregistrer mapping pour apprentissage
        try:
            from services.product_mapping_db import get_product_mapping_db
            mapping_db = get_product_mapping_db()
            mapping_db.add_mapping(
                external_code=item_code,
                sap_code=sap_item.item_code,
                source="manual_user_input",
                confidence=1.0
            )
            logger.info(f"Mapping ajouté: {item_code} → {sap_item.item_code}")
        except Exception as e:
            logger.warning(f"Could not save mapping (non-critical): {e}")

        # 5. Recalculer pricing pour ce produit
        unit_price = None
        try:
            from services.pricing_engine import get_pricing_engine
            from services.pricing_models import PricingContext

            pricing_engine = get_pricing_engine()

            card_code = result.extracted_data.client_card_code if result.extracted_data else "UNKNOWN"
            quantity = next((p.get("quantity", 1) for p in result.product_matches if p.get("item_code") == sap_item.item_code), 1)

            pricing_result = await pricing_engine.calculate_price(
                PricingContext(
                    item_code=sap_item.item_code,
                    card_code=card_code,
                    quantity=quantity
                )
            )

            if pricing_result.success and pricing_result.decision:
                # Enrichir avec pricing
                for product in result.product_matches:
                    if product.get("item_code") == sap_item.item_code:
                        product["unit_price"] = pricing_result.decision.calculated_price
                        product["line_total"] = pricing_result.decision.line_total
                        product["pricing_case"] = pricing_result.decision.case_type.value
                        product["pricing_justification"] = pricing_result.decision.justification
                        unit_price = pricing_result.decision.calculated_price
                        break
        except Exception as e:
            logger.warning(f"Could not calculate pricing (non-critical): {e}")

        return {
            "success": True,
            "original_code": item_code,
            "rondot_code": sap_item.item_code,
            "item_name": sap_item.item_name,
            "unit_price": unit_price,
            "mapping_saved": True,
            "product_updated": product_updated
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual code error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/{message_id}/products/{item_code}/retry-search")
async def retry_product_search(
    message_id: str,
    item_code: str,
    request: RetrySearchRequest
):
    """
    Relance la recherche SAP pour un article non trouvé.
    Utile si l'article a été créé dans SAP en parallèle.
    """
    global _analysis_cache

    try:
        # 1. Récupérer analyse en cache
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Analyse non trouvée")

        cached_entry = _analysis_cache[message_id]
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            result = cached_entry['data']
        else:
            result = cached_entry

        # 2. Rechercher dans SAP
        from services.sap_business_service import get_sap_business_service
        sap_service = get_sap_business_service()

        search_query = request.search_query or item_code
        sap_items = await sap_service.search_items(search_query, limit=5)

        if not sap_items:
            return {
                "success": False,
                "found": False,
                "message": f"Aucun article trouvé pour '{search_query}'"
            }

        # 3. Retourner résultats pour choix utilisateur
        logger.info(f"Recherche relancée pour {item_code}: {len(sap_items)} résultat(s)")

        return {
            "success": True,
            "found": True,
            "count": len(sap_items),
            "items": [
                {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "quantity_on_hand": getattr(item, 'quantity_on_hand', None)
                }
                for item in sap_items
            ]
        }

    except Exception as e:
        logger.error(f"Retry search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emails/{message_id}/recalculate-pricing")
async def recalculate_pricing(message_id: str):
    """
    Recalcule les prix pour un email déjà analysé.
    Utile pour les emails analysés avant l'implémentation de la Phase 5.

    Returns:
        Analyse mise à jour avec les prix calculés
    """
    global _analysis_cache

    try:
        # 1. Récupérer analyse en cache
        if message_id not in _analysis_cache:
            raise HTTPException(status_code=404, detail="Analyse non trouvée en cache")

        cached_entry = _analysis_cache[message_id]
        if isinstance(cached_entry, dict) and 'data' in cached_entry:
            result = cached_entry['data']
        else:
            result = cached_entry

        # 2. Vérifier qu'il y a des produits matchés
        if not result.product_matches or len(result.product_matches) == 0:
            return {
                "success": False,
                "message": "Aucun produit trouvé dans cette analyse"
            }

        # 3. Vérifier si pricing engine est activé
        pricing_enabled = os.getenv("PRICING_ENGINE_ENABLED", "false").lower() == "true"

        if not pricing_enabled:
            raise HTTPException(
                status_code=503,
                detail="Le moteur de pricing n'est pas activé (PRICING_ENGINE_ENABLED=false)"
            )

        # 4. Importer les modules nécessaires
        from services.pricing_engine import get_pricing_engine
        from services.pricing_models import PricingContext
        from services.email_matcher import MatchedProduct

        pricing_engine = get_pricing_engine()

        # 5. Récupérer CardCode client
        card_code = "UNKNOWN"
        if result.client_matches and len(result.client_matches) > 0:
            best_client = result.client_matches[0]
            card_code = best_client.get('card_code', 'UNKNOWN')
        elif result.extracted_data and result.extracted_data.client_card_code:
            card_code = result.extracted_data.client_card_code

        logger.info(f"🔄 Recalcul pricing pour {message_id} - Client: {card_code}")

        # 6. Préparer contextes pricing pour tous les produits
        pricing_contexts = []
        original_products = []

        for product_data in result.product_matches:
            # Convertir dict en MatchedProduct si nécessaire
            if isinstance(product_data, dict):
                product = MatchedProduct(**product_data)
            else:
                product = product_data

            # Skip si produit non trouvé dans SAP
            if product.not_found_in_sap:
                original_products.append(product)
                continue

            context = PricingContext(
                item_code=product.item_code,
                card_code=card_code,
                quantity=product.quantity,
                supplier_price=None,  # Sera récupéré automatiquement
                apply_margin=float(os.getenv("PRICING_DEFAULT_MARGIN", "45.0")),
                force_recalculate=True  # Force le recalcul même si déjà en cache
            )
            pricing_contexts.append((product, context))

        # 7. Calcul parallèle des prix
        t_start = time.time()

        pricing_tasks = [
            pricing_engine.calculate_price(ctx)
            for _, ctx in pricing_contexts
        ]

        pricing_results = await asyncio.gather(*pricing_tasks, return_exceptions=True)

        # 8. Enrichir produits avec résultats pricing
        enriched_products = []
        pricing_success_count = 0
        pricing_errors = []

        for i, (product, context) in enumerate(pricing_contexts):
            pricing_result = pricing_results[i]

            # Gestion erreurs
            if isinstance(pricing_result, Exception):
                error_msg = f"{product.item_code}: {str(pricing_result)}"
                logger.error(f"Pricing error - {error_msg}")
                pricing_errors.append(error_msg)
                enriched_products.append(product)
                continue

            if pricing_result.success and pricing_result.decision:
                decision = pricing_result.decision

                # Créer produit enrichi avec pricing
                enriched_dict = product.dict()
                enriched_dict.update({
                    "unit_price": decision.calculated_price,
                    "line_total": decision.calculated_price * product.quantity,
                    "pricing_case": decision.case_type.value,
                    "pricing_justification": decision.justification,
                    "requires_validation": decision.requires_validation,
                    "validation_reason": decision.validation_reason,
                    "supplier_price": decision.supplier_price,
                    "margin_applied": decision.margin_applied,
                    "confidence_score": decision.confidence_score,
                    "alerts": decision.alerts,
                    "decision_id": decision.decision_id
                })

                enriched_product = MatchedProduct(**enriched_dict)
                enriched_products.append(enriched_product)

                pricing_success_count += 1

                logger.info(
                    f"  ✓ {decision.case_type.value}: {product.item_code} → "
                    f"{decision.calculated_price:.2f} EUR (marge {decision.margin_applied:.0f}%)"
                )
            else:
                # Fallback: garder produit sans pricing
                enriched_products.append(product)

        # 9. Ajouter produits non trouvés dans SAP (sans pricing)
        enriched_products.extend(original_products)

        # 10. Mettre à jour le cache avec les produits enrichis
        result.product_matches = [p.dict() for p in enriched_products]

        # Mettre à jour le cache (gérer les deux formats)
        if isinstance(_analysis_cache[message_id], dict) and 'data' in _analysis_cache[message_id]:
            _analysis_cache[message_id]['data'] = result
        else:
            _analysis_cache[message_id] = result

        duration_ms = (time.time() - t_start) * 1000

        logger.info(
            f"✅ Recalcul pricing terminé : {duration_ms:.0f}ms - "
            f"{pricing_success_count}/{len(pricing_contexts)} succès"
        )

        return {
            "success": True,
            "pricing_calculated": pricing_success_count,
            "total_products": len(pricing_contexts),
            "duration_ms": duration_ms,
            "errors": pricing_errors if pricing_errors else None,
            "analysis": result.dict()
        }

    except Exception as e:
        logger.error(f"Recalculate pricing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ENDPOINTS : PIÈCES JOINTES STOCKÉES LOCALEMENT
# ============================================================

@router.post("/emails/store-attachments")
async def trigger_attachment_storage(email_id: str = Query(..., description="Microsoft Graph message ID")):
    """
    Déclenche le téléchargement et stockage des pièces jointes si pas encore fait.
    Idempotent : si déjà stockées, retourne la liste existante.
    """
    from services.attachment_storage_service import get_attachment_storage
    storage = get_attachment_storage()
    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    # Vérifier si déjà stockées
    existing = storage.get_stored_attachments(email_id)
    if existing:
        return {
            "email_id": email_id,
            "stored_count": len(existing),
            "already_stored": True,
            "attachments": [a.to_dict() for a in existing],
        }

    # Télécharger maintenant (synchrone pour avoir le résultat immédiatement)
    try:
        stored = await storage.download_and_store_all(email_id, email_id, graph_service)
        return {
            "email_id": email_id,
            "stored_count": len(stored),
            "already_stored": False,
            "attachments": [a.to_dict() for a in stored],
        }
    except Exception as e:
        logger.error("Erreur stockage PJ pour %s: %s", email_id[:30], e)
        raise HTTPException(status_code=500, detail=f"Erreur stockage: {e}")


@router.get("/emails/stored-attachments/serve")
async def serve_stored_attachment(
    email_id: str = Query(..., description="Microsoft Graph message ID"),
    attachment_id: str = Query(..., description="Attachment ID"),
    download: bool = False,
):
    """
    Sert une pièce jointe depuis le stockage local (disque).
    Plus fiable que /stream car ne nécessite pas de reconnexion Graph.

    Paramètre `download=true` force le téléchargement (Content-Disposition: attachment).
    Sinon, affichage inline (pour PDF, images).
    """
    from fastapi.responses import FileResponse
    from services.attachment_storage_service import get_attachment_storage, PREVIEWABLE_TYPES
    import mimetypes

    storage = get_attachment_storage()

    # Chercher le fichier stocké
    att_path = storage.get_attachment_path(email_id, attachment_id)
    if att_path is None:
        raise HTTPException(
            status_code=404,
            detail="Pièce jointe non trouvée localement. Lancez /store-attachments d'abord."
        )

    # Récupérer le nom de fichier original depuis DB
    stored = storage._get_from_db(email_id, attachment_id)
    filename = stored.filename if stored else att_path.name
    content_type = stored.content_type if stored else mimetypes.guess_type(str(att_path))[0]
    content_type = content_type or "application/octet-stream"

    # Disposition
    if download or content_type not in PREVIEWABLE_TYPES:
        disposition = "attachment"
    else:
        disposition = "inline"

    safe_name = filename.encode('ascii', errors='replace').decode('ascii')

    return FileResponse(
        path=str(att_path),
        media_type=content_type,
        filename=safe_name,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "Cache-Control": "private, max-age=3600",  # Cache 1h (fichier local stable)
        }
    )


# ============================================================
# ENDPOINTS : CORRECTIONS MANUELLES
# ============================================================

@router.put("/emails/corrections")
async def save_corrections(
    email_id: str = Query(..., description="Microsoft Graph message ID"),
    body: dict = Body(...),
):
    """
    Sauvegarde des corrections manuelles sur les données extraites.

    Body attendu :
    ```json
    {
      "corrections": [
        {
          "field_type": "product",
          "field_index": 0,
          "field_name": "quantity",
          "corrected_value": 15,
          "original_value": 10
        },
        {
          "field_type": "client",
          "field_name": "card_name",
          "corrected_value": "MARMARA CAM TURKEY"
        }
      ]
    }
    ```
    """
    from services.quote_corrections_db import get_quote_corrections_db
    db = get_quote_corrections_db()

    corrections_list = body.get("corrections", [])
    if not corrections_list:
        raise HTTPException(status_code=400, detail="'corrections' list is required and must not be empty")

    saved = db.save_corrections_batch(email_id, corrections_list)
    return {
        "email_id": email_id,
        "saved_count": len(saved),
        "corrections": [c.to_dict() for c in saved],
    }


@router.delete("/emails/corrections")
async def delete_correction(
    email_id: str = Query(..., description="Microsoft Graph message ID"),
    field_type: str = Query(...),
    field_name: str = Query(...),
    field_index: Optional[int] = Query(None),
):
    """Supprime une correction spécifique (restitue la valeur originale)."""
    from services.quote_corrections_db import get_quote_corrections_db
    db = get_quote_corrections_db()
    db.delete_correction(email_id, field_type, field_name, field_index)
    return {"success": True, "message": f"Correction {field_type}/{field_name} supprimée"}
