# routes/routes_devis.py - Correction pour interface
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class DevisPromptRequest(BaseModel):
    prompt: str
    draft_mode: bool = False

# routes/routes_devis.py - CORRECTION DU BUG

@router.post("/generate_quote")
async def generate_quote(request: DevisPromptRequest):
    """
    Génère un devis à partir d'une demande en langage naturel
    CORRIGÉ: Vérifie le bon champ pour déterminer le succès
    """
    try:
        from workflow.devis_workflow import DevisWorkflow
        
        logger.info(f"Début génération devis: {request.prompt}")
        logger.info(f"Mode draft: {request.draft_mode}")
        
        workflow = DevisWorkflow()
        workflow_result = await workflow.process_prompt(
            request.prompt, 
            draft_mode=request.draft_mode
        )
        
        logger.info(f"Workflow terminé avec statut: {workflow_result.get('success')}")
        
        # ✅ CORRECTION CRITIQUE: Vérifier le bon champ
        if workflow_result.get("success"):  # Comparaison simplifiée
            # Structure attendue par showQuoteResult()
            formatted_response = {
                "status": "success",  # ← Pour l'interface
                "quote_id": workflow_result.get("quote_id", f"NOVA-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
                "client": {
                    "name": workflow_result.get("client", {}).get("name", "Client extrait"),
                    "account_number": workflow_result.get("client", {}).get("account_number", "N/A"),
                    "salesforce_id": workflow_result.get("client", {}).get("salesforce_id", "")
                },
                "products": workflow_result.get("products", []),
                "total_amount": workflow_result.get("total_amount", 0.0),
                "currency": workflow_result.get("currency", "EUR"),
                "date": workflow_result.get("date", datetime.now().strftime("%Y-%m-%d")),
                "quote_status": workflow_result.get("quote_status", "Created"),
                "all_products_available": workflow_result.get("all_products_available", True),
                "message": workflow_result.get("message", "Devis généré avec succès"),
                
                # Informations système pour debug
                "sap_doc_num": workflow_result.get("sap_doc_num"),
                "salesforce_quote_id": workflow_result.get("salesforce_quote_id"),
                "draft_mode": request.draft_mode
            }
            
            logger.info("Réponse formatée pour interface avec succès")
            return formatted_response
            
        else:
            # Gestion des erreurs
            error_response = {
                "status": "error", 
                "message": workflow_result.get("message", "Erreur lors de la génération du devis"),
                "error_details": workflow_result.get("error_details", "Détails indisponibles")
            }
            logger.error(f"Erreur workflow: {error_response['message']}")
            return error_response
            
    except Exception as e:
        logger.exception(f"Erreur critique dans l'endpoint: {str(e)}")
        return {
            "status": "error",
            "message": f"Erreur système: {str(e)}",
            "error_details": "Erreur côté serveur"
        }