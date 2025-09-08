from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import asyncio
import logging
from datetime import datetime

from services.websocket_manager import websocket_manager
from services.progress_tracker import progress_tracker
from routes.routes_progress import handle_user_response_task
logger = logging.getLogger(__name__)

router = APIRouter()
@router.websocket("/ws/assistant/{task_id}")
async def websocket_assistant_progress(websocket: WebSocket, task_id: str):
    """WebSocket pour l'assistant intelligent avec gestion des messages"""
    await websocket_manager.connect(websocket, task_id)
    logger.info(f"🔌 Assistant WebSocket connecté pour {task_id}")
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "user_response":
                    logger.info(f"🎯 Traitement user_response pour {task_id}: {message}")
                    response_data = message.get("data", {})
                    await handle_user_response_task(task_id, response_data)
                    
                    await websocket.send_text(json.dumps({
                        "type": "user_response_processed",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                elif message_type == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                else:
                    await websocket.send_text(json.dumps({
                        "type": "echo",
                        "task_id": task_id,
                        "received_type": message_type,
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                    
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "ping",
                    "task_id": task_id,
                    "timestamp": datetime.utcnow().isoformat()
                }))
                continue
                
    except WebSocketDisconnect:
        logger.info(f"🔌 Assistant WebSocket déconnecté pour {task_id}")
    except Exception as e:
        logger.error(f"❌ Erreur WebSocket assistant {task_id}: {str(e)}")
    finally:
        await websocket_manager.disconnect(websocket, task_id)
        
@router.websocket("/ws/task/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket pour suivi en temps réel d'une tâche"""
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
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "user_response":
                logger.info(f"🎯 Réception user_response pour {task_id}: {message}")
                
                response_data = message.get("data", {})
                await handle_user_response_task(task_id, response_data)

    except WebSocketDisconnect:
        # Correction: Appel correct de la méthode disconnect avec les bons paramètres
        await websocket_manager.disconnect(websocket, task_id)


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
        # la méthode est async et attend (websocket, task_id)
        await websocket_manager.disconnect(websocket, client_id)