# routes/routes_graph.py
"""
Routes API pour Microsoft Graph (connexion Office 365 / emails)
"""

import os
import logging
import base64
import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv

from services.graph_service import get_graph_service, GraphEmail, GraphAttachment, GraphEmailsResponse
from services.email_analyzer import get_email_analyzer, extract_pdf_text, EmailAnalysisResult, ExtractedQuoteData, ExtractedProduct
from services.email_matcher import get_email_matcher

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache simple pour les résultats d'analyse (en production, utiliser Redis)
_analysis_cache: dict = {}


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
        return result

    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/{message_id}", response_model=GraphEmail)
async def get_email(message_id: str):
    """
    Récupère un email complet avec son body et ses pièces jointes.
    """
    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        email = await graph_service.get_email(message_id, include_attachments=True)
        return email

    except Exception as e:
        logger.error(f"Error fetching email {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/{message_id}/attachments", response_model=List[GraphAttachment])
async def get_email_attachments(message_id: str):
    """
    Récupère la liste des pièces jointes d'un email.
    """
    graph_service = get_graph_service()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        attachments = await graph_service.get_attachments(message_id)
        return attachments

    except Exception as e:
        logger.error(f"Error fetching attachments for {message_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/emails/{message_id}/analyze", response_model=EmailAnalysisResult)
async def analyze_email(message_id: str, force: bool = False):
    """
    Analyse un email avec l'IA pour déterminer s'il s'agit d'une demande de devis.
    Le résultat est mis en cache.

    Args:
        message_id: ID de l'email
        force: Si True, force la ré-analyse même si le résultat est en cache
    """
    global _analysis_cache

    # Vérifier le cache (sauf si force=True)
    if not force and message_id in _analysis_cache:
        logger.info(f"Returning cached analysis for {message_id}")
        return _analysis_cache[message_id]

    if force:
        logger.info(f"Forcing re-analysis for {message_id}")

    graph_service = get_graph_service()
    email_analyzer = get_email_analyzer()

    if not graph_service.is_configured():
        raise HTTPException(status_code=400, detail="Microsoft Graph credentials not configured")

    try:
        # Récupérer l'email complet
        email = await graph_service.get_email(message_id, include_attachments=True)

        # Extraire le contenu des PDFs si présents
        pdf_contents = []
        for attachment in email.attachments:
            if attachment.content_type == "application/pdf":
                try:
                    content_bytes = await graph_service.get_attachment_content(
                        message_id, attachment.id
                    )
                    text = await extract_pdf_text(content_bytes)
                    if text:
                        pdf_contents.append(text)
                except Exception as e:
                    logger.warning(f"Could not extract PDF {attachment.name}: {e}")

        # Analyser l'email (classification LLM/rules)
        body_text = email.body_content or email.body_preview
        result = await email_analyzer.analyze_email(
            subject=email.subject,
            body=body_text,
            sender_email=email.from_address,
            sender_name=email.from_name,
            pdf_contents=pdf_contents
        )

        # Enrichir avec le matching SAP (clients + produits réels)
        try:
            matcher = get_email_matcher()
            # Nettoyer le body pour le matching (HTML → texte)
            clean_text = email_analyzer._clean_html(body_text)
            # Ajouter le contenu des PDFs au texte de matching
            if pdf_contents:
                clean_text += " " + " ".join(pdf_contents)

            match_result = await matcher.match_email(
                body=clean_text,
                sender_email=email.from_address,
                subject=email.subject
            )

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

        except Exception as e:
            logger.warning(f"SAP matching failed (non-blocking): {e}")

        # Mettre en cache (limiter à 100 entrées)
        if len(_analysis_cache) > 100:
            oldest_keys = list(_analysis_cache.keys())[:20]
            for key in oldest_keys:
                del _analysis_cache[key]

        _analysis_cache[message_id] = result

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

    if message_id in _analysis_cache:
        return _analysis_cache[message_id]

    return None


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
