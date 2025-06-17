# services/progress_tracker.py
"""
Système de suivi de progression pour les générations de devis
Réutilise et améliore le pattern du sync_dashboard
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    """Statuts possibles d'une tâche"""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

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
    """Représente une tâche de génération de devis avec tracking détaillé"""
    
    # Définition des étapes métier standard
    BUSINESS_STEPS = {
        "analyze_request": [
            ("parse_prompt", "🔍 Analyse de votre demande"),
            ("extract_entities", "📋 Identification des besoins"), 
            ("validate_input", "✅ Demande comprise")
        ],
        "validate_client": [
            ("search_client", "👤 Recherche du client"),
            ("verify_client_info", "🔍 Vérification des informations"),
            ("client_ready", "✅ Client identifié")
        ],
        "process_products": [
            ("connect_catalog", "🔌 Connexion au catalogue"),
            ("lookup_products", "📦 Vérification des produits"),
            ("check_stock", "📊 Vérification du stock"),
            ("calculate_prices", "💰 Calcul des prix"),
            ("products_ready", "✅ Produits confirmés")
        ],
        "create_quote": [
            ("prepare_quote", "📋 Préparation du devis"),
            ("save_to_sap", "💾 Enregistrement SAP"),
            ("sync_salesforce", "☁️ Synchronisation Salesforce"),
            ("quote_finalized", "✅ Devis finalisé")
        ]
    }

    def __init__(self, task_id: str = None, user_prompt: str = "", draft_mode: bool = False):
        self.task_id = task_id or f"quote_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self.user_prompt = user_prompt
        self.draft_mode = draft_mode
        self.status = TaskStatus.PENDING
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.steps: Dict[str, ProgressStep] = {}
        self.current_step: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        
        # Initialiser toutes les étapes
        self._initialize_steps()
        
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
    
    def update_step_progress(self, step_id: str, progress_percent: int, message: str = "") -> bool:
        """Met à jour la progression d'une étape"""
        if step_id not in self.steps:
            return False
            
        self.steps[step_id].update_progress(progress_percent, message)
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
            "error": self.error
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

class ProgressTracker:
    """Gestionnaire global des tâches de progression"""
    
    def __init__(self):
        self.active_tasks: Dict[str, QuoteTask] = {}
        self.completed_tasks: List[Dict[str, Any]] = []
        self.max_completed_history = 50  # Garder les 50 dernières tâches
    
    def create_task(self, user_prompt: str = "", draft_mode: bool = False) -> QuoteTask:
        """Crée une nouvelle tâche de génération de devis"""
        task = QuoteTask(user_prompt=user_prompt, draft_mode=draft_mode)
        self.active_tasks[task.task_id] = task
        logger.info(f"Nouvelle tâche créée: {task.task_id}")
        return task
    
    def get_task(self, task_id: str) -> Optional[QuoteTask]:
        """Récupère une tâche par son ID"""
        return self.active_tasks.get(task_id)
    
    def complete_task(self, task_id: str, result: Dict[str, Any]):
        """Termine une tâche et la déplace dans l'historique"""
        if task_id not in self.active_tasks:
            return False
            
        task = self.active_tasks[task_id]
        task.complete_task(result)
        
        # Déplacer vers l'historique
        self.completed_tasks.append(task.get_overall_progress())
        
        # Limiter la taille de l'historique
        if len(self.completed_tasks) > self.max_completed_history:
            self.completed_tasks = self.completed_tasks[-self.max_completed_history:]
        
        # Supprimer des tâches actives
        del self.active_tasks[task_id]
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
        return True
    
    def get_all_active_tasks(self) -> List[Dict[str, Any]]:
        """Retourne toutes les tâches actives"""
        return [task.get_overall_progress() for task in self.active_tasks.values()]
    
    def get_task_history(self) -> List[Dict[str, Any]]:
        """Retourne l'historique des tâches terminées"""
        return self.completed_tasks.copy()

# Instance globale du tracker
progress_tracker = ProgressTracker()