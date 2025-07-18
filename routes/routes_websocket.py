from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

class WebSocketManager:
    """Gestionnaire WebSocket pour mises à jour temps réel"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.task_subscribers: Dict[str, List[str]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Connecte un client WebSocket"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connecté via WebSocket")
    
    def disconnect(self, client_id: str):
        """Déconnecte un client"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} déconnecté")
    
    async def send_task_update(self, task_id: str, update_data: dict):
        """Envoie mise à jour à tous les abonnés"""
        message = {
            "type": "task_update",
            "task_id": task_id,
            "data": update_data,
            "timestamp": datetime.now().isoformat()
        }
        
        disconnected_clients = []
        for client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Erreur envoi WebSocket à {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Nettoyer clients déconnectés
        for client_id in disconnected_clients:
            self.disconnect(client_id)

# Instance globale
websocket_manager = WebSocketManager()

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Endpoint WebSocket principal"""
    await websocket_manager.connect(websocket, client_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "subscribe":
                task_id = message.get("task_id")
                if task_id:
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "task_id": task_id
                    }))
    
    except WebSocketDisconnect:
        websocket_manager.disconnect(client_id)