# services/websocket_manager.py
import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from services.progress_tracker import progress_tracker

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, task_id: str = None):
        """Connecte un WebSocket"""
        await websocket.accept()
        
        # Ajouter à toutes les connexions actives
        if "all" not in self.active_connections:
            self.active_connections["all"] = set()
        self.active_connections["all"].add(websocket)
        
        # Ajouter aux connexions spécifiques à la tâche
        if task_id:
            if task_id not in self.task_connections:
                self.task_connections[task_id] = set()
            self.task_connections[task_id].add(websocket)
            
        logger.info(f"WebSocket connecté pour tâche: {task_id}")
        
    def disconnect(self, websocket: WebSocket, task_id: str = None):
        """Déconnecte un WebSocket"""
        # Retirer de toutes les connexions
        if "all" in self.active_connections:
            self.active_connections["all"].discard(websocket)
            
        # Retirer des connexions spécifiques à la tâche
        if task_id and task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            
        logger.info(f"WebSocket déconnecté pour tâche: {task_id}")
        
    async def send_task_update(self, task_id: str, message: dict):
        """Envoie une mise à jour à tous les clients suivant une tâche"""
        # AJOUT DE LOGS DE DEBUG pour identifier le problème
        logger.warning(f"🔍 DEBUG: Tentative envoi WebSocket pour task_id={task_id}")
        logger.warning(f"🔍 DEBUG: task_connections keys={list(self.task_connections.keys())}")
        logger.warning(f"🔍 DEBUG: Nombre de connexions pour cette tâche: {len(self.task_connections.get(task_id, []))}")
        if task_id not in self.task_connections:
            logger.error(f"❌ PROBLÈME: Aucune connexion WebSocket trouvée pour task_id={task_id}")
            return
            
        # Préparer le message
        message_data = {
            "type": "task_update",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            **message
        }
        
        # Envoyer à tous les clients connectés pour cette tâche
        disconnected = []
        for websocket in self.task_connections[task_id]:
            try:
                await websocket.send_text(json.dumps(message_data))
            except Exception as e:
                logger.error(f"Erreur envoi WebSocket: {e}")
                disconnected.append(websocket)
                
        # Nettoyer les connexions fermées
        for websocket in disconnected:
            self.task_connections[task_id].discard(websocket)
            
    async def send_user_interaction_required(self, task_id: str, interaction_data: dict):
        """Envoie une demande d'interaction utilisateur"""
        await self.send_task_update(task_id, {
            "type": "user_interaction_required",
            "interaction_data": interaction_data
        })
        
    async def send_step_update(self, task_id: str, step_id: str, status: str, message: str, details: dict = None):
        """Envoie une mise à jour d'étape"""
        await self.send_task_update(task_id, {
            "type": "step_update",
            "step_id": step_id,
            "status": status,
            "message": message,
            "details": details or {}
        })

# Instance globale
websocket_manager = WebSocketManager()