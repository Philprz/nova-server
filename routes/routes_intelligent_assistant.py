"""
🤖 Routes pour l'Assistant Intelligent NOVA
==========================================

API conversationnelle qui transforme NOVA en collègue intelligent
capable de comprendre les demandes en langage naturel et proposer
des solutions proactives.
"""
from __future__ import annotations  # optionnel mais recommandé
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Request, BackgroundTasks
from auth.dependencies import get_current_user
import time
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, validator, model_validator
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import re
import json

from services.security_helpers import escape_soql, safe_int

# Configuration du router FastAPI
router = APIRouter(tags=["Assistant Intelligent"], dependencies=[Depends(get_current_user)])
# Import du système de progression
from services.progress_tracker import progress_tracker, TaskStatus
from workflow.devis_workflow import DevisWorkflow
from workflow.client_creation_workflow import ClientCreationWorkflow, client_creation_workflow
logger = logging.getLogger(__name__)

# Import des services NOVA existants
from services.suggestion_engine import SuggestionEngine, SuggestionResult
from services.client_validator import ClientValidator
from services.progress_tracker import ProgressTracker
from services.mcp_connector import MCPConnector
from services.llm_extractor import LLMExtractor, get_llm_extractor
# Import des routes existantes pour réutiliser la logique
import asyncio
import httpx
import secrets
from services.websocket_manager import websocket_manager
# 🔧 MODIFICATION : Ajouter le modèle pour la progression
class ProgressChatMessage(BaseModel):
    """Message de chat avec support progression"""
    message: str
    draft_mode: bool = False
    conversation_history: Optional[list] = []
    use_progress_tracking: bool = True  # 🆕 NOUVEAU : Active le tracking

class ProgressChatResponse(BaseModel):
    """Réponse avec support progression"""
    success: bool
    task_id: Optional[str] = None  # 🆕 NOUVEAU : ID pour le polling
    
    response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    use_polling: bool = False  # 🆕 NOUVEAU : Indique si utiliser polling

class QuoteRequest(BaseModel):
    # Champs principaux - l'un des deux est requis
    prompt: Optional[str] = Field(None, description="Message utilisateur")
    message: Optional[str] = Field(None, description="Message utilisateur (alias)")
    
    # Champs optionnels
    draft_mode: bool = Field(False, description="Mode brouillon")
    task_id: Optional[str] = Field(None, description="Task ID pré-généré côté client")
    websocket_task_id: Optional[str] = Field(None, description="Task ID WebSocket pré-connecté")
    force_production: bool = Field(False, description="Force le mode production")
    
    def __init__(self, **data):
        if 'websocket_task_id' in data and not data.get('task_id'):
            data['task_id'] = data['websocket_task_id']
        super().__init__(**data)

    @model_validator(mode='before')
    @classmethod
    def validate_message_fields(cls, values: Any) -> Any:
        # Pydantic peut passer autre chose qu'un dict (ex: déjà une instance)
        if not isinstance(values, dict):
            return values

        # Copie websocket_task_id -> task_id si manquant
        if values.get('websocket_task_id') and not values.get('task_id'):
            values['task_id'] = values['websocket_task_id']

        # Exiger au moins l'un des deux: prompt ou message
        prompt = values.get('prompt')
        message = values.get('message')
        if not prompt and not message:
            raise ValueError('Prompt ou message requis')

        # Normaliser: dupliquer l'un vers l'autre si nécessaire
        if prompt and not message:
            values['message'] = prompt
        elif message and not prompt:
            values['prompt'] = message

        return values

    
    
# ✅ MODÈLES CORRIGÉS avec validation Field
class WorkflowCreateQuoteRequest(BaseModel):
    """Modèle validé pour la création de devis"""
    message: str = Field(..., description="Demande en langage naturel", min_length=1)
    draft_mode: Optional[bool] = Field(False, description="Mode brouillon")
    force_production: Optional[bool] = Field(False, description="Force production")
    websocket_task_id: Optional[str] = Field(None, description="Task ID WebSocket pré-connecté")  # 🔧 NOUVEAU
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message vide non autorisé')
        return v.strip()

# ✅ MODÈLE DE RÉPONSE
class WorkflowCreateQuoteResponse(BaseModel):
    """Réponse standardisée"""
    success: bool
    status: Optional[str] = None
    task_id: Optional[str] = None
    client: Optional[Dict[str, Any]] = None
    products: Optional[List[Dict[str, Any]]] = None
    total_amount: Optional[float] = None
    quote_id: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    websocket_url: Optional[str] = None
    interaction_data: Optional[Dict[str, Any]] = None  # 🆕 NOUVEAU champ
    
@router.post("/workflow/create_quote", response_model=WorkflowCreateQuoteResponse)
async def start_quote_workflow(
    request: WorkflowCreateQuoteRequest,
    background_tasks: BackgroundTasks
) -> WorkflowCreateQuoteResponse:
    """
    Exécute le workflow de création de devis en arrière-plan.
    """
    try:
        # 1. Génération de task_id si nécessaire
        task_id = request.websocket_task_id or f"quote_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"
        logger.info(f"🔑 Démarrage du DevisWorkflow pour task_id={task_id}")
        # CORRECTION: Créer immédiatement la tâche dans le tracker
        task = progress_tracker.create_task(
            user_prompt=request.message,
            draft_mode=request.draft_mode,
            task_id=task_id
        )

        # 2. Instanciation du workflow
        workflow = DevisWorkflow(validation_enabled=True, draft_mode=True, force_production=True)

        # 3. Lancement en arrière-plan
        background_tasks.add_task(workflow.process_prompt, request.message, task_id)

        # 4. Réponse immédiate typée
        return WorkflowCreateQuoteResponse(
            success=True,
            task_id=task_id,
            status="started",
            websocket_url=f"/ws/assistant/{task_id}",
            message="🚀 Workflow démarré en arrière-plan"
            
        )

    except ImportError as e:
        logger.error(f"Erreur import workflow: {e}")
        raise HTTPException(status_code=500, detail="Workflow de devis non disponible")
    except Exception as e:
        logger.error(f"❌ Erreur exécution workflow: {e}")
        return WorkflowCreateQuoteResponse(
            success=False,
            task_id=task_id,
            status="error",
            message=f"**Erreur technique**\n\n{e}"
        )
@router.post('/workflow/create_client')
async def workflow_create_client(request: Dict[str, Any]):
    """
    🚀 Alias pour la création complète de client.
    Ce point d'entrée accepte un corps JSON du type {"client_data": {...}, "validated": bool}
    et s'appuie sur le workflow existant pour créer un client.
    """
    try:
        client_data = request.get('client_data', {})
        validated = request.get('validated', False)
        
        workflow = ClientCreationWorkflow()
        if validated:
            # Si les données sont déjà validées, créer directement le client
            result = await workflow.create_client_in_salesforce(client_data)
        else:
            # Sinon, lancer le workflow complet de recherche/validation
            result = await workflow.process_client_creation_request(client_data)
        return result
    except Exception as e:
        logger.error(f"Erreur création client via alias: {e}")
        return {'success': False, 'error': str(e), 'message': f"Erreur lors de la création du client"}

async def websocket_endpoint(websocket: WebSocket, task_id: str):
    logger.info(f"🔌 WebSocket - Tentative de connexion pour {task_id}")
    try:
        await websocket_manager.connect(websocket, task_id)
        logger.info(f"✅ WebSocket - Connexion établie pour {task_id}")
        
        while True:
            # Timeout de 60 secondes pour éviter la déconnexion immédiate
            try:
                # Utiliser receive_text avec un timeout plus généreux
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                logger.debug(f"📥 WebSocket - Message reçu de {task_id}: {data}")
                
                # Parse du message JSON
                try:
                    message = json.loads(data)
                    message_type = message.get("type")
                    
                    if message_type == "user_response":
                        logger.info(f"🎯 Traitement user_response pour {task_id}: {message}")
                        response_data = message.get("data", {})
                        # Importer et traiter la réponse utilisateur
                        from routes.routes_progress import handle_user_response_task
                        await handle_user_response_task(task_id, response_data)
                        
                        # Confirmer la réception
                        logger.info(f"✅ user_response traité avec succès pour {task_id}")
                        await websocket.send_text(json.dumps({
                            "type": "user_response_processed",
                            "task_id": task_id,
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                    else:
                        # Echo pour vérifier la connexion (ping/pong)
                        if message_type == "ping":
                            # Répondre au ping pour maintenir la connexion
                            await websocket.send_text(json.dumps({
                                "type": "pong",
                                "task_id": task_id,
                                "timestamp": datetime.utcnow().isoformat()
                            }))
                        else:
                            # Pour tout autre type de message, envoyer un echo générique
                            await websocket.send_text(json.dumps({
                                "type": "echo",
                                "task_id": task_id,
                                "received_type": message_type,
                                "timestamp": datetime.utcnow().isoformat()
                            }))
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ WebSocket - Message non JSON reçu de {task_id}")
                except asyncio.TimeoutError:
                    # Envoyer un ping pour maintenir la connexion
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "ping",
                            "task_id": task_id,
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                        continue
                    except Exception:
                        logger.warning(f"⚠️ WebSocket ping failed pour {task_id}")
                        break
                    
            except WebSocketDisconnect:
                logger.warning(f"⚠️ WebSocket - Client déconnecté: {task_id}")
                break
            except Exception as e:
                logger.error(f"❌ WebSocket - Erreur: {str(e)}")
                break
                
    except Exception as e:
        logger.error(f"❌ WebSocket - Erreur connexion {task_id}: {str(e)}")
    finally:
        await websocket_manager.disconnect(websocket, task_id)
        logger.info(f"🔌 WebSocket - Déconnexion complète pour {task_id}")
@router.get("/api/assistant/workflow/pending-interaction/{task_id}")
async def get_pending_interaction(task_id: str):
    """Récupère les interactions en attente pour un task_id et les marque comme traités"""
    # Vérifier dans websocket_manager.pending_messages
    if task_id in websocket_manager.pending_messages:
        messages = websocket_manager.pending_messages[task_id]
        if messages:
            # Retourner le premier message en attente ET le supprimer pour éviter duplication
            message = messages.pop(0)
            # Si plus de messages, supprimer la clé si liste vide
            if not messages:
                websocket_manager.pending_messages.pop(task_id, None)
            logger.info(f"📨 Interaction en attente récupérée et supprimée pour {task_id}")
            return JSONResponse(content=message)
    
    # Vérifier aussi dans progress_tracker
    task_info = progress_tracker.get_task(task_id)
    if task_info and task_info.get("status") == "user_interaction_required":
        logger.info(f"📋 Tâche en attente d'interaction: {task_id}")
        return JSONResponse(content={
            "type": "user_interaction_required",
            "task_id": task_id,
            "interaction_data": task_info.get("interaction_data", {})
        })
    
    return JSONResponse(content={"status": "no_interaction_pending"})

# 🔧 MODIFICATION : Fonction chat_with_nova modifiée
@router.post("/chat")
async def chat_with_nova_with_progress(
    message_data: ProgressChatMessage, 
    background_tasks: BackgroundTasks
):
    """
    Chat avec NOVA - Version avec progression temps réel
    """
    try:
        logger.info(f"📨 Message reçu: {message_data.message[:100]}...")
        
        # Détecter si c'est une demande de devis (nécessite progression)
        message_lower = message_data.message.lower()
        needs_progress = any(keyword in message_lower for keyword in [
            'devis', 'quote', 'quotation', 'proposition', 'offre',
            'prix', 'tarif', 'commande', 'créer', 'générer'
        ])
        
        # 🆕 NOUVEAU : Si progression nécessaire ET activée
        if needs_progress and message_data.use_progress_tracking:
            logger.info("🔄 Demande de devis détectée - Mode progression activé")
            
            # Créer une tâche de tracking
            task = progress_tracker.create_task(
                user_prompt=message_data.message,
                draft_mode=message_data.draft_mode
            )
            
            # Lancer la génération en arrière-plan
            background_tasks.add_task(
                _execute_quote_with_progress,
                task.task_id,
                message_data.message,
                message_data.draft_mode,
                message_data.conversation_history
            )
            
            return ProgressChatResponse(
                success=True,
                task_id=task.task_id,
                use_polling=True,
                response={
                    "type": "progress_started",
                    "message": "🤖 NOVA analyse votre demande de devis...",
                    "task_id": task.task_id,
                    "polling_url": f"/progress/quote_status/{task.task_id}"
                }
            )
        
        # 🔧 MODIFICATION : Mode synchrone pour les autres demandes
        else:
            logger.info("💬 Traitement chat standard (sans progression)")
            
            # Appeler l'ancien système pour les questions simples
            result = await _handle_simple_chat(message_data)
            
            return ProgressChatResponse(
                success=True,
                use_polling=False,
                response=result
            )
            
    except Exception as e:
        logger.error(f"❌ Erreur chat_with_nova_with_progress: {str(e)}", exc_info=True)
        return ProgressChatResponse(
            success=False,
            error=str(e),
            response={
                "message": f"❌ Erreur: {str(e)}",
                "suggestions": ['Réessayer', 'Reformuler', 'Contacter le support']
            }
        )
    
# Ajouter cette fonction après la définition de create_quote_workflow
async def _wait_for_websocket_connection(task_id: str, timeout: int = 15):
    """Attend qu'une connexion WebSocket soit établie pour le task_id"""
    
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if websocket_manager.task_connections.get(task_id):
            logger.info(f"✅ Connexion WebSocket confirmée pour {task_id}")
            return True
        await asyncio.sleep(0.5)
    
    logger.warning(f"⚠️ Timeout attente WebSocket pour {task_id}")
    return False
# 🆕 NOUVELLE FONCTION : Exécution avec progression
async def _execute_quote_with_progress(task_id: str, message: str, draft_mode: bool = False, conversation_history: list = None):
    """
    Exécute la génération de devis avec tracking de progression
    """
    conversation_history = conversation_history or []

    try:
        logger.info(f"🔄 Démarrage génération avec progression - Task: {task_id}")
        
        workflow = DevisWorkflow(
            validation_enabled=True, 
            draft_mode=draft_mode,
            task_id=task_id
        )
        
        # L'historique sera géré différemment si nécessaire
        result = await workflow.process_prompt(
            message,
            task_id=task_id
        )
        
        logger.info(f"✅ Génération terminée avec succès - Task: {task_id}")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur génération avec progression: {str(e)}", exc_info=True)
        progress_tracker.fail_task(task_id, f"Erreur d'exécution: {str(e)}")

# 🔧 MODIFICATION : Fonction pour chat simple (sans progression)
async def _handle_simple_chat(message_data: ProgressChatMessage) -> Dict[str, Any]:
    """
    Gère les messages de chat simples sans progression
    """
    try:
        # Importer les modules nécessaires

        message = message_data.message
        logger.info(f"💬 Chat simple: {message[:50]}...")

        # Obtenir l'instance de l'extracteur
        llm_extractor = get_llm_extractor()

        # Analyser le type de demande
        extraction = await llm_extractor.extract_quote_info(message)
        
        if extraction.get("action_type") == "RECHERCHE_PRODUIT":
            # Recherche de produits
            return await _handle_product_search(extraction)
            
        elif extraction.get("action_type") == "INFO_CLIENT":
            # Information client
            return await _handle_client_info(extraction)
            
        elif extraction.get("action_type") == "CONSULTATION_STOCK":
            # Consultation stock
            return await _handle_stock_query(extraction)
            
        else:
            # Chat général
            return {
                "type": "chat",
                "message": f"🤖 J'ai compris votre demande: {message}\n\n" +
                          "💡 Je peux vous aider avec:\n" +
                          "• Création de devis\n" +
                          "• Recherche de produits\n" +
                          "• Information clients\n" +
                          "• Consultation de stock",
                "suggestions": [
                    "Créer un devis",
                    "Rechercher un produit", 
                    "Info client",
                    "Vérifier le stock"
                ]
            }
            
    except Exception as e:
        logger.error(f"❌ Erreur chat simple: {str(e)}", exc_info=True)
        return {
            "type": "error",
            "message": f"❌ Erreur de traitement: {str(e)}",
            "suggestions": ['Réessayer', 'Reformuler']
        }
@router.post("/continue_quote")
async def continue_quote_endpoint(request: dict):
    """Continue le workflow après interaction utilisateur"""
    try:
        task_id = request.get("task_id")
        user_input = request.get("user_input", {})
        context = request.get("context", {})
        
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id requis")
        
        # Récupérer l'instance workflow
        workflow = DevisWorkflow(task_id=task_id, force_production=True)
        
        # Continuer avec l'input utilisateur
        result = await workflow.continue_after_user_input(user_input, context)
        
        return {"success": True, "data": result}
        
    except Exception as e:
        logger.error(f"Erreur continue_quote: {e}")
        return {"success": False, "error": str(e)}
# 🆕 NOUVELLES FONCTIONS : Gestionnaires spécialisés

async def _handle_product_search(extraction: Dict[str, Any]) -> Dict[str, Any]:
    """Gère la recherche de produits"""
    try:
        search_criteria = extraction.get("search_criteria", {})
        category = search_criteria.get("category", "")
        characteristics = search_criteria.get("characteristics", [])
        
        # Ici, appeler votre système de recherche de produits
        # Pour l'exemple, on retourne une réponse structurée
        
        return {
            "type": "product_search",
            "message": f"🔍 Recherche de {category} avec les caractéristiques: {', '.join(characteristics)}",
            "suggestions": [
                "Voir les résultats",
                "Affiner la recherche",
                "Créer un devis avec ces produits"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche produit: {str(e)}")
        return {
            "type": "error",
            "message": "❌ Erreur lors de la recherche de produits",
            "suggestions": ['Réessayer', 'Reformuler la recherche']
        }

async def _handle_client_info(extraction: Dict[str, Any]) -> Dict[str, Any]:
    """Gère les demandes d'information client"""
    try:
        client_name = extraction.get("client", "")
        
        return {
            "type": "client_info",
            "message": f"👤 Recherche d'informations pour le client: {client_name}",
            "suggestions": [
                "Voir le profil complet",
                "Historique des commandes",
                "Créer un devis pour ce client"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur info client: {str(e)}")
        return {
            "type": "error",
            "message": "❌ Erreur lors de la récupération des informations client",
            "suggestions": ['Réessayer', 'Vérifier le nom du client']
        }

async def _handle_stock_query(extraction: Dict[str, Any]) -> Dict[str, Any]:
    """Gère les consultations de stock"""
    try:
        return {
            "type": "stock_query",
            "message": "📦 Consultation du stock en cours...",
            "suggestions": [
                "Voir le stock détaillé",
                "Alertes stock faible",
                "Commander des produits"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur consultation stock: {str(e)}")
        return {
            "type": "error",
            "message": "❌ Erreur lors de la consultation du stock",
            "suggestions": ['Réessayer', 'Contacter le responsable stock']
        }

async def get_unified_data(data_type: str, limit: int = 20):
    """Service unifié pour récupérer clients et produits"""
    try:
        if data_type == "clients":
            # Appel direct au MCP
            sf_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": f"SELECT Id, Name, Phone, BillingCity, BillingCountry, Type, Industry, AccountNumber FROM Account LIMIT {safe_int(limit, default=10, max_value=100)}"
            })
            
            if "error" not in sf_result:
                return {
                    'clients': sf_result.get('records', []),
                    'total': sf_result.get('totalSize', 0)
                }
                
        elif data_type == "products":
            # Appel direct au MCP
            sap_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$top={limit}",
                "method": "GET"
            })
            
            if "error" not in sap_result:
                return {
                    'products': sap_result.get('value', []),
                    'total': len(sap_result.get('value', []))
                }
                
        return {'clients': [], 'products': [], 'total': 0}

    except Exception as e:
        logger.error(f"Erreur get_unified_data: {e}")
        return {'clients': [], 'products': [], 'total': 0}


async def get_workflow_context(task_id: str) -> Dict[str, Any]:
    """Récupère le contexte de workflow persisté pour une tâche.

    Mécanisme de persistance réel = la QuoteTask du progress_tracker :
      - `task.context` (alimenté par DevisWorkflow._save_context_to_task) porte
        `extracted_info` (et donc `products`) ;
      - `task.task_id` et `task.user_prompt` portent l'identifiant et le prompt
        d'origine.
    Le consommateur produit `apply_product_suggestions` (devis_workflow:1604)
    attend `extracted_info.products`, `extracted_info.original_prompt` et
    `task_id` au niveau racine. On reconstitue donc un contexte complet à partir
    de la tâche persistée (et non le seul `task.context` brut).
    Retourne un dict vide si la tâche n'existe pas / a expiré.
    """
    task = progress_tracker.get_task(task_id)
    if not task:
        return {}
    context = dict(getattr(task, "context", {}) or {})
    context.setdefault("task_id", getattr(task, "task_id", task_id))
    extracted_info = dict(context.get("extracted_info") or {})
    extracted_info.setdefault("original_prompt", getattr(task, "user_prompt", "") or "")
    context["extracted_info"] = extracted_info
    return context
logger = logging.getLogger(__name__)

# Modèles Pydantic
class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    success: bool
    response: Optional[Dict[str, Any]] = None
    intent: Optional[Dict[str, Any]] = None
    conversation_id: Optional[int] = None
    error: Optional[str] = None

# ✅ CLASSE MANQUANTE - AssistantRequest
class AssistantRequest(BaseModel):
    """Requête générique pour l'assistant intelligent"""
    message: str = Field(..., description="Message de l'utilisateur")
    context: Optional[Dict[str, Any]] = Field(None, description="Contexte de conversation")
    session_id: Optional[str] = Field(None, description="ID de session")
    draft_mode: Optional[bool] = Field(False, description="Mode brouillon")
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message vide non autorisé')
        return v.strip()

class AssistantResponse(BaseModel):
    """Réponse de l'assistant intelligent"""
    success: bool
    message: str
    response_type: str = "text"
    data: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None
    error: Optional[str] = None
    conversation_id: Optional[str] = None
# Router pour l'assistant intelligent
# router = APIRouter(prefix="/api/assistant", tags=["Assistant Intelligent"])  # Déjà défini plus haut

# Instances des services
suggestion_engine = SuggestionEngine()
client_validator = ClientValidator()
progress_tracker = ProgressTracker()

class ConversationManager:
    """Gestionnaire de conversation intelligente avec NOVA"""
    
    def __init__(self):
        self.conversation_history = []
        self.current_context = {}
        self.user_preferences = {}
    
    def analyze_intent(self, user_message: str) -> Dict[str, Any]:
        """Analyse l'intention de l'utilisateur avec logique améliorée"""
        message_lower = user_message.lower()
        
        # Patterns d'intention - avec priorité aux patterns spécifiques
        intent_patterns = {
            'find_client': ['rechercher client', 'chercher client', 'trouver client', 'client chercher', 'client', 'chercher', 'trouver', 'recherche'],
            'find_product': ['rechercher produit', 'chercher produit', 'trouver produit', 'produit chercher', 'produit', 'référence', 'article', 'stock'],
            'create_quote': ['créer devis', 'nouveau devis', 'faire devis', 'génération devis', 'devis', 'créer', 'nouveau', 'génération', 'quote'],
            'help': ['aide', 'help', 'comment', 'expliquer'],
            'status': ['statut', 'état', 'progression', 'avancement'],
            'greeting': ['bonjour', 'salut', 'hello', 'bonsoir']
        }
        
        # Détecter l'intention avec priorité aux patterns longs
        detected_intent = None
        max_match_length = 0
        
        for intent, keywords in intent_patterns.items():
            for keyword in keywords:
                if keyword in message_lower:
                    # Priorité aux patterns plus longs (plus spécifiques)
                    if len(keyword.split()) > max_match_length:
                        max_match_length = len(keyword.split())
                        detected_intent = intent
                        break
        
        return {
            'primary_intent': detected_intent if detected_intent else 'unknown',
            'all_intents': [detected_intent] if detected_intent else [],
            'confidence': 0.8 if detected_intent else 0.2,
            'entities': self._extract_entities(user_message)
        }
    
    def _extract_entities(self, message: str) -> Dict[str, List[str]]:
        """Extrait les entités du message (noms, références, etc.)"""
        import re
        
        entities = {
            'client_names': [],
            'product_refs': [],
            'quantities': [],
            'dates': []
        }
        
        # Extraction des références produits (format A00XXX, B00XXX, etc.)
        product_refs = re.findall(r'\b[A-Z]\d{5}\b', message)
        entities['product_refs'] = product_refs
        
        # Extraction des quantités - plus flexible
        quantities = []
        
        # 1. Nombres avec unités explicites
        qty_with_units = re.findall(r'\b(\d+)\s*(?:pièces?|unités?|pc|u)\b', message, re.IGNORECASE)
        quantities.extend([int(q) for q in qty_with_units])
        
        # 2. Patterns spécifiques pour les quantités
        qty_patterns = [
            r'\b(\d+)\s+ref\b',  # "500 ref"
            r'\bquantité\s+(\d+)\b',  # "quantité 25"
            r'\b(\d+)\s+[A-Z]\d{5}\b',  # "100 A00025"
        ]
        
        for pattern in qty_patterns:
            matches = re.findall(pattern, message, re.IGNORECASE)
            quantities.extend([int(q) for q in matches])
        
        # 3. Nombres isolés (probablement des quantités) - plus restrictif
        isolated_numbers = re.findall(r'\b(\d{1,4})\b', message)
        for num in isolated_numbers:
            num_int = int(num)
            # Considérer comme quantité si entre 1 et 9999 et pas déjà détecté
            if 1 <= num_int <= 9999 and num_int not in quantities:
                # Vérifier que ce n'est pas une référence produit
                if not re.search(rf'[A-Z]\d{{5}}.*{num}|{num}.*[A-Z]\d{{5}}', message):
                    quantities.append(num_int)
        
        # Supprimer les doublons et trier
        entities['quantities'] = sorted(list(set(quantities)))
        
        # Extraction des noms de clients - amélioration
        client_names = []
        
        # 1. Patterns explicites avec mots-clés
        explicit_patterns = [
            r'(?:client|pour le client|société|entreprise)\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\.|\n)',
            r'\bpour\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',  # "pour Edge Communications"
        ]
        
        for pattern in explicit_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                clean_name = match.strip()
                if clean_name and clean_name not in client_names:
                    # Vérifier que ce n'est pas une référence produit
                    if not re.match(r'^[A-Z]\d{5}$', clean_name):
                        client_names.append(clean_name)
        
        # 2. Noms propres composés (seulement si pas déjà trouvés)
        if not client_names:
            compound_names = re.findall(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b', message)
            for name in compound_names:
                if name not in client_names:
                    # Vérifier que ce n'est pas un mot commun
                    common_words = ['edge communications', 'microsoft corp', 'nouveau devis', 'pour client']
                    if name.lower() not in common_words:
                        client_names.append(name)
        
        # 3. Filtrer les mots communs et références
        filtered_names = []
        for name in client_names:
            # Exclure les mots communs et références produits
            if (name.lower() not in ['devis', 'pour', 'avec', 'dans', 'sur', 'client', 'produit', 'ref', 'nouveau'] and
                not re.match(r'^[A-Z]\d{5}$', name) and  # Pas une référence produit
                len(name) > 2):  # Au moins 3 caractères
                filtered_names.append(name)
        
        entities['client_names'] = filtered_names
        
        return entities

conversation_manager = ConversationManager()

@router.post('/chat', response_model=ChatResponse)
async def chat_with_nova(message_data: ChatMessage):
    """
    🤖 Endpoint principal pour converser avec NOVA
    """
    try:
        user_message = message_data.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message vide")
        
        # Analyser l'intention
        intent_analysis = conversation_manager.analyze_intent(user_message)
        
        # ✅ NOUVELLE LOGIQUE - Détection automatique des devis
        if detect_workflow_request(user_message):
            logger.info(f"🎯 Demande de devis détectée automatiquement: {user_message}")
            
            try:
                # Lancer directement le workflow de création
                
                # Mode production (pas draft) pour créer réellement le devis
                workflow = DevisWorkflow(
                    validation_enabled=True,
                    draft_mode=False,
                    force_production=True  # 🔥 FORCER LE MODE PRODUCTION
                )
                
                # Exécuter le workflow avec le message complet
                workflow_result = await workflow.process_prompt(user_message)
                
                if workflow_result.get('success'):
                    response = {
                        'type': 'quote_created',
                        'message': f"✅ **Devis créé avec succès !**\n\n📋 **Référence :** {workflow_result.get('quote_id', 'N/A')}\n💰 **Montant :** {workflow_result.get('total_amount', 'N/A')}€\n🏢 **Client :** {workflow_result.get('client_name', 'N/A')}",
                        'quote_data': workflow_result,
                        'suggestions': ["Voir le devis", "Créer un nouveau devis", "Modifier ce devis"]
                    }
                else:
                    # Si échec, proposer des alternatives
                    error_msg = workflow_result.get('message', 'Erreur inconnue')
                    response = {
                        'type': 'quote_error',
                        'message': f"❌ **Impossible de créer le devis**\n\n{error_msg}\n\n💡 **Que faire ?**\n• Vérifier les informations\n• Créer le client s'il n'existe pas\n• Utiliser l'interface classique",
                        'suggestions': ["Interface classique", "Créer le client", "Réessayer"]
                    }
                
                # Sauvegarder dans l'historique
                conversation_manager.conversation_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'user_message': user_message,
                    'intent': intent_analysis,
                    'nova_response': response
                })
                
                return ChatResponse(
                    success=True,
                    response=response,
                    intent=intent_analysis,
                    conversation_id=len(conversation_manager.conversation_history)
                )
                    
            except Exception as e:
                logger.error(f"Erreur workflow automatique: {e}")
                response = {
                    'type': 'system_error',
                    'message': f"⚠️ **Erreur système**\n\n{str(e)}\n\nUtilisez l'interface classique pour créer votre devis.",
                    'suggestions': ["Interface classique", "Aide"]
                }
                
                return ChatResponse(
                    success=True,
                    response=response,
                    intent=intent_analysis,
                    conversation_id=len(conversation_manager.conversation_history)
                )
        
        # Générer la réponse selon l'intention (logique existante)
        response = await generate_intelligent_response(user_message, intent_analysis)
        
        # Sauvegarder dans l'historique
        conversation_manager.conversation_history.append({
            'timestamp': datetime.now().isoformat(),
            'user_message': user_message,
            'intent': intent_analysis,
            'nova_response': response
        })
        
        return ChatResponse(
            success=True,
            response=response,
            intent=intent_analysis,
            conversation_id=len(conversation_manager.conversation_history)
        )
        
    except Exception as e:
        logger.error(f"Erreur dans chat_with_nova: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")

async def generate_intelligent_response(message: str, intent: Dict[str, Any]) -> Dict[str, Any]:
    """Génère une réponse intelligente basée sur l'intention détectée"""
    
    primary_intent = intent['primary_intent']
    entities = intent['entities']
    
    if primary_intent == 'greeting':
        return {
            'type': 'greeting',
            'message': "👋 Bonjour ! Je suis NOVA, votre assistant intelligent pour la génération de devis.\n\n💡 **Je peux vous aider à :**\n• Créer des devis automatiquement\n• Trouver des clients et produits\n• Valider des informations\n• Proposer des solutions intelligentes\n\n🚀 **Dites-moi simplement ce que vous voulez faire !**",
            'suggestions': [
                "Créer un nouveau devis",
                "Chercher un client",
                "Voir les produits disponibles"
            ],
            'quick_actions': [
                {'label': '📝 Nouveau Devis', 'action': 'new_quote'},
                {'label': '👥 Clients', 'action': 'show_clients'},
                {'label': '📦 Produits', 'action': 'show_products'}
            ]
        }
    
    elif primary_intent == 'create_quote':
        return handle_quote_creation_intent(message, entities)
    
    elif primary_intent == 'find_client':
        return await handle_client_search_intent(message, entities)
    
    elif primary_intent == 'find_product':
        return await handle_product_search_intent(message, entities)
    
    elif primary_intent == 'help':
        return {
            'type': 'help',
            'message': "🆘 **Guide d'utilisation NOVA**\n\n**Exemples de demandes :**\n• \"Créer un devis pour Edge Communications\"\n• \"Chercher le client Acme Corp\"\n• \"Produit A00025 disponible ?\"\n• \"Nouveau devis avec 10 ordinateurs\"\n\n**Fonctionnalités intelligentes :**\n✅ Correction automatique des noms\n✅ Suggestions proactives\n✅ Validation en temps réel\n✅ Détection des doublons",
            'suggestions': [
                "Créer un devis pour [nom client]",
                "Chercher le produit [référence]",
                "Voir mes devis en cours"
            ]
        }
    
    else:
        # Intention inconnue - Proposer des suggestions intelligentes
        return {
            'type': 'suggestion',
            'message': f"🤔 Je n'ai pas bien compris votre demande : \"{message}\"\n\n💡 **Voulez-vous peut-être :**",
            'suggestions': [
                "Créer un nouveau devis",
                "Rechercher un client ou produit",
                "Voir l'aide complète"
            ],
            'quick_actions': [
                {'label': '📝 Créer Devis', 'action': 'new_quote'},
                {'label': '🔍 Rechercher', 'action': 'search'},
                {'label': '❓ Aide', 'action': 'help'}
            ]
        }

def handle_quote_creation_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de création de devis en utilisant le workflow existant"""
    
    try:
        # Importer le workflow de devis existant
        
        response = {
            'type': 'quote_creation',
            'message': "📝 **Création de devis intelligente**\n\n",
            'suggestions': [],
            'workflow_action': 'create_quote'
        }
        
        # Utiliser le workflow existant pour analyser le message
        workflow = DevisWorkflow(
            validation_enabled=True,
            draft_mode=False,
            force_production=True  # 🔥 FORCER LE MODE PRODUCTION
        )
        
        # Le workflow peut analyser le message directement
        response['message'] += f"🔍 **Analyse de votre demande :**\n"
        response['message'] += f"'{message}'\n\n"
        
        # Proposer d'utiliser le workflow complet
        response['message'] += "🚀 **Options disponibles :**\n"
        response['message'] += "1. 📝 Créer le devis avec le workflow complet\n"
        response['message'] += "2. 🔍 Analyser d'abord les informations\n"
        response['message'] += "3. 💼 Ouvrir l'interface classique\n\n"
        
        response['suggestions'] = [
            "Créer le devis maintenant",
            "Analyser les informations",
            "Interface classique"
        ]
        
        # Actions rapides pour le workflow
        response['quick_actions'] = [
            {'label': '🚀 Créer Devis', 'action': 'start_workflow', 'data': {'message': message}},
            {'label': '🔍 Analyser', 'action': 'analyze_request', 'data': {'message': message}},
            {'label': '💼 Interface', 'action': 'open_classic'}
        ]
        
        return response
        
    except ImportError as e:
        logger.error(f"Erreur import workflow: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur workflow**\n\nImpossible de charger le workflow de devis.\n\n💡 **Solution :** Utilisez l'interface classique pour créer vos devis.",
            'suggestions': ["Ouvrir l'interface classique", "Contacter le support"]
        }
    except Exception as e:
        logger.error(f"Erreur création devis: {e}")
        return {
            'type': 'error', 
            'message': f"❌ **Erreur inattendue**\n\n{str(e)}",
            'suggestions': ["Réessayer", "Interface classique"]
        }

async def handle_client_search_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de recherche de client avec recherche google-like"""
    
    client_names = entities.get('client_names', [])
    
    if not client_names:
        return {
            'type': 'client_search_prompt',
            'message': "🔍 **Recherche Google-Like Client**\n\n**Tapez le nom du client à rechercher :**\n\n💡 **Exemples :**\n• \"Microsoft\"\n• \"Orange\"\n• \"Air France\"\n\nJe rechercherai automatiquement et proposerai des suggestions.",
            'suggestions': [
                "Tous les clients",
                "Créer nouveau client"
            ],
            'enable_search_mode': True
        }
    
    # Recherche intelligente avec les vraies données
    try:
        search_term = client_names[0]
        logger.info(f"🔍 Recherche google-like pour client: '{search_term}'")
        
        response = {
            'type': 'client_search_results',
            'message': f"🔍 **Résultats pour '{search_term}'**\n\n",
            'suggestions': []
        }

        # Recherche client unifiée (Salesforce via MCP), filtrée sur le terme et
        # normalisée au format attendu par l'affichage ci-dessous.
        raw_clients = await get_unified_data("clients")
        matches = []
        for rec in raw_clients.get('clients', []):
            rec_name = (rec.get('Name') or rec.get('name') or '')
            if search_term.lower() in rec_name.lower():
                location = ', '.join(p for p in [rec.get('BillingCity', ''), rec.get('BillingCountry', '')] if p)
                matches.append({
                    'id': rec.get('Id', rec.get('id', '')),
                    'name': rec_name,
                    'industry': rec.get('Industry', rec.get('industry', '')),
                    'location_display': location,
                })
        clients_data = {'success': bool(matches), 'clients': matches}

        if clients_data.get('success') and clients_data.get('clients'):
            # Clients trouvés - affichage google-like
            found_clients = clients_data['clients'][:5]  # Max 5 résultats
            
            response['message'] += f"✅ **{len(found_clients)} résultat(s) trouvé(s) :**\n\n"
            
            for i, client in enumerate(found_clients, 1):
                client_name = client.get('name', 'Client sans nom')
                location = client.get('location_display', '')
                industry = client.get('industry', '')
                
                response['message'] += f"**{i}. {client_name}**\n"
                if location:
                    response['message'] += f"   📍 {location}\n"
                if industry:
                    response['message'] += f"   🏭 {industry}\n"
                response['message'] += f"   🆔 ID: {client.get('id', 'N/A')}\n\n"
            
            # Suggestions d'actions
            response['suggestions'] = [
                f"Utiliser {found_clients[0]['name']}",
                "Affiner la recherche",
                f"Créer '{search_term}'" if search_term.lower() not in [c['name'].lower() for c in found_clients] else "Nouveau client"
            ]
            
            if len(clients_data['clients']) > 5:
                response['message'] += f"... et {len(clients_data['clients']) - 5} autres résultats.\n\n"
                response['suggestions'].append("Voir tous les résultats")
                
        else:
            # Aucun client trouvé - proposer création
            response['message'] += f"❌ **Aucun client trouvé pour '{search_term}'**\n\n"
            response['message'] += "💡 **Que souhaitez-vous faire ?**\n\n"
            response['message'] += f"1. 🆕 **Créer le client '{search_term}'**\n"
            response['message'] += "2. 🔍 **Essayer une autre recherche**\n"
            response['message'] += "3. 👥 **Voir tous les clients disponibles**\n"
            
            response['suggestions'] = [
                f"Créer '{search_term}'",
                "Nouvelle recherche", 
                "Tous les clients"
            ]
            response['create_option'] = {
                'client_name': search_term,
                'action': 'create_client'
            }
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur recherche client google-like: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur lors de la recherche**\n\n{str(e)}\n\nVoulez-vous essayer une recherche manuelle ?",
            'suggestions': [
                "Nouvelle recherche",
                "Tous les clients",
                f"Créer '{client_names[0] if client_names else 'nouveau client'}'"
            ]
        }

async def handle_product_search_intent(message: str, entities: Dict[str, Any]) -> Dict[str, Any]:
    """Gère l'intention de recherche de produit avec recherche google-like"""

    product_refs = entities.get('product_refs', [])

    if not product_refs:
        return {
            'type': 'product_search_prompt',
            'message': "🔍 **Recherche Google-Like Produit**\n\n**Tapez la référence ou le nom du produit à rechercher :**\n\n💡 **Exemples :**\n• \"A00025\"\n• \"Connecteur USB\"\n• \"Cable HDMI\"\n\nJe rechercherai automatiquement et proposerai des suggestions.",
            'suggestions': [
                "Tous les produits",
                "Créer nouveau produit"
            ],
            'enable_search_mode': True
        }

    # Recherche intelligente avec les vraies données
    try:
        search_term = product_refs[0]
        logger.info(f"🔍 Recherche google-like pour produit: '{search_term}'")

        # Appel direct à la fonction Python (P5-M4 : remplace l'appel HTTP self-loop
        # qui créait un nouvel event loop dans un contexte sync — antipattern).
        from routes.routes_products import search_products_advanced
        products_data = await search_products_advanced(q=search_term, limit=10)
        
        response = {
            'type': 'product_search_results',
            'message': f"🔍 **Résultats pour '{search_term}'**\n\n",
            'suggestions': []
        }
        
        if products_data.get('success') and products_data.get('products'):
            # Produits trouvés - affichage google-like
            found_products = products_data['products'][:5]  # Max 5 résultats
            
            response['message'] += f"✅ **{len(found_products)} résultat(s) trouvé(s) :**\n\n"
            
            for i, product in enumerate(found_products, 1):
                product_code = product.get('ItemCode', 'Sans référence')
                product_name = product.get('ItemName', 'Sans nom')
                product_price = product.get('UnitPrice', 0)
                product_stock = product.get('StockQuantity', 0)
                
                response['message'] += f"**{i}. {product_code} - {product_name}**\n"
                if product_price > 0:
                    response['message'] += f"   💰 Prix: {product_price:.2f}€ HT\n"
                response['message'] += f"   📦 Stock: {product_stock} unités\n"
                response['message'] += f"   🆔 Code: {product_code}\n\n"
            
            # Suggestions d'actions
            best_product = found_products[0]
            response['suggestions'] = [
                f"Utiliser {best_product['ItemCode']}",
                "Affiner la recherche",
                f"Créer '{search_term}'" if search_term.upper() not in [p['ItemCode'].upper() for p in found_products] else "Nouveau produit"
            ]
            
            if len(products_data['products']) > 5:
                response['message'] += f"... et {len(products_data['products']) - 5} autres résultats.\n\n"
                response['suggestions'].append("Voir tous les résultats")
                
        else:
            # Aucun produit trouvé - proposer création
            response['message'] += f"❌ **Aucun produit trouvé pour '{search_term}'**\n\n"
            response['message'] += "💡 **Que souhaitez-vous faire ?**\n\n"
            response['message'] += f"1. 🆕 **Créer le produit '{search_term}'**\n"
            response['message'] += "2. 🔍 **Essayer une autre recherche**\n"
            response['message'] += "3. 📦 **Voir tous les produits disponibles**\n"
            response['message'] += "4. 📞 **Contacter le support pour vérifier la référence**\n"
            
            response['suggestions'] = [
                f"Créer '{search_term}'",
                "Nouvelle recherche", 
                "Tous les produits",
                "Contacter support"
            ]
            response['create_option'] = {
                'product_ref': search_term,
                'action': 'create_product'
            }
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur recherche produit google-like: {e}")
        return {
            'type': 'error',
            'message': f"❌ **Erreur lors de la recherche**\n\n{str(e)}\n\nVoulez-vous essayer une recherche manuelle ?",
            'suggestions': [
                "Nouvelle recherche",
                "Tous les produits",
                f"Créer '{product_refs[0] if product_refs else 'nouveau produit'}'"
            ]
        }

@router.get('/suggestions/{suggestion_type}')
async def get_contextual_suggestions(suggestion_type: str):
    """Endpoint pour obtenir des suggestions contextuelles"""
    try:
        if suggestion_type == 'clients':
            clients_data = await get_unified_data("clients")
            return {
                'success': True,
                'suggestions': clients_data.get('clients', [])[:10]  # Top 10
            }

        elif suggestion_type == 'products':
            products_data = await get_unified_data("products")
            return {
                'success': True,
                'suggestions': products_data.get('products', [])[:10]  # Top 10
            }
        
        else:
            raise HTTPException(status_code=400, detail="Type de suggestion non supporté")
            
    except Exception as e:
        logger.error(f"Erreur suggestions contextuelles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/conversation/history')
async def get_conversation_history():
    """Récupère l'historique de conversation"""
    return {
        'success': True,
        'history': conversation_manager.conversation_history[-10:]  # 10 derniers
    }

@router.post('/conversation/clear')
async def clear_conversation():
    """Efface l'historique de conversation"""
    conversation_manager.conversation_history.clear()
    conversation_manager.current_context.clear()
    
    return {
        'success': True,
        'message': 'Historique effacé'
    }

# Route pour servir l'interface intelligente
@router.get('/interface', response_class=HTMLResponse)
async def intelligent_interface():
    """Sert l'interface de l'assistant intelligent"""
    try:
        with open('templates/intelligent_assistant.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read( media_type="text/html; charset=utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Interface non trouvée")

@router.get("/clients/list")
async def get_clients_list():
    """Endpoint pour récupérer la liste complète des clients"""
    try:
        # Récupération des clients via MCP
        clients_data = await get_unified_data("clients")
        # Normaliser les clés pour l'interface
        for client in clients_data.get('clients', []):
            client['name'] = client.get('Name', client.get('name', ''))
            client['type'] = client.get('Type', client.get('type', ''))
            client['industry'] = client.get('Industry', client.get('industry', ''))
            client['phone'] = client.get('Phone', client.get('phone', ''))
        clients = clients_data.get('clients', [])
        
        # Formatage pour affichage
        formatted_clients = []
        for client in clients[:15]:  # Limiter à 15 pour l'affichage
            formatted_client = f"**{client.get('name', 'Client sans nom')}**"
            details = []
            if client.get('type'):
                details.append(f"Type: {client['type']}")
            if client.get('industry'):
                details.append(f"Secteur: {client['industry']}")
            if client.get('phone'):
                details.append(f"Tél: {client['phone']}")
            if client.get('city'):
                details.append(f"Ville: {client['city']}")
            if client.get('country'):
                details.append(f"Pays: {client['country']}")
            
            if details:
                formatted_client += f" - {' | '.join(details)}"
            formatted_clients.append(formatted_client)
        
        total_clients = len(clients)
        message = f"🔍 **{len(formatted_clients)} clients trouvés** (sur {total_clients} total)"
        
        return {
            "success": True,
            "clients": formatted_clients,
            "total": total_clients,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Erreur endpoint clients/list: {e}")
        return {
            "success": False,
            "clients": [],
            "total": 0,
            "message": f"❌ Erreur lors de la récupération des clients: {str(e)}"
        }

@router.get("/products/list")
async def get_products_list():
    """Récupère la liste complète des produits"""
    try:
        # Récupération des produits via MCP
        products_data = await get_unified_data("products")
        products = products_data.get('products', [])
        
        # Formater les produits pour l'affichage
        formatted_products = []
        for product in products:
            formatted_product = {
                'code': product.get('code', product.get('Code', '')),
                'name': product.get('name', product.get('Name', 'Produit sans nom')),
                'description': product.get('description', product.get('Description', '')),
                'price': product.get('price', product.get('Price', 0)),
                'currency': product.get('currency', product.get('Currency', 'EUR')),
                'stock': product.get('stock', product.get('Stock', 0)),
                'category': product.get('category', product.get('Category', 'Général'))
            }
            formatted_products.append(formatted_product)
        
        return {
            'success': True,
            'products': formatted_products,
            'total': len(formatted_products),
            'message': f"🛍️ **{len(formatted_products)} produits trouvés** (sur {len(formatted_products)} total)"
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération liste produits: {e}")
        return {
            'success': False,
            'products': [],
            'total': 0,
            'error': str(e),
            'message': "❌ **Erreur lors de la récupération des produits**"
        }
@router.post("/choice")
async def handle_user_choice(choice_data: Dict[str, Any]):
    """
    🔧 GESTION DES CHOIX UTILISATEUR DEPUIS L'INTERFACE
    """
    try:
        choice_type = choice_data.get("type")
        task_id = choice_data.get("task_id")

        if not task_id:
            raise HTTPException(status_code=400, detail="task_id manquant")

        # Récupérer le contexte du workflow
        workflow_context = await get_workflow_context(task_id)

        if choice_type == "client_choice":
            # ⚠️ Branche CLIENT NON IMPLÉMENTÉE : workflow.handle_client_suggestions
            # n'existe pas (chantier séparé à spécifier — voir aussi
            # client_workflow_choice_endpoint et continue_workflow_with_choice).
            raise HTTPException(
                status_code=501,
                detail="Sélection client via suggestions non implémentée "
                       "(handle_client_suggestions absent — chantier séparé)"
            )

        elif choice_type == "product_choice":
            # Choix produit depuis les alternatives
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow.apply_product_suggestions(choice_data.get("products", []), workflow_context)

        elif choice_type == "create_client":
            # Déclenchement création client
            workflow = DevisWorkflow(task_id=task_id, force_production=True)
            result = await workflow._handle_new_client_creation(
                choice_data.get("client_name", ""),
                workflow_context
            )

        else:
            raise HTTPException(status_code=400, detail=f"Type de choix '{choice_type}' non supporté")

        return result

    except HTTPException:
        # Préserver les codes explicites (400/501) sans les convertir en 500.
        raise
    except Exception as e:
        logger.error(f"Erreur gestion choix utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Import du workflow de création de client

# Modèles pour la création de client
class ClientSearchRequest(BaseModel):
    company_name: Optional[str] = None
    city: Optional[str] = None
    siret: Optional[str] = None

class ClientCreationRequest(BaseModel):
    siret: str
    additional_data: Optional[Dict[str, Any]] = {}

@router.post('/client/search')
async def search_companies(request: ClientSearchRequest):
    """
    🔍 Recherche d'entreprises par nom ou SIRET via INSEE/Pappers
    """
    try:
        logger.info(f"🔍 Recherche entreprise: {request.company_name or request.siret}")

        if request.siret:
            # Validation directe par SIRET
            result = await client_creation_workflow.validate_and_enrich_company(request.siret)
            if result.get("success"):
                return {
                    "success": True,
                    "companies": [result["company_data"]],
                    "search_method": "siret_validation",
                    "message": "Entreprise trouvée et validée"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                    "message": result.get("message")
                }
        else:
            # Recherche par nom
            result = await client_creation_workflow.search_company_by_name(
                request.company_name,
                request.city
            )
            return result

    except Exception as e:
        logger.error(f"Erreur recherche entreprise: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur lors de la recherche"
        }

@router.post('/client/create')
async def create_client(request: ClientCreationRequest):
    """
    🏢 Création d'un nouveau client dans Salesforce
    """
    try:
        logger.info(f"🏢 Création client SIRET: {request.siret}")

        # Valider et enrichir les données
        validation_result = await client_creation_workflow.validate_and_enrich_company(request.siret)

        if not validation_result.get("success"):
            return {
                "success": False,
                "error": validation_result.get("error"),
                "message": validation_result.get("message")
            }

        # Fusionner avec les données additionnelles
        company_data = validation_result["company_data"]
        company_data.update(request.additional_data)

        # Créer le client
        creation_result = await client_creation_workflow.create_client_in_salesforce(company_data)

        return creation_result

    except Exception as e:
        logger.error(f"Erreur création client: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur lors de la création du client"
        }

@router.post('/client/workflow')
async def client_creation_workflow_endpoint(request: Dict[str, Any]):
    """
    🚀 Workflow complet de création de client
    """
    try:
        logger.info("🚀 Démarrage workflow création client")
        result = await client_creation_workflow.process_client_creation_request(request)
        return result
    except Exception as e:
        logger.error(f"Erreur workflow création client: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Erreur dans le workflow de création"
        }
@router.post('/client/workflow/choice')
async def client_workflow_choice_endpoint(choice_data: Dict[str, Any]):
    """
    🔧 GESTION DES CHOIX UTILISATEUR DEPUIS L'INTERFACE
    """
    try:
        choice_type = choice_data.get("type")
        task_id = choice_data.get("task_id")

        if not task_id:
            raise HTTPException(status_code=400, detail="task_id manquant")

        # Récupérer le contexte du workflow
        workflow_context = await get_workflow_context(task_id)

        if choice_type == "client_choice":
            # ⚠️ Branche CLIENT NON IMPLÉMENTÉE : workflow.handle_client_suggestions
            # n'existe pas (chantier séparé à spécifier).
            raise HTTPException(
                status_code=501,
                detail="Sélection client via suggestions non implémentée "
                       "(handle_client_suggestions absent — chantier séparé)"
            )

        workflow = DevisWorkflow(task_id=task_id, force_production=True)

        if choice_type == "product_choice":
            # Choix produit depuis les alternatives
            result = await workflow.apply_product_suggestions(
                choice_data.get("products", []),
                workflow_context
            )

        elif choice_type == "create_client":
            # Déclenchement création client
            result = await workflow._handle_new_client_creation(
                choice_data.get("client_name", ""),
                workflow_context
            )

        else:
            raise HTTPException(status_code=400, detail=f"Type de choix '{choice_type}' non supporté")

        return result

    except HTTPException:
        # Préserver les codes explicites (400/501) sans les convertir en 500.
        raise
    except Exception as e:
        logger.error(f"Erreur gestion choix utilisateur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Modèles pour la création de client
class ClientCreationRequest(BaseModel):
    company_name: str
    city: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

class ClientCreationFromCompanyRequest(BaseModel):
    company_data: Dict[str, Any]
    contact_info: Optional[Dict[str, Any]] = None

@router.post('/create_client/search')
async def search_company_for_creation(request: ClientCreationRequest):
    """
    🔍 Recherche d'entreprise pour création de client
    """
    try:

        workflow = ClientCreationWorkflow()

        # Rechercher les informations de l'entreprise
        search_results = await workflow.search_company_by_name(
            request.company_name,
            request.city
        )

        # Remap vers le contrat de sortie déclaré {search_results, recommended, sources}
        companies = search_results.get('companies', [])

        return {
            'success': True,
            'company_name': request.company_name,
            'city': request.city,
            'contact_name': request.contact_name,
            'search_results': companies,
            'recommended': None,
            'sources': [],
            'message': f"Trouvé {len(companies)} résultat(s) pour '{request.company_name}'"
        }

    except Exception as e:
        logger.error(f"Erreur recherche entreprise: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors de la recherche: {str(e)}"
        }

@router.post('/create_client/confirm')
async def create_client_from_company(request: ClientCreationFromCompanyRequest):
    """
    ✅ Création de client à partir des données d'entreprise sélectionnées
    """
    try:

        workflow = ClientCreationWorkflow()

        # Fusionner données entreprise + infos de contact (champs additifs compatibles)
        client_data = {**request.company_data, **(request.contact_info or {})}

        # Créer le client
        creation_result = await workflow.create_client_in_salesforce(client_data)

        return creation_result

    except Exception as e:
        logger.error(f"Erreur création client: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors de la création: {str(e)}"
        }

@router.post('/create_client/from_text')
async def create_client_from_text(request: Dict[str, str]):
    """
    📝 Création de client à partir d'une demande en texte libre
    """
    try:

        workflow = ClientCreationWorkflow()

        # 🔧 CORRECTION: Extraire les informations structurées depuis le texte
        user_text = request.get('text', '').strip()

        if not user_text:
            return {
                'success': False,
                'error': 'Texte de demande requis',
                'message': 'Veuillez fournir une description du client à créer'
            }

        # Utiliser le LLM pour extraire les informations client
        llm_extractor = LLMExtractor()
        extracted_info = await llm_extractor.extract_client_info_from_text(user_text)

        if not extracted_info.get('success'):
            return {
                'success': False,
                'error': 'Extraction impossible',
                'message': 'Impossible d\'extraire les informations client du texte fourni',
                'details': extracted_info.get('error', 'Erreur inconnue')
            }

        # Traiter la demande avec les données structurées
        client_data = extracted_info.get('client_data', {})
        result = await workflow.process_client_creation_request(client_data)

        # 🆕 FALLBACK: Si l'API Sirene échoue, proposer la saisie manuelle
        if not result.get('success') and 'api' in result.get('error', '').lower():
            logger.warning("🔄 API Sirene indisponible - Activation du fallback saisie manuelle")

            # Retourner les données extraites pour saisie manuelle
            return {
                'success': False,
                'type': 'manual_input_required',
                'message': 'API de validation indisponible - Saisie manuelle requise',
                'extracted_data': client_data,
                'required_fields': [
                    {'name': 'company_name', 'label': 'Nom de l\'entreprise', 'type': 'text', 'required': True, 'value': client_data.get('company_name', '')},
                    {'name': 'contact_name', 'label': 'Nom du contact', 'type': 'text', 'required': False, 'value': client_data.get('contact_name', '')},
                    {'name': 'email', 'label': 'Email', 'type': 'email', 'required': False, 'value': client_data.get('email', '')},
                    {'name': 'phone', 'label': 'Téléphone', 'type': 'tel', 'required': False, 'value': client_data.get('phone', '')},
                    {'name': 'address', 'label': 'Adresse', 'type': 'text', 'required': False, 'value': client_data.get('address', '')},
                    {'name': 'city', 'label': 'Ville', 'type': 'text', 'required': False, 'value': client_data.get('city', '')},
                    {'name': 'postal_code', 'label': 'Code postal', 'type': 'text', 'required': False, 'value': client_data.get('postal_code', '')},
                    {'name': 'siret', 'label': 'SIRET (optionnel)', 'type': 'text', 'required': False, 'value': client_data.get('siret', '')}
                ],
                'fallback_reason': 'API de validation des entreprises temporairement indisponible'
            }

        return result

    except Exception as e:
        logger.error(f"Erreur traitement demande création: {e}")

        # 🆕 FALLBACK GÉNÉRAL: En cas d'erreur système, proposer aussi la saisie manuelle
        if 'api' in str(e).lower() or 'timeout' in str(e).lower() or 'connection' in str(e).lower():
            return {
                'success': False,
                'type': 'manual_input_required',
                'message': 'Service de validation temporairement indisponible - Saisie manuelle requise',
                'extracted_data': {},
                'required_fields': [
                    {'name': 'company_name', 'label': 'Nom de l\'entreprise', 'type': 'text', 'required': True, 'value': ''},
                    {'name': 'contact_name', 'label': 'Nom du contact', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'email', 'label': 'Email', 'type': 'email', 'required': False, 'value': ''},
                    {'name': 'phone', 'label': 'Téléphone', 'type': 'tel', 'required': False, 'value': ''},
                    {'name': 'address', 'label': 'Adresse', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'city', 'label': 'Ville', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'postal_code', 'label': 'Code postal', 'type': 'text', 'required': False, 'value': ''},
                    {'name': 'siret', 'label': 'SIRET (optionnel)', 'type': 'text', 'required': False, 'value': ''}
                ],
                'fallback_reason': 'Erreur de connexion aux services de validation'
            }

        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors du traitement: {str(e)}"
        }

@router.post('/create_client/manual')
async def create_client_manual(request: Dict[str, Any]):
    """
    📝 Création de client avec saisie manuelle (fallback API Sirene)
    """
    try:

        workflow = ClientCreationWorkflow()
        client_data = request.get('client_data', {})

        # Validation des champs obligatoires
        if not client_data.get('company_name', '').strip():
            return {
                'success': False,
                'error': 'Nom d\'entreprise requis',
                'message': 'Le nom de l\'entreprise est obligatoire pour créer un client'
            }

        # Nettoyer et normaliser les données
        normalized_data = {
            'company_name': client_data.get('company_name', '').strip(),
            'contact_name': client_data.get('contact_name', '').strip(),
            'email': client_data.get('email', '').strip(),
            'phone': client_data.get('phone', '').strip(),
            'address': client_data.get('address', '').strip(),
            'city': client_data.get('city', '').strip(),
            'postal_code': client_data.get('postal_code', '').strip(),
            'siret': client_data.get('siret', '').strip(),
            'country': 'FR',  # Par défaut France
            'source': 'manual_input',
            'validation_bypassed': True  # Indique que la validation API a été contournée
        }

        # Validation basique locale (sans API externe)
        validation_errors = []

        # Validation email basique
        if normalized_data['email']:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, normalized_data['email']):
                validation_errors.append("Format d'email invalide")

        # Validation téléphone basique
        if normalized_data['phone']:
            phone_clean = re.sub(r'[^\d+]', '', normalized_data['phone'])
            if len(phone_clean) < 8:
                validation_errors.append("Numéro de téléphone trop court")

        # Validation SIRET basique
        if normalized_data['siret']:
            siret_clean = re.sub(r'[^\d]', '', normalized_data['siret'])
            if len(siret_clean) != 14:
                validation_errors.append("Le SIRET doit contenir exactement 14 chiffres")

        if validation_errors:
            return {
                'success': False,
                'error': 'Données invalides',
                'message': 'Veuillez corriger les erreurs suivantes',
                'validation_errors': validation_errors
            }

        # Créer le client directement dans Salesforce (bypass de la recherche API)
        creation_result = await workflow.create_client_in_salesforce(normalized_data)

        if creation_result.get('success'):
            return {
                'success': True,
                'type': 'client_created_manual',
                'message': 'Client créé avec succès (saisie manuelle)',
                'client_data': normalized_data,
                'client_id': creation_result.get('client_id'),
                'account_number': creation_result.get('account_number'),
                'validation_note': 'Client créé sans validation API externe'
            }
        else:
            return {
                'success': False,
                'error': creation_result.get('error', 'Erreur inconnue'),
                'message': creation_result.get('message', 'Erreur lors de la création du client')
            }

    except Exception as e:
        logger.error(f"Erreur création client manuelle: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Erreur lors de la création manuelle: {str(e)}"
        }

def detect_workflow_request(message: str) -> bool:
    """Détecte si un message nécessite le workflow (devis OU recherche produit)"""
    message_lower = message.lower()
    
    # Mots-clés pour les DEVIS
    quote_triggers = [
        'devis pour', 'créer un devis', 'faire un devis', 'je veux un devis',
        'quote for', 'create quote', 'quotation for',
        'commande pour', 'commander', 'acheter',
        'prix pour', 'tarif pour'
    ]
    
    # 🆕 NOUVEAUX : Mots-clés pour RECHERCHE PRODUIT
    search_triggers = [
        'je cherche', 'recherche', 'trouve', 'trouver',
        'imprimante', 'ordinateur', 'scanner', 'écran',
        'laser', 'jet d\'encre', 'recto-verso', 'réseau',
        'ppm', 'caractéristiques', 'spécifications'
    ]
    
    # Vérifier si le message contient une demande
    has_quote_trigger = any(trigger in message_lower for trigger in quote_triggers)
    has_search_trigger = any(trigger in message_lower for trigger in search_triggers)
    
    # Vérifier qu'il y a du contexte
    has_context = any(keyword in message_lower for keyword in [
        'avec', 'pour', 'de', 'ref', 'prod', 'article', 'quantité', 'unité', 
        'corp', 'company', 'client', 'laser', 'réseau', 'ppm'
    ])
    
    return (has_quote_trigger or has_search_trigger) and has_context
@router.post("/assistant/continue_workflow")
async def continue_workflow_with_choice(request: Request):
    """Continuer workflow après choix utilisateur"""

    data = await request.json()
    task_id = data.get("task_id")
    choice_type = data.get("choice_type")

    # Récupérer contexte workflow
    context = await get_workflow_context(task_id)
    workflow = DevisWorkflow(task_id=task_id, force_production=True)

    if choice_type == "client_selected":
        # ⚠️ Branche CLIENT NON IMPLÉMENTÉE : workflow.handle_client_selection_and_continue
        # n'existe pas (chantier séparé à spécifier).
        raise HTTPException(
            status_code=501,
            detail="Continuation après sélection client non implémentée "
                   "(handle_client_selection_and_continue absent — chantier séparé)"
        )

    elif choice_type == "product_selected":
        # ⚠️ Branche PRODUIT NON IMPLÉMENTÉE : workflow.apply_product_choices n'existe pas.
        # Seule apply_product_suggestions est définie, avec un payload différent
        # (choices typés {"type": "use_suggestion", "selected_product", "quantity"}).
        # Même catégorie que handle_client_suggestions / handle_client_selection_and_continue :
        # chantier séparé (ne pas inventer la méthode ni adapter le payload ici).
        raise HTTPException(
            status_code=501,
            detail="Continuation après sélection produit non implémentée "
                   "(apply_product_choices absent — chantier séparé)"
        )
@router.post("/assistant/workflow/select_client")
async def select_client_and_continue(request: Request):
    """Sélection client et continuation workflow - SANS WebSocket"""
    data = await request.json()
    task_id = data.get("task_id")
    selected_client = data.get("selected_client")
    workflow_context = data.get("workflow_context", {})
    if not task_id or not selected_client:
        raise HTTPException(status_code=400, detail="task_id et selected_client requis")

    workflow = DevisWorkflow(task_id=task_id, force_production=True)

    # Traitement direct avec client sélectionné
    user_input = {
        "action": "select_existing",
        "selected_data": selected_client
    }

    result = await workflow.continue_after_user_input(user_input, workflow_context)

    return {"success": True, "result": result, "task_id": task_id}
# Modèle pour la compatibilité avec le frontend existant
class GenerateQuoteRequest(BaseModel):
    message: str
    draft_mode: Optional[bool] = False
    force_production: Optional[bool] = False  # Nouveau paramètre pour forcer la production

class GenerateQuoteResponse(BaseModel):
    status: Optional[str] = None
    success: Optional[bool] = None
    client: Optional[Dict[str, Any]] = None
    products: Optional[List[Dict[str, Any]]] = None
    total_amount: Optional[float] = None
    quote_id: Optional[str] = None
    stock_info: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    similar_clients: Optional[List[Dict[str, Any]]] = None

@router.post('/generate_quote', response_model=GenerateQuoteResponse)
async def generate_quote_endpoint(request: GenerateQuoteRequest):
    """
    🎯 Endpoint de compatibilité pour le frontend existant
    Transforme les demandes de devis en format compatible avec l'interface
    """
    try:
        user_message = request.prompt.strip()

        if not user_message:
            return GenerateQuoteResponse(
                success=False,
                error="Message vide"
            )

        logger.info(f"🎯 Demande de devis via /generate_quote: {user_message}")

        # Utiliser la logique existante du workflow

        # Créer le workflow avec task_id fixe pour éviter la double génération
        task_id = f"quote_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
        workflow = DevisWorkflow(
            validation_enabled=True,
            draft_mode=request.draft_mode,
            force_production=request.force_production,
            task_id=task_id  # Forcer l'utilisation d'un task_id cohérent
        )

        # Exécuter le workflow avec le message complet
        workflow_result = await workflow.process_prompt(user_message)
        # Si interaction utilisateur requise, retourner directement les données
        if workflow_result.get("status") == "user_interaction_required":
            return {
                "success": False,
                "requires_interaction": True,
                "interaction_data": workflow_result,
                "task_id": task_id
            }
        if workflow_result.get('success'):
            # Extraire les données pour le format frontend
            client_data = workflow_result.get('client', {})
            products_data = workflow_result.get('products', [])

            # Formater les produits pour le frontend
            formatted_products = []
            for product in products_data:
                formatted_products.append({
                    'item_code': product.get('code', product.get('item_code', '')),
                    'code': product.get('code', product.get('item_code', '')),
                    'item_name': product.get('name', product.get('item_name', '')),
                    'name': product.get('name', product.get('item_name', '')),
                    'quantity': product.get('quantity', 1),
                    'unit_price': product.get('price', product.get('unit_price', 0)),
                    'line_total': product.get('line_total', product.get('quantity', 1) * product.get('price', product.get('unit_price', 0)))
                })

            return GenerateQuoteResponse(
                status='success',
                success=True,
                client={
                    'name': client_data.get('name', 'Client non spécifié'),
                    'account_number': client_data.get('account_number', client_data.get('id', ''))
                },
                products=formatted_products,
                total_amount=workflow_result.get('total_amount', 0),
                quote_id=workflow_result.get('quote_id', 'N/A'),
                stock_info=workflow_result.get('stock_info'),
                similar_clients=workflow_result.get('similar_clients', [])
            )
        else:
            # En cas d'échec, retourner les détails de l'erreur
            error_message = workflow_result.get('message', 'Erreur lors de la génération du devis')

            # Si des clients similaires ont été trouvés, les inclure dans la réponse
            similar_clients = workflow_result.get('similar_clients', [])

            return GenerateQuoteResponse(
                success=False,
                error=error_message,
                message=error_message,
                similar_clients=similar_clients
            )

    except Exception as e:
        logger.error(f"Erreur dans generate_quote_endpoint: {e}")
        return GenerateQuoteResponse(
            success=False,
            error=f"Erreur interne: {str(e)}"
        )
@router.post("/search_clients")
async def search_clients_direct(request: Dict[str, Any]):
    """Recherche directe de clients pour affichage immédiat"""
    try:
        client_name = request.get("client_name", "")
        if not client_name:
            return {"success": False, "error": "Nom client requis"}
        # Recherche dans Salesforce
        mcp = MCPConnector()
        # CORRECTION: MCPConnector n'a pas de méthode connect(), utiliser test_connections
        connection_status = await mcp.test_connections()
        if not connection_status.get("results", {}).get("overall_status") == "OK":
            return {"success": False, "error": "Connexions système indisponibles"}
        
        search_result = await mcp.search_salesforce_accounts(client_name)
        clients = search_result.get("accounts", [])

        if clients:
            return {
                "success": True,
                "requires_selection": True,
                "clients": clients,
                "message": f"{len(clients)} client(s) trouvé(s)"
            }
        else:
            return {
                "success": True,
                "requires_creation": True,
                "client_name": client_name,
                "message": "Aucun client trouvé, création nécessaire"
            }
            
    except Exception as e:
        logger.error(f"Erreur recherche clients: {e}")
        return {"success": False, "error": str(e)}