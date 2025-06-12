# routes/routes_devis.py
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any

router = APIRouter()

class DevisPromptRequest(BaseModel):
    prompt: str
    draft_mode: bool = False

@router.post("/generate_quote")
async def generate_quote(request: DevisPromptRequest):
    """
    Génère un devis à partir d'une demande en langage naturel
    """
    try:
        from workflow.devis_workflow import DevisWorkflow
        workflow = DevisWorkflow()
        result = await workflow.process_prompt(
            request.prompt, 
            draft_mode=request.draft_mode
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du devis: {str(e)}")

class UpdateQuoteRequest(BaseModel):
    quote_id: str
    products: List[Dict[str, Any]]

@router.post("/update_quote")
async def update_quote(request: UpdateQuoteRequest):
    """
    Met à jour un devis avec les produits modifiés (remplacement d'alternatives)
    """
    try:
        # Rechercher le devis original dans la base de données ou Salesforce
        # Pour le POC, nous allons appeler le workflow de devis
        
        # Calculer le nouveau montant total
        total_amount = sum(
            product.get("quantity", 0) * product.get("unit_price", 0)
            for product in request.products
        )
        
        # Construction de la réponse
        result = {
            "status": "success",
            "quote_id": request.quote_id,
            "quote_status": "Updated",
            "client": {
                "name": "Edge Communications",
                "account_number": "CD451796"
            },
            "products": request.products,
            "total_amount": total_amount,
            "currency": "EUR",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "message": "Devis mis à jour avec succès",
            "all_products_available": True  # Les alternatives sont supposées être disponibles
        }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la mise à jour du devis: {str(e)}")
@router.post("/validate_quote")
async def validate_quote(quote_id: str):
    """Valide un devis brouillon pour le rendre définitif"""
    