# services/progress_tracker.py
"""
Système de suivi de progression pour les générations de devis
Réutilise et améliore le pattern du sync_dashboard
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)
# Étapes métier parallèles
BUSINESS_STEPS_PARALLEL = {
    "analyze_request": [
        ("parse_prompt", "🔍 Analyse de votre demande"),
        ("extract_entities", "📋 Identification des besoins"),
        ("validate_input", "✅ Demande comprise")
    ],
    "parallel_search": [
        ("search_client_start", "👤 Recherche client..."),
        ("search_product_start", "📦 Recherche produits..."),
        ("search_client_progress", "🔄 Consultation bases client"),
        ("search_product_progress", "🔄 Consultation catalogue"),
        ("search_client_complete", "👤 Résultat recherche client"),
        ("search_product_complete", "📦 Résultat recherche produits")
    ],
    "user_validation": [
        ("client_validation", "❓ Validation client requise"),
        ("product_validation", "❓ Validation produits requise"),
        ("user_confirmed", "✅ Choix utilisateur confirmé")
    ],
    "quote_generation": [
        ("prepare_quote", "📋 Préparation du devis"),
        ("save_to_sap", "💾 Enregistrement SAP"),
        ("sync_salesforce", "☁️ Synchronisation Salesforce"),
        ("quote_finalized", "✅ Devis finalisé")
    ]
}
class TaskStatus(str, Enum):
    """Statuts possibles d'une tâche"""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    WAITING_USER = "waiting_user"
    FAILED = "failed"
    CANCELLED = "cancelled"
def set_waiting_for_user(self, task_id: str, reason: str = ""):
    t = self.tasks.get(task_id)
    if not t:
        return
    t.status = TaskStatus.WAITING_USER
    meta = getattr(t, "meta", {}) or {}
    meta["waiting_reason"] = reason
    t.meta = meta

def is_waiting_for_user(self, task_id: str) -> bool:
    t = self.tasks.get(task_id)
    return bool(t and getattr(t, "status", None) == TaskStatus.WAITING_USER)

class ProgressStep:
    """Représente une étape de progression"""
    def __init__(self, 
                 step_id: str, 
                 title: str, 
                 status: TaskStatus = TaskStatus.PENDING,
                 message: str = "",
                 progress_percent: int = 0):
        self.step_id = step_id
        self.title = title
        self.status = status
        self.message = message
        self.progress_percent = progress_percent
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.error: Optional[str] = None

    def start(self, message: str = ""):
        """Démarre l'étape"""
        self.status = TaskStatus.RUNNING
        self.start_time = datetime.now()
        self.message = message or f"Exécution de {self.title}..."
        self.progress_percent = 0

    def complete(self, message: str = "", progress_percent: int = 100):
        """Termine l'étape avec succès"""
        self.status = TaskStatus.COMPLETED
        self.end_time = datetime.now()
        self.message = message or f"{self.title} terminé"
        self.progress_percent = progress_percent

    def fail(self, error: str, message: str = ""):
        """Termine l'étape en erreur"""
        self.status = TaskStatus.FAILED
        self.end_time = datetime.now()
        self.error = error
        self.message = message or f"Erreur lors de {self.title}"
        
    def update_progress(self, progress_percent: int, message: str = ""):
        """Met à jour la progression de l'étape"""
        self.progress_percent = min(100, max(0, progress_percent))
        if message:
            self.message = message

class QuoteTask:
    BUSINESS_STEPS = {
        "analyze_request": [
            ("parse_prompt", "🔍 Analyse de votre demande"),
            ("extract_entities", "📋 Identification des besoins"), 
            ("validate_input", "✅ Demande comprise")
        ],
        "validate_client": [
            ("search_client", "👤 Recherche du client"),
            ("client_search_progress", "🔍 Consultation des bases de données"),
            ("client_alternatives", "🔄 Évaluation des alternatives"),
            ("client_validation", "✅ Validation utilisateur requise"),
            ("client_creation", "🏗️ Création du nouveau client"),
            ("client_ready", "✅ Client confirmé")
        ],
        "validate_products": [
            ("search_products", "📦 Recherche des produits"),
            ("product_search_progress", "🔍 Consultation du catalogue"),
            ("product_alternatives", "🔄 Analyse des alternatives"),
            ("product_validation", "✅ Sélection utilisateur requise"),
            ("connect_catalog", "🔌 Connexion catalogue"),
            ("lookup_products", "📦 Vérification des produits"),
            ("get_products_info", "ℹ️ Informations produits"),
            ("check_stock", "📊 Vérification du stock"),
            ("calculate_prices", "💰 Calcul des prix"),
            ("product_ready", "✅ Produits confirmés")
        ],
        "create_quote": [
            ("prepare_quote", "📋 Préparation du devis"),
            ("create_quote", "🧾 Création du devis"),
            ("sync_external_systems", "💾 Synchronisation SAP & Salesforce"),
            ("sync_to_sap", "💾 Enregistrement SAP"),
            ("sync_to_salesforce", "☁️ Synchronisation Salesforce"),
            ("save_to_sap", "💾 Enregistrement SAP"),
            ("sync_salesforce", "☁️ Synchronisation Salesforce"),
            ("check_duplicates", "🔍 Vérification doublons"),  # ✅ AJOUT ICI
            ("quote_finalized", "✅ Devis finalisé")
        ]
    }
    def __init__(self, task_id: str = None, user_prompt: str = "", draft_mode: bool = False):
        self.task_id = task_id if task_id else f"quote_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self.user_prompt = user_prompt
        self.draft_mode = draft_mode
        self.status = TaskStatus.PENDING
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.steps: Dict[str, ProgressStep] = {}
        self.current_step: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.user_interactions = []  # Historique des interactions
        self.validation_data = {}    # Données de validation
        self.alternatives = {}       # Alternatives disponibles
        self.interaction_data = {}  # Stocker les données d'interaction
        self.context = {}           # Contexte du workflow pour persistence
        # Initialiser toutes les étapes
        self._initialize_steps()
    def add_user_interaction(self, interaction_type: str, data: dict, response: dict = None):
        """Ajoute une interaction utilisateur à l'historique"""
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "type": interaction_type,
            "data": data,
            "response": response,
            "step_id": self.current_step
        }
        self.user_interactions.append(interaction)
        
    def set_alternatives(self, step_id: str, alternatives: list):
        """Définit les alternatives disponibles pour une étape"""
        self.alternatives[step_id] = alternatives
        
    def get_alternatives(self, step_id: str) -> list:
        """Récupère les alternatives pour une étape"""
        return self.alternatives.get(step_id, [])        
    def _initialize_steps(self):
        """Initialise toutes les étapes métier"""
        for phase_name, phase_steps in self.BUSINESS_STEPS.items():
            for step_id, step_title in phase_steps:
                self.steps[step_id] = ProgressStep(step_id, step_title)
    
    def start_step(self, step_id: str, message: str = "") -> bool:
        """Démarre une étape spécifique"""
        if step_id not in self.steps:
            logger.warning(f"Étape inconnue: {step_id}")
            return False
            
        self.current_step = step_id
        self.steps[step_id].start(message)
        logger.info(f"Étape démarrée: {step_id} - {self.steps[step_id].title}")
        return True
    
    def complete_step(self, step_id: str, message: str = "", progress_percent: int = 100) -> bool:
        """Termine une étape avec succès"""
        if step_id not in self.steps:
            return False
            
        self.steps[step_id].complete(message, progress_percent)
        logger.info(f"Étape terminée: {step_id} - {self.steps[step_id].title}")
        return True
    
    def fail_step(self, step_id: str, error: str, message: str = "") -> bool:
        """Termine une étape en erreur"""
        if step_id not in self.steps:
            return False
            
        self.steps[step_id].fail(error, message)
        self.status = TaskStatus.FAILED
        self.error = error
        logger.error(f"Étape échouée: {step_id} - {error}")
        return True
    
    def update_step_progress(self, step_id: str, progress: int, message: str = "") -> bool:
        """Met à jour la progression d'une étape avec notification"""
        if step_id not in self.steps:
            logger.warning(f"Étape inconnue pour mise à jour: {step_id}")
            return False
            
        self.steps[step_id].update_progress(progress, message)
        self.current_step = step_id
        
        # Log pour debugging
        logger.debug(f"📊 Progression {step_id}: {progress}% - {message}")
        
        return True
    
    def complete_task(self, result: Dict[str, Any]):
        """Termine la tâche avec succès"""
        self.status = TaskStatus.COMPLETED
        self.end_time = datetime.now()
        self.result = result
        logger.info(f"Tâche terminée: {self.task_id}")
    
    def fail_task(self, error: str):
        """Termine la tâche en erreur"""
        self.status = TaskStatus.FAILED
        self.end_time = datetime.now()
        self.error = error
        logger.error(f"Tâche échouée: {self.task_id} - {error}")
    
    def get_overall_progress(self) -> Dict[str, Any]:
        """Retourne le progrès global de la tâche"""
        completed_steps = len([s for s in self.steps.values() if s.status == TaskStatus.COMPLETED])
        total_steps = len(self.steps)
        overall_percent = int((completed_steps / total_steps) * 100) if total_steps > 0 else 0
        
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "overall_progress": overall_percent,
            "current_step": self.current_step,
            "current_step_title": self.steps[self.current_step].title if self.current_step and self.current_step in self.steps else "",
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": (self.end_time - self.start_time).total_seconds() if self.end_time else None,
            "draft_mode": self.draft_mode,
            "user_prompt": self.user_prompt,
            "error": self.error,
            "result": self.result if self.status == TaskStatus.COMPLETED else None
        }
    
    def get_detailed_progress(self) -> Dict[str, Any]:
        """Retourne le progrès détaillé avec toutes les étapes"""
        overall = self.get_overall_progress()
        
        # Regrouper les étapes par phase
        phases = {}
        for phase_name, phase_steps in self.BUSINESS_STEPS.items():
            phases[phase_name] = {
                "name": phase_name,
                "steps": []
            }
            for step_id, step_title in phase_steps:
                if step_id in self.steps:
                    step = self.steps[step_id]
                    phases[phase_name]["steps"].append({
                        "id": step.step_id,
                        "title": step.title,
                        "status": step.status.value,
                        "message": step.message,
                        "progress_percent": step.progress_percent,
                        "start_time": step.start_time.isoformat() if step.start_time else None,
                        "end_time": step.end_time.isoformat() if step.end_time else None,
                        "error": step.error
                    })
        
        overall["phases"] = phases
        return overall
    def require_user_validation(self, step_id: str, validation_type: str, data: dict):
        """Marque une étape comme nécessitant une validation utilisateur"""
        self.validation_data[step_id] = {
            "type": validation_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        # Mettre à jour le statut de l'étape
        if step_id in self.steps:
            self.steps[step_id].status = TaskStatus.PENDING
            self.steps[step_id].message = f"Validation utilisateur requise: {validation_type}"
            
    def complete_user_validation(self, step_id: str, user_response: dict):
        """Complète une validation utilisateur"""
        if step_id in self.validation_data:
            self.validation_data[step_id]["status"] = "completed"
            self.validation_data[step_id]["user_response"] = user_response
            self.validation_data[step_id]["completed_at"] = datetime.now().isoformat()
            
            # Enregistrer l'interaction
            self.add_user_interaction(
                interaction_type=self.validation_data[step_id]["type"],
                data=self.validation_data[step_id]["data"],
                response=user_response
            )
            
            # Continuer l'étape
            self.complete_step(step_id, f"Validation utilisateur complétée: {self.validation_data[step_id]['type']}")
class ParallelStep:
    """Étape parallèle avec statut indépendant"""
    
    def __init__(self, step_id: str, title: str, parent_group: str = None):
        self.step_id = step_id
        self.title = title
        self.parent_group = parent_group
        self.status = TaskStatus.PENDING
        self.details = {}
        self.sub_steps = []
        self.timestamp = datetime.now()
    
    def add_detail(self, key: str, value: Any):
        """Ajoute des détails"""
        self.details[key] = value
    
    def add_sub_step(self, title: str, status: str = "pending"):
        """Ajoute une sous-étape"""
        self.sub_steps.append({
            "title": title,
            "status": status,
            "timestamp": datetime.now().isoformat()
        })
class ProgressTracker:
    """Gestionnaire global des tâches de progression"""
    
    def __init__(self):
        self.active_tasks: Dict[str, QuoteTask] = {}
        self.completed_tasks: List[Dict[str, Any]] = []
        self.max_completed_history = 50  # Garder les 50 dernières tâches
    
    def create_task(self, user_prompt: str = "", draft_mode: bool = False, task_id: str = None) -> QuoteTask:
        """Crée une nouvelle tâche de génération de devis avec idempotence"""
        # Vérifier si la tâche existe déjà
        if task_id and task_id in self.active_tasks:
            logger.info(f"♻️ Tâche existante récupérée: {task_id}")
            return self.active_tasks[task_id]
        
        task = QuoteTask(task_id=task_id, user_prompt=user_prompt, draft_mode=draft_mode)
        self.active_tasks[task.task_id] = task
        logger.info(f"🆕 Nouvelle tâche créée: {task.task_id}")
        return task
    
    def get_task(self, task_id: str) -> Optional[QuoteTask]:
        """Récupère une tâche par son ID"""
        return self.active_tasks.get(task_id)
    
    def complete_task(self, task_id: str, result: Dict[str, Any]):
        """
        Termine une tâche et sauvegarde le résultat
        """
        if task_id not in self.active_tasks:
            logger.warning(f"⚠️ Tentative de completion tâche inexistante: {task_id}")
            return False

        task = self.active_tasks[task_id]

        # Sécuriser la complétion de la tâche
        try:
            task.complete_task(result)
        except Exception as e:
            logger.error(f"❌ Échec complete_task({task_id}): {e}")
            # On continue quand même l'archivage minimal
            # (option: return False si tu veux un échec strict)
        
        # Sauvegarder le résultat dans l'historique
        try:
            task_data = task.get_overall_progress()
        except Exception as e:
            logger.error(f"❌ get_overall_progress({task_id}) a échoué: {e}")
            task_data = {"task_id": task_id, "progress": None}
        # s'assurer d'une copie indépendante
        task_data = dict(task_data) if isinstance(task_data, dict) else {"task_id": task_id}
        task_data["result"] = result  # Ajouter le résultat
        self.completed_tasks.append(task_data)

        # Limiter la taille de l'historique
        if len(self.completed_tasks) > self.max_completed_history:
            self.completed_tasks = self.completed_tasks[-self.max_completed_history:]

        # Supprimer des tâches actives
        del self.active_tasks[task_id]
            
        logger.info(f"✅ Tâche {task_id} déplacée vers l'historique avec résultat")
        return True

    
    def fail_task(self, task_id: str, error: str):
        """Termine une tâche en erreur"""
        if task_id not in self.active_tasks:
            return False
            
        task = self.active_tasks[task_id]
        task.fail_task(error)
        
        # Déplacer vers l'historique
        self.completed_tasks.append(task.get_overall_progress())
        
        # Supprimer des tâches actives
        del self.active_tasks[task_id]
        # 🔧 CORRECTION: Notification WebSocket d'échec
        try:
            from services.websocket_manager import websocket_manager
            import asyncio
            
            asyncio.create_task(websocket_manager.broadcast_to_task(task_id, {
                "type": "error",
                "task_id": task_id,
                "error": error,
                "status": "failed",
                "timestamp": datetime.now().isoformat()
            }))
            logger.info(f"🔔 Notification WebSocket d'erreur envoyée pour {task_id}")
        except Exception as e:
            logger.error(f"Erreur notification WebSocket échec: {e}")
        return True
    
    def get_all_active_tasks(self) -> List[Dict[str, Any]]:
        """Retourne toutes les tâches actives"""
        return [task.get_overall_progress() for task in self.active_tasks.values()]
    
    def get_task_history(self) -> List[Dict[str, Any]]:
        """Retourne l'historique des tâches terminées"""
        return self.completed_tasks.copy()

    # 🔧 NOUVELLES MÉTHODES POUR LE WORKFLOW

    def set_current_task(self, task_id: str):
        """
        🔧 NOUVELLE MÉTHODE : Définit la tâche courante pour le tracking automatique
        """
        task = self.get_task(task_id)
        if task:
            self._current_task = task
            logger.debug(f"Tâche courante définie: {task_id}")
        else:
            logger.warning(f"Impossible de définir la tâche courante: {task_id} introuvable")

    def clear_current_task(self):
        """
        🔧 NOUVELLE MÉTHODE : Efface la tâche courante
        """
        self._current_task = None
        logger.debug("Tâche courante effacée")

    def get_current_task(self) -> Optional[QuoteTask]:
        """
        🔧 NOUVELLE MÉTHODE : Récupère la tâche courante
        """
        return getattr(self, '_current_task', None)

    def get_task_statistics(self) -> Dict[str, Any]:
        """
        🔧 NOUVELLE MÉTHODE : Statistiques des tâches
        """
        completed_count = len(self.completed_tasks)
        active_count = len(self.active_tasks)

        # Analyser les statuts des tâches terminées
        success_count = 0
        failed_count = 0

        for task_data in self.completed_tasks:
            if task_data.get("status") == TaskStatus.COMPLETED:
                success_count += 1
            elif task_data.get("status") == TaskStatus.FAILED:
                failed_count += 1

        return {
            "active_tasks": active_count,
            "completed_tasks": completed_count,
            "successful_tasks": success_count,
            "failed_tasks": failed_count,
            "success_rate": (success_count / completed_count * 100) if completed_count > 0 else 0,
            "total_tasks_processed": completed_count + active_count
        }

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """
        🔧 NOUVELLE MÉTHODE : Nettoie les anciennes tâches
        """
        from datetime import datetime, timedelta
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        # Nettoyer les tâches actives anciennes (probablement abandonnées)
        abandoned_tasks = []
        for task_id, task in list(self.active_tasks.items()):
            if task.created_at < cutoff_time:
                abandoned_tasks.append(task_id)
                # Marquer comme échouée et déplacer vers l'historique
                task.fail_task("Tâche abandonnée (timeout)")
                self.completed_tasks.append(task.get_overall_progress())
                del self.active_tasks[task_id]

        if abandoned_tasks:
            logger.info(f"🧹 {len(abandoned_tasks)} tâches abandonnées nettoyées")

        return len(abandoned_tasks)
    def get_task_from_history(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Récupère une tâche depuis l'historique"""
        for completed_task in self.completed_tasks:
            if completed_task.get("task_id") == task_id:
                return completed_task
        return None
# Instance globale du tracker
progress_tracker = ProgressTracker()

# 🔧 FONCTIONS UTILITAIRES POUR LE WORKFLOW

def get_or_create_task(task_id: str = None, user_prompt: str = "", draft_mode: bool = False) -> QuoteTask:
    """
    🔧 NOUVELLE FONCTION : Récupère une tâche existante ou en crée une nouvelle
    """
    if task_id:
        existing_task = progress_tracker.get_task(task_id)
        if existing_task:
            logger.info(f"✅ Tâche existante récupérée: {task_id}")
            return existing_task
        else:
            logger.warning(f"⚠️ Tâche {task_id} introuvable, création d'une nouvelle")

    # Créer une nouvelle tâche
    new_task = progress_tracker.create_task(user_prompt=user_prompt, draft_mode=draft_mode)
    logger.info(f"🆕 Nouvelle tâche créée: {new_task.task_id}")
    return new_task

def track_workflow_step(step_id: str, message: str = "", progress: int = 0, task_id: str = None):
    """
    🔧 NOUVELLE FONCTION : Fonction utilitaire pour tracker une étape de workflow
    """
    if task_id:
        task = progress_tracker.get_task(task_id)
    else:
        task = progress_tracker.get_current_task()

    if task:
        if progress == 0:
            task.start_step(step_id, message)
        elif progress == 100:
            task.complete_step(step_id, message)
        else:
            task.update_step_progress(step_id, progress, message)

        logger.debug(f"📊 Étape {step_id}: {progress}% - {message}")
    else:
        logger.warning(f"⚠️ Impossible de tracker l'étape {step_id}: aucune tâche active")

def get_workflow_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """
    🔧 NOUVELLE FONCTION : Récupère la progression d'un workflow
    """
    task = progress_tracker.get_task(task_id)
    if task:
        return task.get_overall_progress()

    # Chercher dans l'historique
    for completed_task in progress_tracker.completed_tasks:
        if completed_task.get("task_id") == task_id:
            return completed_task

    return None