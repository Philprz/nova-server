# routes/routes_progress.py
"""
Routes API pour le suivi de progression des générations de devis
À intégrer dans main.py avec : app.include_router(progress_router, prefix="/progress", tags=["progress"])
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from services.websocket_manager import websocket_manager
from services.progress_tracker import progress_tracker, TaskStatus
from workflow.devis_workflow import DevisWorkflow
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
logger = logging.getLogger(__name__)

# Configuration du router
# Le préfixe est appliqué lors de l'enregistrement dans main.py.
# Ne pas définir de préfixe ici pour éviter un doublon dans les routes.
router = APIRouter(
    tags=["Progress"]
)

# =============================================
# MODÈLES PYDANTIC
# =============================================

class TaskProgressResponse(BaseModel):
    """Réponse de progression d'une tâche"""
    task_id: str
    status: str
    overall_progress: int
    current_step: Optional[str] = None
    current_step_title: Optional[str] = None
    completed_steps: int
    total_steps: int
    start_time: str
    end_time: Optional[str] = None
    duration: Optional[float] = None
    draft_mode: bool
    user_prompt: str
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

class TaskDetailedResponse(BaseModel):
    """Réponse détaillée avec phases"""
    task_id: str
    status: str
    overall_progress: int
    current_step: Optional[str] = None
    current_step_title: Optional[str] = None
    completed_steps: int
    total_steps: int
    start_time: str
    end_time: Optional[str] = None
    duration: Optional[float] = None
    draft_mode: bool
    user_prompt: str
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    phases: Dict[str, Any]

# =============================================
# ENDPOINTS REST
# =============================================

@router.get("/task/{task_id}")
async def get_task_progress(task_id: str):
    """
    Récupère le statut de progression d'une tâche
    """
    logger.info(f"Recherche de la tâche {task_id} dans progress_tracker")
    try:
        # Rechercher d'abord dans les tâches actives
        task = progress_tracker.get_task(task_id)
        if task:
            progress_data = task.get_overall_progress()
            return TaskProgressResponse(**progress_data)
        # Attendre brièvement si tâche en cours de création
        import asyncio
        if not task:
            await asyncio.sleep(0.5)  # Attendre 500ms
            task = progress_tracker.get_task(task_id)
        
        # Rechercher dans l'historique si pas trouvé
        historical_task = progress_tracker.get_task_from_history(task_id)
        if historical_task:
            return TaskProgressResponse(**historical_task)
        
        # Dernier essai après délai plus long pour tâches en création
        if not task and not historical_task:
            await asyncio.sleep(1.0)  # Attendre 1 seconde
            task = progress_tracker.get_task(task_id)
        if task:
            progress_data = task.get_overall_progress()
            return TaskProgressResponse(**progress_data)
        # Si vraiment pas trouvé après tous les essais
        raise HTTPException(status_code=404, detail=f"Tâche {task_id} non trouvée après délais d'attente")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération progression {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.get("/task/{task_id}/detailed")
async def get_task_detailed_progress(task_id: str):
    """
    Récupère le statut détaillé avec toutes les phases
    """
    try:
        task = progress_tracker.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Tâche {task_id} non trouvée")
        
        detailed_progress = task.get_detailed_progress()
        return TaskDetailedResponse(**detailed_progress)
        
    except Exception as e:
        logger.error(f"Erreur récupération progression détaillée {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/active")
async def get_active_tasks():
    """
    Liste toutes les tâches actives
    """
    try:
        active_tasks = progress_tracker.get_active_tasks()
        return {
            "count": len(active_tasks),
            "tasks": [task.get_overall_progress() for task in active_tasks]
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération tâches actives: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """
    Annule une tâche en cours
    """
    try:
        success = progress_tracker.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Tâche {task_id} non trouvée")
        
        return {"success": True, "message": f"Tâche {task_id} annulée"}
        
    except Exception as e:
        logger.error(f"Erreur annulation tâche {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup")
async def cleanup_old_tasks(max_age_hours: int = 24):
    """
    Nettoie les anciennes tâches terminées
    """
    try:
        cleaned_count = progress_tracker.cleanup_old_tasks(max_age_hours)
        return {
            "success": True,
            "cleaned_tasks": cleaned_count,
            "message": f"{cleaned_count} tâches anciennes supprimées"
        }
        
    except Exception as e:
        logger.error(f"Erreur nettoyage tâches: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================
# WEBSOCKET POUR TEMPS RÉEL
# =============================================


async def websocket_progress(websocket: WebSocket, task_id: str):
    """
    WebSocket pour suivi en temps réel d'une tâche
    """
    await websocket_manager.connect(websocket, task_id)
    logger.info(f"Client connecté au WebSocket pour tâche {task_id}")
    
    try:
        # Envoyer le statut initial
        task = progress_tracker.get_task(task_id)
        if task:
            initial_progress = task.get_detailed_progress()
            await websocket.send_json({
                "type": "initial_progress",
                "data": initial_progress
            })
        
        # Maintenir la connexion active
        while True:
            try:
                # Recevoir les messages du client (ping/pong)
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "connection_confirm":
                    # Confirmer l'enregistrement de la connexion
                    await websocket.send_json({
                    "type": "connection_confirmed",
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat(),
                    "message": "Connexion WebSocket confirmée côté serveur"
                    })
                    logger.info(f"✅ Connexion confirmée pour task: {task_id}")
            except WebSocketDisconnect:
                break
                
    except Exception as e:
        logger.error(f"Erreur WebSocket pour tâche {task_id}: {e}")
        
    finally:
        websocket_manager.disconnect(websocket, task_id)
        logger.info(f"Client déconnecté du WebSocket pour tâche {task_id}")

async def handle_user_response_task(task_id: str, response_data: dict):
    """Traite réponses utilisateur pour les tâches"""
    try:
        logger.info(f"🎯 Traitement réponse utilisateur task {task_id}: {response_data}")
        
        response_type = response_data.get("response_type")
        if response_type == "client_validation":
            await handle_client_selection_task(task_id, response_data)
            
    except Exception as e:
        logger.error(f"❌ Erreur traitement réponse task {task_id}: {e}")

async def handle_client_selection_task(task_id: str, response_data: dict):
    """Traite sélection client pour les tâches"""
    from workflow.devis_workflow import DevisWorkflow
    
    selected_client = response_data.get("selected_client")
    if selected_client:
        workflow = DevisWorkflow(task_id=task_id, force_production=True)
        user_input = {
            "action": "select_existing", 
            "selected_data": selected_client
        }
        result = await workflow.continue_after_user_input(user_input, {})
        logger.info(f"✅ Client task sélectionné pour {task_id}")
        
# =============================================
# ENDPOINTS DE VALIDATION UTILISATEUR
# =============================================

@router.get("/task/{task_id}/validation")
async def get_task_validation(task_id: str):
    """Récupère validation en attente pour affichage interface"""
    task = progress_tracker.get_task(task_id)
    if not task:
        # Chercher dans l'historique aussi
        historical_task = progress_tracker.get_task_from_history(task_id)
        if historical_task and historical_task.get("validation_data"):
            return {
                "has_validation": True,
                "validation_data": historical_task["validation_data"]
            }
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    
    if task.validation_data:
        # Vérifier aussi les messages WebSocket en attente
        pending_ws_messages = websocket_manager.pending_messages.get(task_id, [])
        interaction_messages = [msg for msg in pending_ws_messages if msg.get("type") == "user_interaction_required"]
        if interaction_messages:
            latest_interaction = interaction_messages[-1]
            return {
                "has_validation": True,
                "validation_data": latest_interaction.get("interaction_data"),
                "message": "Interaction récupérée depuis WebSocket en attente"
            }
        pending_validations = {k: v for k, v in task.validation_data.items() if v.get("status") == "pending"}
        if pending_validations:
            return {
                "has_validation": True,
                "validation_data": pending_validations
            }
    
    return {"has_validation": False}

@router.post("/task/{task_id}/validation/{step_id}")
async def submit_validation(task_id: str, step_id: str, user_response: Dict[str, Any]):
    """
    Soumet une réponse de validation utilisateur
    """
    try:
        task = progress_tracker.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Tâche {task_id} non trouvée")
        
        # Traiter la validation
        task.complete_user_validation(step_id, user_response)
        
        # Notifier via WebSocket
        await websocket_manager.broadcast_to_task(task_id, {
            "type": "validation_completed",
            "step_id": step_id,
            "user_response": user_response
        })
        
        return {
            "success": True,
            "message": f"Validation complétée pour étape {step_id}"
        }
        
    except Exception as e:
        logger.error(f"Erreur validation {task_id}/{step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================
# ENDPOINTS DE STATISTIQUES
# =============================================

@router.get("/stats")
async def get_progress_stats():
    """
    Statistiques globales du système de progression
    """
    try:
        stats = progress_tracker.get_global_stats()
        return {
            "timestamp": datetime.now().isoformat(),
            "active_tasks": stats.get("active_tasks", 0),
            "completed_tasks": stats.get("completed_tasks", 0),
            "failed_tasks": stats.get("failed_tasks", 0),
            "total_tasks": stats.get("total_tasks", 0),
            "average_duration": stats.get("average_duration", 0),
            "success_rate": stats.get("success_rate", 0)
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération statistiques: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === MODÈLES DE DONNÉES ===

class StartQuoteRequest(BaseModel):
    """Requête pour démarrer une génération de devis"""
    prompt: str
    draft_mode: bool = False

class QuoteTaskResponse(BaseModel):
    """Réponse avec informations sur une tâche"""
    task_id: str
    status: str
    message: str

# === ENDPOINTS PRINCIPAUX ===

from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio

@router.post("/start_quote", response_model=QuoteTaskResponse)
async def start_quote_generation(request: StartQuoteRequest, background_tasks: BackgroundTasks):
    """
    Démarre une génération de devis en arrière-plan avec tracking de progression
    """
    try:
        # Créer une tâche de tracking
        task = progress_tracker.create_task(
            user_prompt=request.prompt,
            draft_mode=request.draft_mode
        )
        
        # Lancer la génération en arrière-plan
        background_tasks.add_task(
            _execute_quote_generation,  # ← Correction : pas d'astérisques
            task.task_id,
            request.prompt,
            request.draft_mode
        )
        
        return QuoteTaskResponse(
            task_id=task.task_id,
            status=task.status.value,
            message="Génération de devis démarrée"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du démarrage: {str(e)}")

async def _execute_quote_generation(task_id: str, prompt: str, draft_mode: bool):
    """
    Exécute la génération de devis en arrière-plan avec gestion d'erreurs
    """
    try:
        # Attendre que le client se connecte au WebSocket
        await asyncio.sleep(0.5)
        
        # Créer le workflow avec le task_id
        workflow = DevisWorkflow(
            validation_enabled=True, 
            draft_mode=draft_mode,
            task_id=task_id  # Important : passer le task_id existant
        )
        
        # Exécuter le workflow
        workflow_result = await workflow.process_prompt(prompt, task_id=task_id)
        logger.info(f"🔍 DEBUG: Envoi interaction WebSocket - Data: {workflow_result.get('interaction_data', 'MISSING')}")
        # Interaction utilisateur requise ?
        if workflow_result.get("status") == "user_interaction_required":
            logger.info(f"🔄 Interaction utilisateur requise pour tâche {task_id}")
            logger.info(f"🔍 DEBUG ROUTE: workflow_result keys = {list(workflow_result.keys())}")
            logger.info(f"🔍 DEBUG ROUTE: interaction_data = {workflow_result.get('interaction_data', 'MISSING')}")
            logger.info(f"🔍 DEBUG ROUTE: WebSocket connections pour {task_id} = {len(websocket_manager.task_connections.get(task_id, []))}")
            await websocket_manager.send_user_interaction_required(
            task_id,
            workflow_result.get("interaction_data", workflow_result)
            )
            # Ne pas marquer comme complet, attendre l'interaction
            return
        
        # Workflow terminé avec succès
        if workflow_result.get("success"):
            progress_tracker.complete_task(task_id, workflow_result)
        else:
            # Workflow terminé avec erreur
            error_msg = workflow_result.get("error", "Erreur inconnue")
            progress_tracker.fail_task(task_id, error_msg)
            
    except Exception as e:
        logger.error(f"❌ Erreur exécution workflow: {str(e)}")
        progress_tracker.fail_task(task_id, f"Erreur d'exécution: {str(e)}")


@router.get("/quote_status/{task_id}")
async def get_quote_status(task_id: str, detailed: bool = False):
    """
    Récupère le statut d'une génération de devis
    """
    try:
        task = progress_tracker.get_task(task_id)
        if not task:
            logger.info(f"Tâche {task_id} non trouvée dans les tâches actives, recherche dans l'historique")
            # Vérifier dans l'historique
            history = progress_tracker.get_task_history()
            task_history = next((t for t in history if t.get("task_id") == task_id), None)
            if task_history:
                return {
                    "found": True,
                    "completed": True,
                    **task_history
                }
            else:
                logger.warning(f"Tâche {task_id} introuvable même dans l'historique")
                raise HTTPException(status_code=404, detail=f"Tâche {task_id} introuvable")
        
        # Tâche active trouvée
        if detailed:
            return {
                "found": True,
                "completed": False,
                **task.get_detailed_progress()
            }
        else:
            return {
                "found": True,
                "completed": False,
                **task.get_overall_progress()
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération quote_status {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération: {str(e)}")



@router.get("/active_quotes")
async def get_active_quotes():
    """Récupère toutes les générations de devis en cours"""
    try:
        active_tasks = progress_tracker.get_all_active_tasks()
        return {
            "active_tasks": active_tasks,
            "count": len(active_tasks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.get("/quote_history") 
async def get_quote_history(limit: int = 20):
    """Récupère l'historique des générations de devis"""
    try:
        history = progress_tracker.get_task_history()
        logger.info(f"Recherche de la tâche {task_id} dans progress_tracker")
        # Trier par date de fin décroissante et limiter
        history_sorted = sorted(
            history, 
            key=lambda x: x.get("start_time", ""), 
            reverse=True
        )[:limit]
        
        return {
            "history": history_sorted,
            "count": len(history_sorted),
            "total_in_history": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.delete("/cancel_quote/{task_id}")
async def cancel_quote_generation(task_id: str):
    """Annule une génération de devis en cours"""
    try:
        task = progress_tracker.get_task(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail=f"Tâche {task_id} introuvable")
        
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            raise HTTPException(status_code=400, detail=f"Tâche {task_id} déjà terminée")
        
        # Marquer comme annulée
        progress_tracker.fail_task(task_id, "Annulé par l'utilisateur")
        
        return {
            "cancelled": True,
            "task_id": task_id,
            "message": "Génération de devis annulée"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

# === ENDPOINTS DE RÉTROCOMPATIBILITÉ ===

@router.post("/generate_quote")
async def generate_quote_legacy(request: dict, background_tasks: BackgroundTasks):
    """
    Endpoint de rétrocompatibilité pour l'ancienne API synchrone
    Retourne immédiatement l'ID de tâche pour le polling
    """
    try:
        # Extraire les paramètres
        prompt = request.get("prompt", request.get("query", ""))
        draft_mode = request.get("draft_mode", False)
        
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt manquant")
        
        # Créer la requête
        start_request = StartQuoteRequest(prompt=prompt, draft_mode=draft_mode)
        
        # Démarrer la génération
        response = await start_quote_generation(start_request, background_tasks)
        
        return {
            "status": "started",
            "task_id": response.task_id,
            "message": "Génération démarrée - suivez la progression via /progress/quote_status/{task_id}",
            "polling_url": f"/progress/quote_status/{response.task_id}",
            "legacy_mode": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

# === FONCTION D'EXÉCUTION EN ARRIÈRE-PLAN ===

async def _execute_quote_generation(task_id: str, prompt: str, draft_mode: bool):
    """
    Exécute la génération de devis en arrière-plan avec gestion d'erreurs
    """
    try:
        # Créer le workflow avec le bon mode
        workflow = EnhancedDevisWorkflow(validation_enabled=True, draft_mode=draft_mode)
        
        # Exécuter le workflow (il gérera automatiquement le tracking)
        await workflow.process_prompt(prompt, task_id=task_id)
        
        # Le workflow gère automatiquement le completion de la tâche
        # donc rien à faire ici si tout s'est bien passé
        
    except Exception as e:
        # En cas d'erreur non gérée par le workflow
        progress_tracker.fail_task(task_id, f"Erreur d'exécution: {str(e)}")

# === ENDPOINTS DE DIAGNOSTIC ===

@router.get("/progress_stats")
async def get_progress_stats():
    """Récupère les statistiques globales du système de progression"""
    try:
        active_tasks = progress_tracker.get_all_active_tasks()
        history = progress_tracker.get_task_history()
        logger.info(f"Recherche de la tâche {task_id} dans progress_tracker")
        # Calculer statistiques
        total_tasks = len(active_tasks) + len(history)
        completed_tasks = len([t for t in history if t.get("status") == "completed"])
        failed_tasks = len([t for t in history if t.get("status") == "failed"])
        success_rate = (completed_tasks / len(history) * 100) if history else 0
        
        # Durée moyenne des tâches réussies
        successful_durations = [
            t.get("duration", 0) for t in history 
            if t.get("status") == "completed" and t.get("duration")
        ]
        avg_duration = sum(successful_durations) / len(successful_durations) if successful_durations else 0
        
        return {
            "total_tasks": total_tasks,
            "active_tasks": len(active_tasks),
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": round(success_rate, 1),
            "average_duration_seconds": round(avg_duration, 2),
            "system_status": "healthy" if success_rate > 80 else "degraded"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

        
async def handle_user_response(task_id: str, response_data: dict):
    """Traite une réponse utilisateur"""
    task = progress_tracker.get_task(task_id)
    if not task:
        return
        
    response_type = response_data.get("response_type")
    step_id = response_data.get("step_id")
    
    if response_type == "client_validation":
        # Traiter la validation client
        await handle_client_validation(task_id, step_id, response_data)
    elif response_type == "product_selection":
        # Traiter la sélection produit
        await handle_product_selection(task_id, step_id, response_data)

async def handle_client_validation(task_id: str, step_id: str, response_data: dict):
    """Traite la validation client par l'utilisateur"""
    try:
        logger.info(f"🎯 Traitement validation client: {task_id}/{step_id}")
        
        # Récupérer la tâche
        task = progress_tracker.get_task(task_id)
        if not task:
            logger.error(f"❌ Tâche {task_id} introuvable")
            return
        
        # Extraire les données de réponse
        selected_option = response_data.get("selected_option")
        client_data = response_data.get("client_data", {})
        
        # Créer instance workflow pour continuer le traitement
        from workflow.devis_workflow import DevisWorkflow
        workflow = DevisWorkflow(task_id=task_id, force_production=True)
        
        # Traiter selon le type de sélection
        if selected_option == "select_existing":
            # Client existant sélectionné
            logger.info(f"✅ Client sélectionné: {client_data.get('Name', 'Inconnu')}")
            continuation_result = await workflow.continue_with_selected_client(client_data)
            
        elif selected_option == "create_new":
            # Création nouveau client
            client_name = response_data.get("client_name", "")
            logger.info(f"✅ Création client demandée: {client_name}")
            continuation_result = await workflow.continue_with_new_client(client_name)
            
        else:
            logger.error(f"❌ Option non reconnue: {selected_option}")
            return
            
        # Notifier le résultat via WebSocket
        await websocket_manager.send_task_update(task_id, {
            "type": "client_validation_processed",
            "step_id": step_id,
            "result": continuation_result
        })
        
        # Marquer l'étape comme complétée
        task.complete_user_validation(step_id, response_data)
        
    except Exception as e:
        logger.exception(f"❌ Erreur validation client {task_id}: {str(e)}")
        await websocket_manager.send_task_update(task_id, {
            "type": "validation_error",
            "step_id": step_id,
            "error": str(e)
        })

async def handle_product_selection(task_id: str, step_id: str, response_data: dict):
    """Traite la sélection produit par l'utilisateur"""
    try:
        logger.info(f"🛍️ Traitement sélection produit: {task_id}/{step_id}")
        
        # Récupérer la tâche
        task = progress_tracker.get_task(task_id)
        if not task:
            logger.error(f"❌ Tâche {task_id} introuvable")
            return
            
        # Extraire les sélections produits
        selected_products = response_data.get("selected_products", [])
        
        # Créer instance workflow
        from workflow.devis_workflow import DevisWorkflow
        workflow = DevisWorkflow(task_id=task_id, force_production=True)
        
        # Continuer avec les produits sélectionnés
        continuation_result = await workflow.continue_with_products(selected_products)
        
        # Notifier via WebSocket
        await websocket_manager.send_task_update(task_id, {
            "type": "product_selection_processed", 
            "step_id": step_id,
            "result": continuation_result,
            "selected_count": len(selected_products)
        })
        
        # Marquer complété
        task.complete_user_validation(step_id, response_data)
        
    except Exception as e:
        logger.exception(f"❌ Erreur sélection produit {task_id}: {str(e)}")
        await websocket_manager.send_task_update(task_id, {
            "type": "validation_error",
            "step_id": step_id, 
            "error": str(e)
        })