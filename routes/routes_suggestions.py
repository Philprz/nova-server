#routes/routes_suggestions.py   
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
from workflow.devis_workflow import DevisWorkflow

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

@router.post("/apply_client_choice")
async def apply_client_choice(request: Dict[str, Any]):
    """Applique le choix utilisateur pour une suggestion client"""
    try:
        workflow = DevisWorkflow()
        result = await workflow.apply_client_suggestion(
            request.get("choice"),
            request.get("workflow_context")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply_product_choices")
async def apply_product_choices(request: Dict[str, Any]):
    """Applique les choix utilisateur pour les suggestions produits"""
    try:
        workflow = DevisWorkflow()
        result = await workflow.apply_product_suggestions(
            request.get("choices"),
            request.get("workflow_context")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))