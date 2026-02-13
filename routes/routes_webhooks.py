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

    Args:
        message_id: ID du message à traiter
    """
    try:
        logger.info(f"🤖 Auto-processing email: {message_id}")

        # Importer ici pour éviter circular imports
        from services.email_analyzer import get_email_analyzer, extract_pdf_text
        from services.email_matcher import get_email_matcher
        from services.pricing_engine import get_pricing_engine
        from services.email_analysis_db import get_email_analysis_db

        graph_service = get_graph_service()
        email_analyzer = get_email_analyzer()
        matcher = get_email_matcher()

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

        # Nettoyage pour matching
        clean_text = email_analyzer._clean_html(body_text)
        if pdf_contents:
            clean_text += " " + " ".join(pdf_contents)

        # 3. LLM analysis + SAP matching EN PARALLÈLE
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

        # Récupérer résultats
        llm_result = parallel_results[0]
        match_result = parallel_results[1]

        if isinstance(llm_result, Exception):
            logger.error(f"LLM analysis failed: {llm_result}")
            return

        if isinstance(match_result, Exception):
            logger.error(f"SAP matching failed: {match_result}")
            return

        # Vérifier si c'est une demande de devis
        if not llm_result.is_quote_request:
            logger.info(f"⏭️ Not a quote request, skipping auto-processing")
            return

        logger.info(f"✅ Quote request detected")

        # Calcul pricing automatique
        pricing_enabled = os.getenv("PRICING_ENGINE_ENABLED", "false").lower() == "true"

        if pricing_enabled and match_result and match_result.products:
            logger.info(f"💰 Calcul pricing pour {len(match_result.products)} produits...")

            from services.pricing_engine import get_pricing_engine
            from services.pricing_models import PricingContext

            pricing_engine = get_pricing_engine()

            card_code = "UNKNOWN"
            if match_result.best_client:
                card_code = match_result.best_client.card_code

            # Calcul parallèle
            pricing_contexts = []
            for product in match_result.products:
                if product.not_found_in_sap:
                    continue

                context = PricingContext(
                    item_code=product.item_code,
                    card_code=card_code,
                    quantity=product.quantity,
                    supplier_price=None,
                    apply_margin=float(os.getenv("PRICING_DEFAULT_MARGIN", "45.0")),
                    force_recalculate=False
                )
                pricing_contexts.append((product, context))

            pricing_tasks = [
                pricing_engine.calculate_price(ctx)
                for _, ctx in pricing_contexts
            ]

            pricing_results = await asyncio.gather(*pricing_tasks, return_exceptions=True)

            # Enrichir produits avec pricing
            enriched_products = []
            for i, (product, context) in enumerate(pricing_contexts):
                pricing_result = pricing_results[i]

                if isinstance(pricing_result, Exception):
                    logger.error(f"Pricing error for {product.item_code}: {pricing_result}")
                    enriched_products.append(product)
                    continue

                if pricing_result.success and pricing_result.decision:
                    decision = pricing_result.decision
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
                        "alerts": decision.alerts
                    })
                    enriched_product = type(product)(**enriched_dict)
                    enriched_products.append(enriched_product)
                else:
                    enriched_products.append(product)

            # Remplacer produits
            match_result.products = enriched_products

        # 4. Sauvegarder en base de données
        analysis_db = get_email_analysis_db()

        analysis_result = {
            "is_quote_request": True,
            "confidence": llm_result.confidence,
            "reasoning": llm_result.reasoning,
            "extracted_data": llm_result.extracted_data.dict() if llm_result.extracted_data else None,
            "product_matches": [p.dict() for p in match_result.products] if match_result and match_result.products else [],
            "best_client": match_result.best_client.dict() if match_result and match_result.best_client else None,
            "other_clients": [c.dict() for c in match_result.clients] if match_result and match_result.clients else []
        }

        analysis_db.save_analysis(
            email_id=message_id,
            subject=email.subject,
            from_address=email.from_address,
            analysis_result=analysis_result
        )

        logger.info(f"✅ Auto-processing completed for {message_id}")
        logger.info(f"💾 Analysis persisted to DB")

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
