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

router = APIRouter()

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
            _execute_quote_generation,
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

@router.get("/quote_status/{task_id}")
async def get_quote_status(task_id: str, detailed: bool = False):
    """
    Récupère le statut d'une génération de devis
    """
    try:
        task = progress_tracker.get_task(task_id)
        
        if not task:
            # Vérifier dans l'historique
            history = progress_tracker.get_task_history()
            task_history = next((t for t in history if t["task_id"] == task_id), None)
            
            if task_history:
                return {
                    "found": True,
                    "completed": True,
                    **task_history
                }
            else:
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
        workflow = DevisWorkflow(validation_enabled=True, draft_mode=draft_mode)
        
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

@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket endpoint pour suivi temps réel d'une tâche"""
    await websocket_manager.connect(websocket, task_id)
    
    try:
        # Envoyer l'état initial
        task = progress_tracker.get_task(task_id)
        if task:
            await websocket.send_text(json.dumps({
                "type": "initial_state",
                "task_id": task_id,
                "data": task.get_detailed_progress()
            }))
        
        # Maintenir la connexion ouverte
        while True:
            try:
                # Recevoir les messages du client (validations utilisateur)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "user_response":
                    await handle_user_response(task_id, message.get("data", {}))
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Erreur WebSocket: {e}")
                break
                
    finally:
        websocket_manager.disconnect(websocket, task_id)
        
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