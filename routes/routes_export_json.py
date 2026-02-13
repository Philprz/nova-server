"""Endpoint pour exporter le JSON pre-sap-quote avec données backend"""
from fastapi import APIRouter, HTTPException
from services.email_analyzer import get_email_analyzer
from services.email_matcher import get_email_matcher
from services.graph_service import get_graph_service
import logging

router = APIRouter(prefix="/api/export", tags=["export"])
logger = logging.getLogger(__name__)

@router.get("/pre-sap-quote/{email_id}")
async def export_pre_sap_quote(email_id: str):
    """
    Exporte le JSON pre-sap-quote avec les données du matching SAP backend
    (client_matches, product_matches déjà filtrés)
    """
    try:
        # Récupérer l'email
        graph_service = get_graph_service()
        email = await graph_service.get_email(email_id)
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # Analyser l'email (avec matching SAP)
        analyzer = get_email_analyzer()
        matcher = get_email_matcher()
        
        # Extraire corps et pièces jointes
        body = email.body_content or email.body_preview
        
        # Quick classify
        quick_result = analyzer.quick_classify(email.subject, body)

        if not quick_result["likely_quote"]:
            return {
                "error": "Not a quote request",
                "classification": "NON_DEVIS"
            }
        
        # Matcher avec SAP
        await matcher.ensure_cache()
        match_result = await matcher.match_email(
            body=body,
            sender_email=email.from_address,
            subject=email.subject
        )
        
        # Construire le JSON pre-sap-quote
        best_client = match_result.clients[0] if match_result.clients else None
        
        pre_sap_json = {
            "sap_document_type": "SalesQuotation",
            "business_partner": {
                "CardCode": best_client.card_code if best_client else None,
                "CardName": best_client.card_name if best_client else "Unknown",
                "ContactEmail": best_client.email_address if best_client and best_client.email_address else "",
                "ToBeCreated": not bool(best_client and best_client.card_code)
            },
            "document_lines": [
                {
                    "ItemCode": product.item_code,
                    "ItemDescription": product.item_name or product.item_code,
                    "Quantity": product.quantity,
                    "RequestedDeliveryDate": None,
                    "ToBeCreated": product.score < 100
                }
                for product in match_result.products
            ],
            "meta": {
                "source": "office365",
                "email_id": email_id,
                "confidence_level": "high" if best_client and best_client.score >= 95 else "medium",
                "manual_validation_required": not (best_client and best_client.score >= 95 and all(p.score == 100 for p in match_result.products)),
                "validated": False,
                "client_score": best_client.score if best_client else 0,
                "product_count": len(match_result.products),
                "false_positives_filtered": True
            }
        }
        
        return pre_sap_json
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
