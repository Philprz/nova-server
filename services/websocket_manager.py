# services/websocket_manager.py
import asyncio
import json
import logging

from datetime import datetime, timezone
from typing import Dict, Set, List
from fastapi import WebSocket, WebSocketDisconnect
from services.progress_tracker import progress_tracker

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        self.pending_messages: Dict[str, List[Dict]] = {}
        self.connection_metadata: Dict[str, Dict] = {}  # 🔧 NOUVEAU
        
    async def connect(self, websocket: WebSocket, task_id: str = None):
        """Connect WebSocket avec métadonnées améliorées"""
        await websocket.accept()

        # Métadonnée timezone-aware
        now = datetime.now(timezone.utc)
        connection_info = {
            "connected_at": now,
            "task_id": task_id,
            "status": "active"
        }

        # Toutes les connexions
        self.active_connections.setdefault("all", set()).add(websocket)

        # Connexions spécifiques
        if task_id:
            self.task_connections.setdefault(task_id, set()).add(websocket)

        # Stocker métadonnées
        websocket_id = id(websocket)
        self.connection_metadata[websocket_id] = connection_info

        logger.info(f"✅ WebSocket connecté pour tâche: {task_id or 'aucune'}")

        # Traitement messages en attente
        if task_id and task_id in self.pending_messages:
            msgs = self.pending_messages[task_id]
            logger.info(f"📬 Envoi {len(msgs)} messages en attente")
            for message in msgs:
                try:
                    await self.send_task_update(task_id, message)
                    logger.info(f"✅ Message en attente envoyé: {message.get('type','unknown')}")
                except Exception as e:
                    logger.error(f"❌ Erreur envoi message en attente: {e}")
            self.pending_messages.pop(task_id, None)
            logger.info(f"🧹 Messages en attente nettoyés pour {task_id}")


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

    async def send_user_interaction_required(self, task_id: str, interaction_data: dict) -> None:
        """Envoie demande d'interaction avec gestion robuste"""

        logger.info(f"🎯 Demande interaction pour task_id: {task_id}")
        message = {
            "type": "user_interaction_required",
            "interaction_data": interaction_data,
            "timestamp": datetime.now().isoformat()
        }

        # Envoyer immédiatement si connexion existante
        connections = self.task_connections.get(task_id, [])
        if connections:
            try:
                await self.send_task_update(task_id, message)
                logger.info(f"✅ Interaction envoyée immédiatement pour {task_id}")
            except Exception as e:
                logger.error(f"❌ Erreur envoi initial pour {task_id}: {e}")
                self.pending_messages.setdefault(task_id, []).append(message)
            return

        # Sinon, mise en attente
        logger.warning(f"⏳ Aucune connexion active pour {task_id}, mise en attente")
        self.pending_messages.setdefault(task_id, []).append(message)

        # Retry automatique avec backoff simple (jusqu'à 30 s)
        delay = 5
        for retry in range(1, 7):
            await asyncio.sleep(delay)
            if self.task_connections.get(task_id):
                logger.info(f"🔄 Connexion détectée au retry {retry}, envoi messages")
                for pending in self.pending_messages.pop(task_id, []):
                    try:
                        await self.send_task_update(task_id, pending)
                        logger.info(f"✅ Message envoyé au retry {retry}: {pending.get('type', 'unknown')}")
                    except Exception as e:
                        logger.error(f"❌ Échec envoi au retry {retry} pour {task_id}: {e}")
                return
            logger.info(f"⏳ Retry {retry}/6 après {delay}s – toujours en attente")
            delay = min(delay * 1.5, 10)  # cap pour éviter trop long

        logger.error(f"❌ ÉCHEC FINAL: Impossible d'envoyer interaction après 6 tentatives")
        
        # Nouveau : Notifier l'échec à l'utilisateur via un autre canal si possible
        try:
            from services.progress_tracker import progress_tracker
            task = progress_tracker.get_task(task_id)
            if task:
                progress_tracker.update_step(task_id, "websocket_timeout", 
                        "error", "❌ Timeout connexion WebSocket", {"retry_count": 6, "total_wait_time": "60s"})
        except Exception as e:
            logger.error(f"Erreur notification échec: {e}")
    
    async def transfer_connection(self, old_task_id: str, new_task_id: str):
            """🔧 NOUVEAU: Transférer connexion d'un task_id à un autre"""
            if old_task_id in self.task_connections:
                connections = self.task_connections[old_task_id].copy()
                
                # Créer nouvelle entrée
                self.task_connections[new_task_id] = connections
                
                # Transférer messages en attente
                if old_task_id in self.pending_messages:
                    self.pending_messages[new_task_id] = self.pending_messages[old_task_id]
                    del self.pending_messages[old_task_id]
                
                # Nettoyer ancienne entrée
                del self.task_connections[old_task_id]
                
                logger.info(f"🔄 Connexions transférées: {old_task_id} → {new_task_id}")
                
                # Notifier les clients du changement
                for websocket in connections:
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "task_id_updated",
                            "old_task_id": old_task_id,
                            "new_task_id": new_task_id,
                            "timestamp": datetime.now().isoformat()
                        }))
                    except Exception as e:
                        logger.error(f"Erreur notification changement task_id: {e}")

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
