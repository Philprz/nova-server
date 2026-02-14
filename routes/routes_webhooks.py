"""
Routes pour gérer les webhooks Microsoft Graph
Reçoit les notifications et déclenche le traitement automatique
"""

import logging
from fastapi import APIRouter, Request, Response, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from services.webhook_service import get_webhook_service
from services.graph_service import get_graph_service
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class WebhookNotification(BaseModel):
    """Modèle d'une notification webhook Microsoft."""
    subscriptionId: str
    subscriptionExpirationDateTime: str
    changeType: str
    resource: str
    resourceData: Dict[str, Any]
    clientState: Optional[str] = None


class WebhookValidation(BaseModel):
    """Modèle de validation webhook."""
    validationToken: Optional[str] = None


@router.post("/notification")
async def receive_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    response: Response
):
    """
    Endpoint pour recevoir les notifications webhook de Microsoft Graph.

    Microsoft envoie deux types de requêtes :
    1. Validation initiale (avec validationToken)
    2. Notifications d'événements (avec changeType, resource, etc.)
    """
    try:
        # Récupérer les paramètres de requête
        validation_token = request.query_params.get("validationToken")

        # CAS 1 : Validation initiale du webhook
        if validation_token:
            logger.info(f"📞 Webhook validation request received")
            # Microsoft attend le token en réponse avec Content-Type: text/plain
            return Response(
                content=validation_token,
                media_type="text/plain",
                status_code=200
            )

        # CAS 2 : Notification d'événement
        body = await request.json()
        logger.info(f"📬 Webhook notification received: {body}")

        # Microsoft envoie un tableau de notifications
        if "value" not in body:
            raise HTTPException(status_code=400, detail="Invalid notification format")

        notifications = body["value"]
        webhook_service = get_webhook_service()

        for notification in notifications:
            # Valider le clientState
            client_state = notification.get("clientState")
            if not webhook_service.validate_notification(client_state):
                logger.warning(f"⚠️ Invalid clientState in notification: {client_state}")
                continue

            # Traiter la notification en arrière-plan (pas de blocage)
            background_tasks.add_task(
                process_notification,
                notification
            )

        return {"status": "accepted", "count": len(notifications)}

    except Exception as e:
        logger.error(f"❌ Error processing webhook notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_notification(notification: Dict[str, Any]):
    """
    Traite une notification webhook en arrière-plan.

    Args:
        notification: Données de la notification
    """
    try:
        change_type = notification.get("changeType")
        resource = notification.get("resource")
        subscription_id = notification.get("subscriptionId")

        logger.info(f"🔄 Processing notification: {change_type} on {resource}")

        # On ne traite que les nouveaux emails (changeType = created)
        if change_type != "created":
            logger.info(f"⏭️ Skipping notification (changeType={change_type})")
            return

        # Extraire l'ID du message depuis la resource
        # Format resource: "Users/{user_id}/Messages/{message_id}"
        resource_parts = resource.split("/")
        if "Messages" not in resource_parts:
            logger.warning(f"⚠️ Unknown resource format: {resource}")
            return

        message_index = resource_parts.index("Messages")
        if message_index + 1 >= len(resource_parts):
            logger.warning(f"⚠️ No message ID in resource: {resource}")
            return

        message_id = resource_parts[message_index + 1]

        logger.info(f"📧 New email detected: {message_id}")

        # Lancer le traitement automatique de l'email
        await auto_process_email(message_id)

    except Exception as e:
        logger.error(f"❌ Error in process_notification: {e}")
        import traceback
        traceback.print_exc()


async def auto_process_email(message_id: str):
    """
    Traite automatiquement un nouvel email.

    NOUVEAU WORKFLOW (Phase Mail-to-Biz stricte):
    1. Récupérer email depuis Microsoft Graph
    2. Extraire PDFs
    3. Appeler mail_processor centralisé (toutes requêtes SAP)
    4. Dual-write: quote_draft + email_analysis (backward compat)

    Args:
        message_id: ID du message à traiter
    """
    try:
        logger.info(f"🤖 Auto-processing email: {message_id}")

        # Importer ici pour éviter circular imports
        from services.email_analyzer import extract_pdf_text
        from services.mail_processor import get_mail_processor
        from services.email_analysis_db import get_email_analysis_db

        graph_service = get_graph_service()

        # 1. Récupérer l'email depuis Microsoft Graph
        email = await graph_service.get_email(message_id, include_attachments=True)
        if not email:
            logger.warning(f"⚠️ Email not found: {message_id}")
            return

        logger.info(f"📧 Email: {email.subject} from {email.from_name}")

        # 2. Extraire le contenu des PDFs si présents
        pdf_contents = []
        MAX_PDF_SIZE = 5 * 1024 * 1024  # 5 MB max

        for attachment in email.attachments:
            if attachment.content_type == "application/pdf":
                if attachment.size > MAX_PDF_SIZE:
                    logger.warning(f"PDF {attachment.name} too large, skip")
                    continue

                try:
                    content_bytes = await graph_service.get_attachment_content(message_id, attachment.id)
                    text = await extract_pdf_text(content_bytes)
                    if text:
                        pdf_contents.append(text)
                        logger.info(f"PDF {attachment.name} extracted")
                except Exception as e:
                    logger.warning(f"Could not extract PDF {attachment.name}: {e}")

        # Préparer body text
        body_text = email.body_content if email.body_content and len(email.body_content.strip()) > 0 else email.body_preview

        # 3. NOUVEAU: Appeler mail_processor centralisé
        mail_processor = get_mail_processor()

        # Préparer payload
        email_payload = {
            "subject": email.subject,
            "body": body_text,
            "from_address": email.from_address,
            "from_name": email.from_name,
            "pdf_contents": pdf_contents,
            "received_at": email.received_datetime.isoformat() if email.received_datetime else None
        }

        # Traiter avec nouveau workflow (LLM + SAP + Pricing + Persist)
        quote_draft = await mail_processor.process_incoming_email(
            mail_id=message_id,
            email_payload=email_payload
        )

        logger.info(f"✅ Quote draft créé: {quote_draft.id} pour mail {message_id}")
        logger.info(f"   Client: {quote_draft.client_status} ({quote_draft.client_code or 'None'})")
        logger.info(f"   Lignes: {len(quote_draft.lines)}")

        # 4. DUAL-WRITE: Sauvegarder aussi dans email_analysis (backward compat)
        # Permet au frontend existant de continuer à fonctionner
        analysis_db = get_email_analysis_db()

        # Build analysis_result compatible avec structure existante
        analysis_result = {
            "quote_draft_id": quote_draft.id,
            "is_quote_request": True,
            "client_status": quote_draft.client_status,
            "client_card_code": quote_draft.client_code,
            "lines_count": len(quote_draft.lines),
            "product_matches": quote_draft.lines,  # Lignes avec métadonnées SAP complètes
            "raw_email_payload": quote_draft.raw_email_payload
        }

        analysis_db.save_analysis(
            email_id=message_id,
            subject=email.subject,
            from_address=email.from_address,
            analysis_result=analysis_result
        )

        logger.info(f"✅ Auto-processing completed for {message_id}")
        logger.info(f"💾 Dual-write: quote_draft + email_analysis (backward compat)")

    except Exception as e:
        logger.error(f"❌ Error in auto_process_email: {e}")
        import traceback
        traceback.print_exc()


# Import os pour les env vars
import os


@router.get("/subscriptions")
async def list_subscriptions():
    """Liste toutes les subscriptions actives."""
    webhook_service = get_webhook_service()
    subscriptions = webhook_service.get_active_subscriptions()

    return {
        "count": len(subscriptions),
        "subscriptions": subscriptions
    }


@router.get("/subscriptions/to-renew")
async def list_subscriptions_to_renew():
    """Liste les subscriptions à renouveler (expire < 24h)."""
    webhook_service = get_webhook_service()
    subscriptions = webhook_service.get_subscriptions_to_renew()

    return {
        "count": len(subscriptions),
        "subscriptions": subscriptions
    }


@router.post("/subscriptions/renew/{subscription_id}")
async def renew_subscription(subscription_id: str):
    """Renouvelle une subscription."""
    try:
        webhook_service = get_webhook_service()
        result = await webhook_service.renew_subscription(subscription_id)

        return {
            "success": True,
            "subscription": result
        }

    except Exception as e:
        logger.error(f"Error renewing subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    """Supprime une subscription."""
    try:
        webhook_service = get_webhook_service()
        result = await webhook_service.delete_subscription(subscription_id)

        return {
            "success": True,
            "message": "Subscription deleted"
        }

    except Exception as e:
        logger.error(f"Error deleting subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Retourne le statut du système de renouvellement automatique."""
    try:
        from services.webhook_scheduler import get_webhook_scheduler

        scheduler = get_webhook_scheduler()
        next_run = scheduler.get_next_run_time()

        return {
            "success": True,
            "scheduler": {
                "is_running": scheduler.is_running(),
                "next_run_time": next_run,
                "timezone": "Europe/Paris (UTC+1)"
            }
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
