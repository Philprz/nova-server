# routes/routes_devis.py
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from workflow.devis_workflow import DevisWorkflow

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
        # Vérifier si le mode démonstration est activé

        #demo_mode = "demo" in request.prompt.lower() or "edge" in request.prompt.lower() or "a00001" in request.prompt.lower()
        demo_mode = False  # Forcer mode production
        if demo_mode:
            # Retourner des données simulées
            return {
                "status": "success",
                "quote_id": "DEMO-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
                "quote_status": "Draft",
                "client": {
                    "name": "Edge Communications",
                    "account_number": "CD736025"
                },
                "products": [
                    {
                        "code": "A00001",
                        "name": "Imprimante IBM type Infoprint 1312",
                        "quantity": 500,
                        "unit_price": 399.99,
                        "line_total": 199995.0
                    }
                ],
                "total_amount": 199995.0,
                "currency": "EUR",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "message": "Devis de démonstration créé avec succès",
                "all_products_available": False,
                "unavailable_products": [
                    {
                        "code": "A00001",
                        "name": "Imprimante IBM type Infoprint 1312",
                        "quantity_requested": 500,
                        "quantity_available": 350,
                        "reason": "Stock insuffisant"
                    }
                ],
                "alternatives": {
                    "A00001": [
                        {
                            "ItemCode": "A00002",
                            "ItemName": "Imprimante HP LaserJet 2100TN",
                            "Price": 429.99,
                            "Stock": 600
                        },
                        {
                            "ItemCode": "A00003",
                            "ItemName": "Imprimante Lexmark T640",
                            "Price": 389.99,
                            "Stock": 450
                        }
                    ]
                }
            }
        
        # Sinon, utiliser le workflow normal (qui retourne une erreur pour le moment)
        from workflow.devis_workflow import DevisWorkflow
        workflow = DevisWorkflow()
        result = await workflow.process_prompt(request.prompt)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du devis: {str(e)}")
# routes/routes_devis.py (ajout de la route update_quote)

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
        # Pour le POC, on simulera une mise à jour
        
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
                "account_number": "CD736025"
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