"""
Routes API pour l'agent de recherche d'entreprises dans NOVA
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
import logging

from services.company_search_service import company_search_service

logger = logging.getLogger(__name__)

# Création du router
router = APIRouter(
    prefix="/companies",
    tags=["Recherche d'entreprises"]
)

# Modèles Pydantic
class CompanySearchRequest(BaseModel):
    """Requête de recherche d'entreprise"""
    query: str = Field(..., description="Nom de l'entreprise ou SIREN")
    max_results: int = Field(10, ge=1, le=50, description="Nombre maximum de résultats")

class SirenValidationRequest(BaseModel):
    """Requête de validation SIREN"""
    siren: str = Field(..., description="Numéro SIREN à valider")

class CompanyEnrichmentRequest(BaseModel):
    """Requête d'enrichissement de données client"""
    client_data: Dict[str, Any] = Field(..., description="Données client à enrichir")

class ExportRequest(BaseModel):
    """Requête d'export"""
    companies: List[Dict[str, Any]] = Field(..., description="Liste des entreprises à exporter")
    format: str = Field("json", description="Format d'export (json ou csv)")

@router.post("/search", response_model=Dict[str, Any])
async def search_companies(request: CompanySearchRequest):
    """
    Recherche d'entreprises par nom ou SIREN
    
    Cette route permet de rechercher des entreprises françaises en utilisant :
    - API INSEE (source prioritaire)
    - Base de données locale des grandes entreprises
    - API Pappers (fallback)
    """
    try:
        result = await company_search_service.search_company(
            query=request.query,
            max_results=request.max_results
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur lors de la recherche: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/{query}")
async def search_companies_get(
    query: str,
    max_results: int = Query(10, ge=1, le=50, description="Nombre maximum de résultats")
):
    """
    Recherche d'entreprises par GET (pour faciliter l'intégration)
    """
    try:
        result = await company_search_service.search_company(
            query=query,
            max_results=max_results
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur lors de la recherche: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate_siren", response_model=Dict[str, Any])
async def validate_siren(request: SirenValidationRequest):
    """
    Valide un numéro SIREN selon l'algorithme de Luhn
    """
    try:
        result = await company_search_service.validate_siren(request.siren)
        return result
        
    except Exception as e:
        logger.error(f"Erreur lors de la validation SIREN: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/siren/{siren}")
async def get_company_by_siren(siren: str):
    """
    Récupère les informations d'une entreprise par son SIREN
    """
    try:
        result = await company_search_service.get_company_by_siren(siren)
        
        if not result['success']:
            raise HTTPException(status_code=404, detail=result['error'])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la récupération par SIREN: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/suggestions/{partial_name}")
async def get_suggestions(
    partial_name: str,
    max_suggestions: int = Query(5, ge=1, le=20, description="Nombre maximum de suggestions")
):
    """
    Obtient des suggestions de noms d'entreprises basées sur un nom partiel
    """
    try:
        suggestions = await company_search_service.get_suggestions(
            partial_name=partial_name,
            max_suggestions=max_suggestions
        )
        
        return {
            'success': True,
            'partial_name': partial_name,
            'suggestions': suggestions
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/enrich_client", response_model=Dict[str, Any])
async def enrich_client_data(request: CompanyEnrichmentRequest):
    """
    Enrichit les données client avec les informations de l'agent de recherche
    
    Cette route permet d'enrichir automatiquement les données d'un client
    avec les informations officielles trouvées dans les bases de données
    """
    try:
        enriched_data = await company_search_service.enrich_client_data(
            client_data=request.client_data
        )
        
        return {
            'success': True,
            'enriched_data': enriched_data
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de l'enrichissement: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export")
async def export_companies(request: ExportRequest):
    """
    Exporte les résultats de recherche au format CSV ou JSON
    """
    try:
        filename = await company_search_service.export_search_results(
            results=request.companies,
            format=request.format
        )
        
        return {
            'success': True,
            'filename': filename,
            'format': request.format,
            'count': len(request.companies)
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de l'export: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/stats")
async def get_cache_stats():
    """
    Retourne les statistiques du cache de l'agent
    """
    try:
        stats = await company_search_service.get_cache_stats()
        return stats
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cache")
async def clear_cache():
    """
    Vide le cache de l'agent
    """
    try:
        company_search_service.clear_cache()
        
        return {
            'success': True,
            'message': 'Cache vidé avec succès'
        }
        
    except Exception as e:
        logger.error(f"Erreur lors du vidage du cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """
    Vérifie le statut de santé de l'agent de recherche
    """
    try:
        # Test de base
        test_result = await company_search_service.search_company("test", max_results=1)
        
        return {
            'status': 'healthy',
            'agent_available': test_result.get('success', False),
            'timestamp': test_result.get('timestamp')
        }
        
    except Exception as e:
        logger.error(f"Erreur lors du health check: {e}")
        return {
            'status': 'unhealthy',
            'agent_available': False,
            'error': str(e)
        }

# Route spéciale pour l'intégration avec le workflow NOVA
@router.get("/integration/nova_client_search/{client_name}")
async def nova_client_search(client_name: str):
    """
    Route spéciale pour l'intégration avec le workflow NOVA
    Recherche optimisée pour la validation de clients
    """
    try:
        # Recherche de l'entreprise
        search_result = await company_search_service.search_company(
            query=client_name,
            max_results=5
        )
        
        if not search_result['success']:
            return {
                'found': False,
                'error': search_result.get('error'),
                'suggestions': await company_search_service.get_suggestions(client_name)
            }
        
        companies = search_result['companies']
        
        if not companies:
            return {
                'found': False,
                'suggestions': await company_search_service.get_suggestions(client_name)
            }
        
        # Formatage pour NOVA
        best_match = companies[0]
        
        return {
            'found': True,
            'company': {
                'name': best_match.get('denomination'),
                'siren': best_match.get('siren'),
                'activity': best_match.get('activite_principale'),
                'legal_form': best_match.get('forme_juridique'),
                'status': best_match.get('etat_administratif'),
                'source': best_match.get('source')
            },
            'alternatives': companies[1:] if len(companies) > 1 else [],
            'confidence': 'high' if len(companies) == 1 else 'medium'
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la recherche NOVA: {e}")
        return {
            'found': False,
            'error': str(e),
            'suggestions': []
        }