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
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        self.pending_messages: Dict[str, List[dict]] = {}

    async def connect(self, websocket: WebSocket, task_id: str = None) -> None:
        """
        Accepte une connexion WebSocket et l'enregistre.

        :param websocket: instance du WebSocket
        :param task_id: identifiant de tâche (optionnel)
        """
        await websocket.accept()
        self.active_connections.setdefault("all", set()).add(websocket)
        if task_id:
            self.task_connections.setdefault(task_id, set()).add(websocket)
        logger.info("WebSocket connecté", extra={"task_id": task_id})

    def disconnect(self, websocket: WebSocket, task_id: str = None) -> None:
        """
        Déconnecte une WebSocket et nettoie les enregistrements.

        :param websocket: instance du WebSocket
        :param task_id: identifiant de tâche (optionnel)
        """
        self.active_connections.get("all", set()).discard(websocket)
        if task_id:
            conns = self.task_connections.get(task_id, set())
            conns.discard(websocket)
            if not conns:
                self.task_connections.pop(task_id, None)
        logger.info("WebSocket déconnecté", extra={"task_id": task_id})

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
                        "Aucune connexion pour tâche après timeout",
                        extra={"task_id": task_id, "timeout": timeout},
                    )
                    return
                await asyncio.sleep(RETRY_INTERVAL)

        sockets = list(self.task_connections.get(task_id) or self.active_connections.get("all", []))
        if not sockets:
            logger.warning("Aucune socket disponible pour broadcast", extra={"task_id": task_id})
            return

        # Validate payload
        try:
            validated = TaskUpdateModel(**{k: message[k] for k in ["type", "task_id", "timestamp"]})
            payload = {**validated.dict(), **{k: v for k, v in message.items() if k not in validated.__fields__}}
        except ValidationError as e:
            logger.error("Payload invalide pour broadcast", exc_info=e)
            return

        # Send and instrument
        for ws in sockets:
            try:
                with WS_SEND_LATENCY.labels(task_id=task_id, type=payload.get("type")).time():
                    await ws.send_text(json.dumps(payload))
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
        message = {
            "type": "user_interaction_required",
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interaction_data": interaction_data,
        }
        # Si pas de connexions, stocker et planifier retry
        if not self.task_connections.get(task_id):
            logger.warning(f"⚠️ Pas de connexion active pour {task_id}, message stocké")
            self.pending_messages.setdefault(task_id, []).append(message)
            # Tentative immédiate de reconnexion
            await self._attempt_reconnection(task_id)
            self._schedule_retry(task_id)
            return
        # Tenter envoi immédiat
        try:
            await self.send_task_update(task_id, message)
            logger.info(f"✅ Interaction envoyée immédiatement pour {task_id}")
        except Exception as e:
            logger.error(f"❌ Erreur envoi initial pour {task_id}: {e}")
            self.pending_messages.setdefault(task_id, []).append(message)
            self._schedule_retry(task_id)

    def _schedule_retry(self, task_id: str) -> None:
        """
        Planifie les tentatives de renvoi des messages en attente.
        """
        async def _attempt_reconnection(task_id: str) -> None:
            """Tentative de reconnexion immédiate pour une tâche"""
            logger.info(f"🔄 Tentative de reconnexion pour {task_id}")

            # Vérifier si la tâche existe toujours
            task = progress_tracker.get_task(task_id)
            if task and task.status.name in ['RUNNING', 'PENDING']:
                # Notifier le frontend qu'une reconnexion est nécessaire
                await self.broadcast_to_task(task_id, {
                    "type": "reconnection_required",
                    "task_id": task_id,
                    "message": "Reconnexion WebSocket requise"
                }, wait=False)

        # Lance la tâche de reconnexion asynchrone
        asyncio.create_task(_attempt_reconnection(task_id))


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
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                except Exception as e:
                    logger.error(f"Erreur notification changement task_id: {e}")

    def cleanup_pending_messages(self, task_id: str):
        """
        Nettoie les messages en attente pour une tâche
        """
        if task_id in self.pending_messages:
            self.pending_messages.pop(task_id, None)
            logger.info(f"🧹 Messages en attente nettoyés pour {task_id}")

# Instance globale
websocket_manager = WebSocketManager()
