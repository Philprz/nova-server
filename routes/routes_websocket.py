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
                
                response_data = message.get("data", {})
                await handle_user_response_task(task_id, response_data)

    except WebSocketDisconnect:
        logger.info(f"Client déconnecté du WebSocket pour tâche {task_id}")
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