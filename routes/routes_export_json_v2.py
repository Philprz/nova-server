"""Endpoint pour exporter le JSON pre-sap-quote en réutilisant l'analyse existante"""
from fastapi import APIRouter, HTTPException
from services.email_analyzer import get_email_analyzer
import httpx
import logging

router = APIRouter(prefix="/api/export-v2", tags=["export"])
logger = logging.getLogger(__name__)

@router.get("/pre-sap-quote/{email_id}")
async def export_pre_sap_quote_from_analysis(email_id: str):
    """
    Exporte le JSON pre-sap-quote en réutilisant l'analyse déjà effectuée.
    Appelle l'endpoint /api/graph/emails/{email_id}/analyze et reformate le résultat.
    """
    try:
        # Appeler l'endpoint d'analyse existant (qui fonctionne)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:8001/api/graph/emails/{email_id}/analyze?force=false",
                timeout=120.0
            )

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Analysis failed")

            analysis = response.json()

        # Vérifier si c'est un devis
        if analysis.get("classification") != "QUOTE_REQUEST":
            return {
                "error": "Not a quote request",
                "classification": analysis.get("classification", "UNKNOWN")
            }

        # Extraire les données matchées
        client_matches = analysis.get("client_matches", [])
        product_matches = analysis.get("product_matches", [])

        best_client = client_matches[0] if client_matches else None

        # Construire le JSON pre-sap-quote
        pre_sap_json = {
            "sap_document_type": "SalesQuotation",
            "business_partner": {
                "CardCode": best_client.get("card_code") if best_client else None,
                "CardName": best_client.get("card_name") if best_client else "Unknown",
                "ContactEmail": best_client.get("email_address", "") if best_client else "",
                "ToBeCreated": not bool(best_client and best_client.get("card_code"))
            },
            "document_lines": [
                {
                    "ItemCode": product.get("item_code"),
                    "ItemDescription": product.get("item_name") or product.get("item_code"),
                    "Quantity": product.get("quantity", 1),
                    "RequestedDeliveryDate": None,
                    "ToBeCreated": product.get("score", 0) < 100
                }
                for product in product_matches
            ],
            "meta": {
                "source": "office365",
                "email_id": email_id,
                "confidence_level": analysis.get("confidence", "medium"),
                "manual_validation_required": not (
                    best_client and
                    best_client.get("score", 0) >= 95 and
                    all(p.get("score", 0) == 100 for p in product_matches)
                ),
                "validated": False,
                "client_score": best_client.get("score", 0) if best_client else 0,
                "product_count": len(product_matches),
                "false_positives_filtered": True,
                "classification": analysis.get("classification"),
                "reasoning": analysis.get("reasoning")
            }
        }

        return pre_sap_json

    except httpx.TimeoutException:
        logger.error(f"Timeout calling analyze endpoint for {email_id}")
        raise HTTPException(status_code=504, detail="Analysis timeout")
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
