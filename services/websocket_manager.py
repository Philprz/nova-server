# main.py
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Set, List, Optional

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Extra, ValidationError
from prometheus_client import Counter, Histogram
from services.progress_tracker import progress_tracker

# Constants
DEFAULT_TIMEOUT = 30.0
RETRY_INTERVAL = 0.1
MAX_RETRIES = 6
INITIAL_DELAY = 5.0

# Metrics
WS_MESSAGES_SENT = Counter(
    "ws_messages_sent_total", "Total number of WebSocket messages sent", ["task_id", "type"]
)
WS_SEND_LATENCY = Histogram(
    "ws_send_latency_seconds", "Latency of WebSocket send operations", ["task_id", "type"]
)

logger = logging.getLogger(__name__)

def json_serializer(obj):
    """Sérialiseur JSON pour gérer les types datetime"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")
class TaskUpdateModel(BaseModel, extra=Extra.forbid):
    type: str
    task_id: str
    timestamp: datetime


class UserInteractionModel(TaskUpdateModel):
    interaction_data: dict


class StepUpdateModel(TaskUpdateModel):
    step_id: str
    status: str
    message: str
    details: dict = {}


class WebSocketManager:
    """
    Gère les connexions WebSocket pour diffusion par tâche.
    """

    def __init__(self) -> None:
        # 'all' regroupe toutes les connexions actives
        self.active_connections: Dict[str, Set["WebSocket"]] = {"all": set()}
        self.task_connections: Dict[str, Set["WebSocket"]] = {}
        self.pending_messages: Dict[str, List[dict]] = {}

    async def connect(self, websocket: "WebSocket", task_id: str = None) -> None:
        """
        Accepte une connexion WebSocket et l'enregistre.
            :param websocket: instance du WebSocket
            :param task_id: identifiant de tâche (optionnel)
            """
        await websocket.accept()
        logger.info(f"🔌 WebSocket ACCEPTÉ pour task_id: {task_id}")
        
        # Enregistrer la connexion immédiatement  
        self.active_connections.setdefault("all", set()).add(websocket)
        if task_id:
            self.task_connections.setdefault(task_id, set()).add(websocket)
            logger.info(f"✅ WebSocket AJOUTÉ - Connexions pour {task_id}: {len(self.task_connections[task_id])}")
        
        # Vérifier les messages en attente
        if task_id in self.pending_messages:
            logger.info(f"📨 {len(self.pending_messages[task_id])} messages en attente pour {task_id}")
            # Envoyer chaque message puis vider la liste
            for msg in self.pending_messages[task_id]:
                try:
                    await self.broadcast_to_task(task_id, msg, wait=False)
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi du message en attente : {e}")
            self.pending_messages[task_id] = []
        logger.info("WebSocket connecté", extra={"task_id": task_id})

    async def disconnect(self, websocket: "WebSocket", task_id: str):
        """Déconnecte proprement un WebSocket"""
        try:
            conns = self.task_connections.get(task_id)
            if conns and websocket in conns:
                conns.discard(websocket)
                logger.info(f"✅ WebSocket RETIRÉ de {task_id}")
                self.active_connections.get("all", set()).discard(websocket)
        except Exception as e:
            logger.error(f"❌ Erreur lors de la déconnexion WebSocket: {e}")
    
    async def broadcast_to_task(
        self,
        task_id: str,
        message: dict,
        wait: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Diffuse un message JSON-validé aux WebSockets d'une tâche.

        :param task_id: identifiant de la tâche
        :param message: payload dict
        :param wait: attendre une connexion active
        :param timeout: délai d'attente maximal
        """


        if wait:
            start = time.monotonic()
            while not self.task_connections.get(task_id):
                if time.monotonic() - start > timeout:
                    logger.warning(
                        "Aucune connexion pour tâche après timeout, message stocké pour task_id=%s", task_id
                    )
                    # Stockage automatique dans la file d'attente
                    self.pending_messages.setdefault(task_id, []).append(message)
                    return
                await asyncio.sleep(RETRY_INTERVAL)

        sockets = list(self.task_connections.get(task_id) or self.active_connections.get("all", []))
        logger.debug(f"🔍 DEBUG BROADCAST: task_id={task_id}")
        logger.debug(f"🔍 DEBUG BROADCAST: task_connections keys={list(self.task_connections.keys())}")
        logger.debug(f"🔍 DEBUG BROADCAST: sockets pour {task_id}={len(sockets)}")
        if not sockets:
            logger.warning("Aucune socket disponible pour broadcast", extra={"task_id": task_id})
            return
        # Normaliser la présence de 'timestamp'
        if 'timestamp' not in message:
            message['timestamp'] = datetime.now(timezone.utc).isoformat()
        # Validate payload
        # CORRECTION: Assurer la présence du task_id dans le message
        if 'task_id' not in message:
            message['task_id'] = task_id
        
        # Validate payload
        try:
            # Assurer la présence des champs requis
            if 'task_id' not in message:
                message['task_id'] = task_id
            if 'type' not in message:
                message['type'] = 'task_update'
                
            validated = TaskUpdateModel(**{k: message[k] for k in ["type", "task_id", "timestamp"]})
            payload = {**validated.dict(), **{k: v for k, v in message.items() if k not in validated.__fields__}}
        except ValidationError as e:
            logger.error(f"Payload invalide pour broadcast: {e}", extra={"task_id": task_id})
            return
        except Exception as e:
            logger.error(f"Erreur validation payload: {e}", extra={"task_id": task_id})
            return

        # Send and instrument
        for ws in sockets:
            try:
                with WS_SEND_LATENCY.labels(task_id=task_id, type=payload.get("type")).time():
                    await ws.send_text(json.dumps(payload, default=json_serializer))
                WS_MESSAGES_SENT.labels(task_id=task_id, type=payload.get("type")).inc()
            except WebSocketDisconnect:
                logger.info("Client déconnecté proprement", extra={"task_id": task_id})
                self._cleanup_ws(ws, task_id)
            except asyncio.TimeoutError:
                logger.error("Envoi WebSocket timeout", extra={"task_id": task_id})
                self._cleanup_ws(ws, task_id)
            except Exception:
                logger.exception("Erreur inattendue lors de l'envoi WebSocket", extra={"task_id": task_id})
                self._cleanup_ws(ws, task_id)

    def _cleanup_ws(self, websocket: WebSocket, task_id: str) -> None:
        """
        Nettoie une connexion WebSocket des enregistrements.
        """
        self.task_connections.get(task_id, set()).discard(websocket)
        self.active_connections.get("all", set()).discard(websocket)

    async def send_task_update(
        self,
        task_id: str,
        message: dict,
        wait: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Prépare et envoie un événement de type 'task_update'.
        """
        message_data = {
            "type": "task_update",
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **message,
        }
        await self.broadcast_to_task(task_id, message_data, wait, timeout)

    async def send_user_interaction_required(
        self, task_id: str, interaction_data: dict
    ) -> None:
        """
        Envoie demande d'interaction avec gestion robuste.

        :param task_id: identifiant de la tâche
        :param interaction_data: données pour l'interaction utilisateur
        """
        logger.info(f"🎯 Demande interaction pour task_id: {task_id}")
        # 🔧 DEBUG CONNEXIONS: État actuel du gestionnaire
        logger.debug(f"🔗 DEBUG CONNEXIONS TOTALES: {len(self.active_connections.get('all', []))}")
        logger.debug(f"🔗 DEBUG TASK_CONNECTIONS: {list(self.task_connections.keys())}")
        logger.debug(f"🔗 DEBUG CONNEXIONS pour {task_id}: {len(self.task_connections.get(task_id, []))}")
        # 🔧 DEBUG AMÉLIORÉ: Log des données d'interaction
        logger.info(f"📊 Type d'interaction: {interaction_data.get('interaction_type', 'non_spécifié')}")
        # 🆕 VÉRIFICATION AUTO-SÉLECTION - Éviter l'envoi si une seule option
        if interaction_data.get('interaction_type') == 'client_selection':
            client_options = interaction_data.get('client_options', [])
            if len(client_options) == 1:
                logger.info(f"🚀 Auto-sélection détectée - 1 seul client disponible, pas d'envoi WebSocket")
                return  # Ne pas envoyer d'interaction si auto-sélection possible
                
        elif interaction_data.get('interaction_type') == 'product_selection':
            product_options = interaction_data.get('options', [])
            if len(product_options) == 1:
                logger.info(f"🚀 Auto-sélection détectée - 1 seul produit disponible, pas d'envoi WebSocket") 
                return  # Ne pas envoyer d'interaction si auto-sélection possible
        if interaction_data.get('client_options'):
            logger.info(f"📊 Nombre de clients: {len(interaction_data.get('client_options', []))}")
            for i, client in enumerate(interaction_data.get('client_options', [])):
                logger.info(f"📊 Client {i+1}: {client.get('name')} ({client.get('source')})")
        else:
            logger.warning(f"⚠️ Pas de client_options dans interaction_data: {json.dumps(interaction_data, indent=2, default=json_serializer)}")

        message = {
            "type": "user_interaction_required",
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interaction_data": interaction_data,
        }

        logger.info(f"📨 Message WebSocket préparé: {json.dumps(message, indent=2, default=str)}")
        # Toujours enrichir le message avec un timestamp
        if 'timestamp' not in message:
            message['timestamp'] = datetime.now(timezone.utc).isoformat()


        # Si pas de connexions, stocker et planifier retry
        if not self.task_connections.get(task_id):
            
            logger.warning(f"⚠️ Pas de connexion active pour {task_id}, message stocké")
            self.pending_messages.setdefault(task_id, []).append(message)
            # Vérifier si la tâche existe dans le progress_tracker
            task = progress_tracker.get_task(task_id)

            await self._attempt_reconnection(task_id)
            self._schedule_retry(task_id)
            return
        # Tenter envoi immédiat
        try:
            logger.info(f"🔗 Connexions actives pour {task_id}: {len(self.task_connections.get(task_id, []))}")
            await self.send_task_update(task_id, message)
            logger.info(f"✅ Interaction envoyée immédiatement pour {task_id}")
        except Exception as e:
            logger.error(f"❌ Erreur envoi initial pour {task_id}: {e}")
            self.pending_messages.setdefault(task_id, []).append(message)
            self._schedule_retry(task_id)

    async def _attempt_reconnection(self, task_id: str) -> None:
        """Tentative de reconnexion immédiate pour une tâche"""
        logger.info(f"🔄 Tentative de reconnexion pour {task_id}")

        # Vérifier si la tâche existe toujours
        task = progress_tracker.get_task(task_id)
        if task and task.status.name in ['RUNNING', 'PENDING']:
            # Notifier le frontend qu'une reconnexion est nécessaire
            # Ajouter un 'timestamp' au message de reconnexion si absent
            recon_msg = {
                "type": "reconnection_required",
                "task_id": task_id,
                "message": "Reconnexion WebSocket requise"
            }
            if 'timestamp' not in recon_msg:
                recon_msg['timestamp'] = datetime.now(timezone.utc).isoformat()
            await self.broadcast_to_task(task_id, recon_msg)


    def _schedule_retry(self, task_id: str) -> None:
        # Requiert une reconnexion côté client ET tente périodiquement d'envoyer les messages en attente
        asyncio.create_task(self._attempt_reconnection(task_id))
        asyncio.create_task(self._retry_pending(task_id))


    async def _retry_pending(self, task_id: str) -> None:
        """
        Tente d'envoyer les messages stockés avec back-off jusqu'à échec ou succès.
        """
        delay = INITIAL_DELAY
        delay = 2.0  # Démarrer avec un délai plus court
        for retry in range(1, MAX_RETRIES + 1):
            await asyncio.sleep(delay)
            sockets = self.task_connections.get(task_id)
            if sockets:
                pending = self.pending_messages.pop(task_id, [])
                for msg in pending:
                    try:
                        await self.send_task_update(task_id, msg)
                        logger.info(
                            f"✅ Message envoyé au retry {retry} pour {task_id}: {msg.get('type')}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Échec au retry {retry} pour {task_id}: {e}"
                        )
                return
            delay = min(delay * 1.2, 15)  # Progression plus douce, maximum plus élevé
            logger.info(f"⏳ Retry {retry}/{MAX_RETRIES} après {delay:.1f}s – pas encore connecté")
            
            
        logger.error(f"❌ ÉCHEC FINAL: Impossible d'envoyer {task_id} après {MAX_RETRIES} tentatives")
        # Notification d'échec
        try:
            task = progress_tracker.get_task(task_id)
            if task:
                task.fail_step("websocket_timeout", "❌ Timeout connexion WebSocket")
        except Exception as e:
            logger.error(f"Erreur notification échec: {e}")

    async def send_step_update(
        self,
        task_id: str,
        step_id: str,
        status: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        """
        Envoie une mise à jour d'une étape spécifique.
        """
        await self.send_task_update(
            task_id,
            {
                "type": "step_update",
                "step_id": step_id,
                "status": status,
                "message": message,
                "details": details or {},
            },
        )

    async def transfer_connection(self, old_task_id: str, new_task_id: str):
        """
        Transférer connexion d'un task_id à un autre
        """
        if old_task_id in self.task_connections:
            connections = self.task_connections[old_task_id].copy()
            # Créer nouvelle entrée
            self.task_connections[new_task_id] = connections
            # Transférer messages en attente
            if old_task_id in self.pending_messages:
                self.pending_messages[new_task_id] = self.pending_messages.pop(old_task_id)
            # Nettoyer ancienne entrée
            self.task_connections.pop(old_task_id)
            logger.info(f"🔄 Connexions transférées: {old_task_id} → {new_task_id}")
            # Notifier les clients du changement
            for websocket in connections:
                try:
                    await websocket.send_text(json.dumps({
                        "type": "task_id_updated",
                        "old_task_id": old_task_id,
                        "new_task_id": new_task_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, default=json_serializer))
                except Exception as e:
                    logger.error(f"Erreur notification changement task_id: {e}")


    def cleanup_pending_messages(self, task_id: str):
        """
        Nettoie les messages en attente pour une tâche
        """
        if task_id in self.pending_messages:
            self.pending_messages.pop(task_id, None)
            logger.info(f"🧹 Messages en attente nettoyés pour {task_id}")
            
    async def close_task_connections(self, task_id: str):
        """Ferme proprement toutes les connexions WebSocket d'une tâche"""
        if task_id not in self.task_connections:
            return
        
        connections = self.task_connections[task_id].copy()
        for websocket in connections:
            try:
                # Envoyer notification finale
                await websocket.send_text(json.dumps({
                    "type": "task_completed",
                    "task_id": task_id,
                    "message": "Tâche terminée - connexion fermée",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, default=json_serializer))
                # Fermer la connexion
                await websocket.close()
            except Exception as e:
                logger.error(f"Erreur fermeture WebSocket: {e}")
        
        # Nettoyer les références
        self.task_connections.pop(task_id, None)
        self.pending_messages.pop(task_id, None)
        logger.info(f"🧹 Connexions WebSocket fermées pour {task_id}")
# Instance globale
websocket_manager = WebSocketManager()

