"""
API REST pour la gestion des devis SAP/Salesforce
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel
import logging
import sys
import os

# Ajouter le répertoire parent au path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quote_management.quote_manager import QuoteManager, Quote, QuoteStatus

logger = logging.getLogger(__name__)

# Router FastAPI
router = APIRouter(prefix="/api/quote-management", tags=["Quote Management"])

# Instance du gestionnaire
quote_manager = QuoteManager()


# Modèles Pydantic
class QuoteResponse(BaseModel):
    """Modèle de réponse pour un devis"""
    doc_num: Optional[str] = None
    doc_entry: Optional[str] = None
    opportunity_id: Optional[str] = None
    client_name: str
    client_code: str
    doc_date: Optional[str] = None
    total: float
    status: str
    differences: Optional[List[str]] = None
    can_delete_sap: bool = False
    can_delete_salesforce: bool = False


class QuoteSummaryResponse(BaseModel):
    """Résumé des devis"""
    total_quotes: int
    synced: int
    only_sap: int
    only_salesforce: int
    with_differences: int
    quotes: List[QuoteResponse]


class DeleteRequest(BaseModel):
    """Requête de suppression"""
    quotes: List[Dict[str, str]]  # [{"sap_doc_entry": "123", "sf_opportunity_id": "456"}]


class DeleteResponse(BaseModel):
    """Réponse de suppression"""
    success: bool
    deleted_sap: int
    deleted_salesforce: int
    errors: List[str]


@router.get("/quotes", response_model=QuoteSummaryResponse)
async def get_quotes(
    days_back: int = Query(30, description="Nombre de jours en arrière"),
    status_filter: Optional[str] = Query(None, description="Filtrer par statut")
):
    """
    Récupère et compare les devis SAP et Salesforce
    """
    try:
        logger.info(f"📋 Récupération des devis des {days_back} derniers jours")
        
        # Récupérer les devis des deux systèmes
        sap_quotes = await quote_manager.get_sap_quotes(days_back=days_back)
        sf_opportunities = await quote_manager.get_salesforce_opportunities(days_back=days_back)
        
        # Comparer les devis
        all_quotes = await quote_manager.compare_quotes(sap_quotes, sf_opportunities)
        
        # Filtrer si nécessaire
        if status_filter:
            status_enum = QuoteStatus(status_filter)
            all_quotes = [q for q in all_quotes if q.status == status_enum]
        
        # Convertir en réponse
        quote_responses = []
        for quote in all_quotes:
            response = QuoteResponse(
                doc_num=quote.doc_num,
                doc_entry=quote.doc_entry,
                opportunity_id=quote.opportunity_id,
                client_name=quote.client_name,
                client_code=quote.client_code,
                doc_date=quote.doc_date.strftime("%Y-%m-%d") if quote.doc_date else None,
                total=quote.total,
                status=quote.status.value,
                differences=quote.differences,
                can_delete_sap=(quote.status in [QuoteStatus.ONLY_SAP, QuoteStatus.MISMATCH] and quote.doc_entry is not None),
                can_delete_salesforce=(quote.status in [QuoteStatus.ONLY_SALESFORCE, QuoteStatus.MISMATCH] and quote.opportunity_id is not None)
            )
            quote_responses.append(response)
        
        # Calculer le résumé
        summary = QuoteSummaryResponse(
            total_quotes=len(all_quotes),
            synced=len([q for q in all_quotes if q.status == QuoteStatus.SYNCED]),
            only_sap=len([q for q in all_quotes if q.status == QuoteStatus.ONLY_SAP]),
            only_salesforce=len([q for q in all_quotes if q.status == QuoteStatus.ONLY_SALESFORCE]),
            with_differences=len([q for q in all_quotes if q.status == QuoteStatus.MISMATCH]),
            quotes=quote_responses
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des devis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotes/delete", response_model=DeleteResponse)
async def delete_quotes(request: DeleteRequest):
    """
    Supprime un lot de devis dans SAP et/ou Salesforce
    """
    try:
        logger.info(f"🗑️ Suppression de {len(request.quotes)} devis")
        
        # Appeler la suppression en lot
        result = await quote_manager.delete_quotes_batch(request.quotes)
        
        return DeleteResponse(
            success=result["success"],
            deleted_sap=result["deleted"]["sap"],
            deleted_salesforce=result["deleted"]["salesforce"],
            errors=result["errors"]
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la suppression des devis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/quotes/sap/{doc_entry}")
async def delete_sap_quote(doc_entry: str):
    """
    Supprime un devis spécifique dans SAP
    """
    try:
        result = await quote_manager.delete_sap_quote(doc_entry)
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de la suppression du devis SAP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/quotes/salesforce/{opportunity_id}")
async def delete_salesforce_opportunity(opportunity_id: str):
    """
    Supprime une opportunité spécifique dans Salesforce
    """
    try:
        result = await quote_manager.delete_salesforce_opportunity(opportunity_id)
        if result["success"]:
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de la suppression de l'opportunité Salesforce: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotes/stats")
async def get_quotes_stats(days_back: int = Query(30)):
    """
    Récupère des statistiques sur les devis
    """
    try:
        # Récupérer les devis
        sap_quotes = await quote_manager.get_sap_quotes(days_back=days_back)
        sf_opportunities = await quote_manager.get_salesforce_opportunities(days_back=days_back)
        all_quotes = await quote_manager.compare_quotes(sap_quotes, sf_opportunities)
        
        # Calculer les statistiques
        stats = {
            "period_days": days_back,
            "total_quotes": len(all_quotes),
            "by_status": {
                "synced": len([q for q in all_quotes if q.status == QuoteStatus.SYNCED]),
                "only_sap": len([q for q in all_quotes if q.status == QuoteStatus.ONLY_SAP]),
                "only_salesforce": len([q for q in all_quotes if q.status == QuoteStatus.ONLY_SALESFORCE]),
                "with_differences": len([q for q in all_quotes if q.status == QuoteStatus.MISMATCH])
            },
            "total_value": {
                "all": sum(q.total for q in all_quotes),
                "synced": sum(q.total for q in all_quotes if q.status == QuoteStatus.SYNCED),
                "only_sap": sum(q.total for q in all_quotes if q.status == QuoteStatus.ONLY_SAP),
                "only_salesforce": sum(q.total for q in all_quotes if q.status == QuoteStatus.ONLY_SALESFORCE)
            }
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du calcul des statistiques: {e}")
        raise HTTPException(status_code=500, detail=str(e))