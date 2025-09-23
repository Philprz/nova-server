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
        
        # Vérifier les messages en attente et les traiter (éviter duplications)
        if task_id in self.pending_messages and self.pending_messages[task_id]:
            logger.info(f"📨 {len(self.pending_messages[task_id])} messages en attente pour {task_id}")
            # Récupérer et vider la liste immédiatement 
            pending_msgs = self.pending_messages.pop(task_id, [])
            # Filtrer les messages déjà envoyés pour éviter duplications
            unsent_msgs = [msg for msg in pending_msgs if not msg.get('_sent')]
            if unsent_msgs:
                logger.info(f"📤 Envoi de {len(unsent_msgs)} messages non envoyés (sur {len(pending_msgs)} total)")
                # Envoyer uniquement les messages non envoyés
                for msg in unsent_msgs:
                    try:
                        await self.broadcast_to_task(task_id, msg, wait=False)
                        logger.info(f"📤 Message en attente envoyé pour {task_id}")
                    except Exception as e:
                        logger.error(f"Erreur lors de l'envoi du message en attente : {e}")
            else:
                logger.info(f"🚫 Tous les messages étaient déjà envoyés - aucune duplication")
        logger.info("WebSocket connecté", extra={"task_id": task_id})

    async def disconnect(self, websocket: "WebSocket", task_id: str = None) -> None:
        """
        Déconnecte un WebSocket et nettoie les références.
        """
        try:
            if task_id:
                self.task_connections.get(task_id, set()).discard(websocket)
            self.active_connections.get("all", set()).discard(websocket)
            
            # Fermer proprement la connexion si encore ouverte
            if websocket.client_state == websocket.client_state.CONNECTED:
                await websocket.close()
                
        except Exception as e:
            logger.error(f"Erreur lors de la déconnexion WebSocket: {e}")
    
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
        self,
        task_id: str,
        interaction_data: Dict[str, Any],
    ) -> None:
        """
        Envoie une demande d'interaction utilisateur via WebSocket, avec gestion robuste :
        - normalisation du type de message
        - auto-sélection si une seule option (ex: 1 seul client)
        - stockage si aucune connexion active + retries
        - déduplication des messages en attente
        - validations d'entrée (task_id, dict) et copie défensive
        """
        # ✅ Validations d'entrée
        if not task_id:
            logger.error("❌ send_user_interaction_required appelé sans task_id")
            return
        if not isinstance(interaction_data, dict):
            logger.error(f"❌ interaction_data invalide (type={type(interaction_data)})")
            return

        # ✅ Copie défensive pour éviter de muter l'objet du caller
        interaction = dict(interaction_data)

        # 🔎 Logs de contexte (résilients)
        logger.info(f"🎯 Demande interaction pour task_id: {task_id}")
        try:
            total_all = len(self.active_connections.get("all", [])) if hasattr(self, "active_connections") else 0
            logger.debug(f"🔗 DEBUG CONNEXIONS TOTALES: {total_all}")
            logger.debug(f"🔗 DEBUG TASK_CONNECTIONS: {list(getattr(self, 'task_connections', {}).keys())}")
            logger.debug(f"🔗 DEBUG CONNEXIONS pour {task_id}: {len(getattr(self, 'task_connections', {}).get(task_id, []))}")
        except Exception as e:
            logger.debug(f"ℹ️ Impossible d'afficher l'état des connexions: {e}")

        # 🧭 Normalisation du type d'interaction
        interaction_type = interaction.get("interaction_type") or interaction.get("type") or "non_spécifié"
        interaction["interaction_type"] = interaction_type  # on force la clé attendue côté UI
        logger.info(f"📊 Type d'interaction: {interaction_type}")

        # 🆕 Auto-sélection : si 1 seule option client, ne pas envoyer de message WS
        if interaction_type == "client_selection":
            client_options = interaction.get("client_options") or []
            if isinstance(client_options, list) and len(client_options) == 1:
                logger.info("🚀 Auto-sélection détectée - 1 seul client disponible, pas d'envoi WebSocket")
                return
            if not isinstance(client_options, list):
                # ✅ Normaliser en liste si mauvaise forme
                client_options = [client_options]
                interaction["client_options"] = client_options

        # 📋 Logs détaillés des options client (si présentes)
        client_options = interaction.get("client_options") or []
        if isinstance(client_options, list) and client_options:
            logger.info(f"📊 Nombre de clients: {len(client_options)}")
            for i, client in enumerate(client_options, start=1):
                name = (client or {}).get("display_name") or (client or {}).get("CardName") or (client or {}).get("name") or "?"
                source = (client or {}).get("source") or (client or {}).get("origin") or "n/c"
                logger.info(f"📊 Client {i}: {name} (source={source})")
        else:
            try:
                default_serializer = globals().get("json_serializer", str)
                logger.warning("⚠️ Pas de client_options dans interaction: " + json.dumps(interaction, indent=2, default=default_serializer))
            except Exception:
                logger.warning("⚠️ Pas de client_options dans interaction (dump impossible)")

        # 📨 Message normalisé pour le front
        message: Dict[str, Any] = {
            "type": "user_interaction_required",  # ⚖️ normalisation côté front
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interaction_data": interaction,
        }

        try:
            logger.info("📨 Message WebSocket préparé: " + json.dumps(message, indent=2, default=str))
        except Exception:
            logger.info("📨 Message WebSocket préparé (dump simplifié - objets non sérialisables)")

        # 🛡️ Déduplication courte (≤2s) AVANT tout envoi/stockage :
        #    même type + même interaction_type déjà émis ou en attente pour ce task_id
        try:
            current_time = datetime.now(timezone.utc)
            pending = getattr(self, "pending_messages", {}).get(task_id, [])
            recent_map = getattr(self, "_recent_emitted", {})
            recent_for_task = recent_map.get(task_id, [])

            msg_type = message.get("type")
            msg_inter_type = (message.get("interaction_data") or {}).get("interaction_type") or "unknown"

            def _is_same(m):
                return (m.get("type") == msg_type) and ((m.get("interaction_data") or {}).get("interaction_type") == msg_inter_type)

            # messages en attente (pending) OU récemment émis (≤2s)
            in_pending = any(_is_same(m) for m in pending)
            in_recent = any(
                _is_same(m) and (
                    current_time - datetime.fromisoformat(
                        m.get("timestamp", "1970-01-01T00:00:00+00:00").replace('Z', '+00:00')
                    )
                ).total_seconds() < 2
                for m in recent_for_task
            )

            if in_pending or in_recent:
                logger.info(f"⏱️ Doublon {msg_type}/{msg_inter_type} ignoré (<2s) pour {task_id}")
                return
        except Exception as _e:
            logger.debug(f"Déduplication courte non appliquée: {_e}")

        # 📦 Si aucune connexion active sur ce task_id : stocker + tenter reconnection + programmer retry
        has_connections = bool(getattr(self, "task_connections", {}).get(task_id))
        if not has_connections:
            pending = getattr(self, "pending_messages", {}).get(task_id, [])
            # Déduplication simple : même type + même interaction_type
            msg_type = message.get("type")
            msg_inter_type = (message.get("interaction_data") or {}).get("interaction_type")
            message_exists = any(
                (m.get("type") == msg_type) and ((m.get("interaction_data") or {}).get("interaction_type") == msg_inter_type)
                for m in pending
            )

            if not message_exists:
                logger.warning(f"⚠️ Pas de connexion active pour {task_id}, message stocké")
                self.pending_messages.setdefault(task_id, []).append(message)
            else:
                logger.info(f"📨 Message similaire déjà en attente pour {task_id}, on évite la duplication")

            # (Optionnel) Vérifier existence de la tâche si un tracker est utilisé
            try:
                progress_tracker = globals().get("progress_tracker")
                if progress_tracker:
                    _ = progress_tracker.get_task(task_id)  # lecture passive
            except Exception as e:
                logger.debug(f"ℹ️ progress_tracker indisponible: {e}")

            # Tenter reconnection + programmer retry
            try:
                await self._attempt_reconnection(task_id)
            except Exception as e:
                logger.debug(f"ℹ️ _attempt_reconnection a échoué/indispo: {e}")

            try:
                self._schedule_retry(task_id)
            except Exception as e:
                logger.debug(f"ℹ️ _schedule_retry indisponible: {e}")

            # 🔁 Mémoriser dans le buffer des messages émis récents (pour la fenêtre de 2s)
            try:
                recent_map = getattr(self, "_recent_emitted", {})
                recent_for_task = recent_map.setdefault(task_id, [])
                recent_for_task.append(message)
                # purge minimale des anciens (> 10s) pour ne pas grossir la mémoire
                ten_secs_ago = datetime.now(timezone.utc).timestamp() - 10
                def _ts_iso_to_epoch(ts):
                    return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
                recent_for_task[:] = [m for m in recent_for_task if _ts_iso_to_epoch(m.get("timestamp", "")) >= ten_secs_ago]
                self._recent_emitted = recent_map
            except Exception as _e:
                logger.debug(f"recent_emitted non mis à jour: {_e}")

            return


        # 🚚 Envoi immédiat si connexion(s) active(s)
        try:
            nb = len(self.task_connections.get(task_id, []))
            logger.info(f"🔗 Connexions actives pour {task_id}: {nb}")
            # broadcast_to_task envoie le payload tel quel (évite double enveloppe)
            await self.broadcast_to_task(task_id, message, wait=False)
            logger.info(f"✅ Interaction envoyée immédiatement pour {task_id}")
            message["_sent"] = True  # marquer envoyé (utile si re-usage interne)
        except Exception as e:
            logger.error(f"❌ Erreur envoi initial pour {task_id}: {e}")
            # Stocker pour retry seulement si non envoyé
            if not message.get("_sent"):
                try:
                    self.pending_messages.setdefault(task_id, []).append(message)
                    self._schedule_retry(task_id)
                except Exception as ee:
                    logger.error(f"❌ Impossible de stocker/programmer retry pour {task_id}: {ee}")


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
                    # Filtrer les messages déjà envoyés
                    unsent_msgs = [msg for msg in pending if not msg.get('_sent')]
                    for msg in unsent_msgs:
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

