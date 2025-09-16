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

class QuoteConfirmationRequest(BaseModel):
    task_id: str
    action: str  # confirm, modify, cancel
    confirmed: bool = False

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
@router.get("/list_draft_quotes")
async def list_draft_quotes():
    """
    Liste tous les devis en mode brouillon
    Utilisé pour alerter l'utilisateur et afficher les devis à valider
    """
    try:
        logger.info("Récupération des devis en brouillon...")
        
        # Utiliser MCPConnector au lieu de l'import direct
        from services.mcp_connector import MCPConnector
        
        result = await MCPConnector.call_sap_mcp("sap_list_draft_quotes", {})
        
        if result and result.get("success"):
            logger.info(f"✅ {result.get('count', 0)} devis en brouillon récupérés")
            
            return {
                "success": True,
                "count": result.get("count", 0),
                "draft_quotes": result.get("draft_quotes", []),
                "has_pending_quotes": result.get("count", 0) > 0
            }
        else:
            logger.error(f"❌ Erreur récupération devis brouillons: {result.get('error', 'Erreur inconnue')}")
            return {
                "success": False,
                "error": result.get("error", "Erreur lors de la récupération"),
                "count": 0,
                "has_pending_quotes": False
            }
            
    except Exception as e:
        logger.exception(f"Erreur endpoint list_draft_quotes: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "count": 0,
            "has_pending_quotes": False
        }
@router.post("/resolve_duplicates")
async def resolve_duplicates(request: dict):
    """
    Gère la résolution des doublons détectés
    Actions possibles: 'consolidate', 'create_new', 'cancel'
    """
    try:
        action = request.get("action")
        client_name = request.get("client_name")
        original_prompt = request.get("original_prompt")
        selected_quote_id = request.get("selected_quote_id")  # Pour consolidation
        
        logger.info(f"Résolution doublons: action={action}, client={client_name}")
        
        if action == "create_new":
            # Forcer la création d'un nouveau devis malgré les doublons
            from workflow.devis_workflow import DevisWorkflow
            
            workflow = DevisWorkflow()
            # Désactiver temporairement la vérification doublons
            workflow.skip_duplicate_check = True
            
            result = await workflow.generate_devis(original_prompt)
            return {"success": True, "action": "created", "result": result}
            
        elif action == "consolidate":
            # Logique de consolidation avec devis existant
            return {
                "success": True, 
                "action": "consolidated",
                "message": f"Consolidation avec devis {selected_quote_id} en cours de développement"
            }
            
        elif action == "cancel":
            return {"success": True, "action": "cancelled", "message": "Opération annulée"}
            
        else:
            return {"success": False, "error": "Action non reconnue"}
            
    except Exception as e:
        logger.exception(f"Erreur résolution doublons: {str(e)}")
        return {"success": False, "error": str(e)}

@router.post("/validate_quote")
async def validate_quote(request: dict):
    """
    Valide un devis brouillon pour le transformer en définitif
    """
    try:
        doc_entry = request.get("doc_entry")
        if not doc_entry:
            return {"success": False, "error": "doc_entry manquant"}
            
        logger.info(f"Validation devis DocEntry: {doc_entry}")
        
        # Utiliser la méthode SAP existante
        from sap_mcp import sap_validate_draft_quote
        result = await sap_validate_draft_quote(doc_entry)
        
        return result
        
    except Exception as e:
        logger.exception(f"Erreur validation devis: {str(e)}")
        return {"success": False, "error": str(e)}

@router.post("/api/quote/confirm")
async def confirm_quote(request: QuoteConfirmationRequest):
    """
    Traite la confirmation de l'utilisateur pour créer ou modifier un devis
    """
    try:
        logger.info(f"Confirmation devis - Action: {request.action}, TaskID: {request.task_id}, Confirmé: {request.confirmed}")
        
        from workflow.devis_workflow import DevisWorkflow
        from services.progress_tracker import get_task_result
        
        # Récupérer le résultat intermédiaire depuis le tracker de progression
        task_result = await get_task_result(request.task_id)
        
        if not task_result:
            return {
                "status": "error",
                "message": f"Impossible de trouver la tâche avec ID: {request.task_id}"
            }
        
        if request.action == "confirm" and request.confirmed:
            # L'utilisateur a confirmé, poursuivre avec la création du devis
            logger.info(f"Confirmation approuvée pour tâche {request.task_id}")
            
            workflow = DevisWorkflow()
            workflow.context = task_result.get("context", {})
            workflow.task_id = request.task_id
            
            # Continuer le flux de travail depuis la dernière étape
            result = await workflow.create_quote_with_confirmation(confirmed=True)
            
            return result
            
        elif request.action == "modify":
            # L'utilisateur veut modifier sa demande
            logger.info(f"Modification demandée pour tâche {request.task_id}")
            
            return {
                "status": "success",
                "message": "Demande prête à être modifiée",
                "action": "modify"
            }
            
        else:  # action == "cancel" ou autre
            # L'utilisateur a annulé
            logger.info(f"Annulation pour tâche {request.task_id}")
            
            return {
                "status": "cancelled",
                "message": "Génération du devis annulée",
                "action": "cancel"
            }
            
    except Exception as e:
        logger.exception(f"Erreur lors de la confirmation du devis: {str(e)}")
        return {
            "status": "error",
            "message": f"Erreur lors de la confirmation: {str(e)}"
        }