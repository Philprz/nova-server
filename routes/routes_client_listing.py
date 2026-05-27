# routes/routes_client_listing.py
"""
Routes API pour lister et rechercher les clients dans Salesforce et SAP
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from auth.dependencies import get_current_user
from pydantic import BaseModel

# Import de nos fonctions de listing
from utils.client_lister import list_all_clients, find_client_everywhere, client_lister

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

class ClientSearchRequest(BaseModel):
    client_name: str
    search_mode: str = "comprehensive"  # "comprehensive", "exact", "fuzzy"

@router.get("/list_all_clients")
async def get_all_clients():
    """
    Liste tous les clients de Salesforce et SAP
    """
    try:
        logger.info("🔍 Demande de listing complet des clients")
        
        result = await list_all_clients()
        
        if not result:
            raise HTTPException(status_code=500, detail="Erreur lors de la récupération des clients")
        
        return {
            "success": True,
            "data": result,
            "message": f"Total de {result['summary']['total_combined']} clients récupérés"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du listing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.get("/salesforce_clients")
async def get_salesforce_clients_only():
    """
    Liste uniquement les clients Salesforce
    """
    try:
        logger.info("🔍 Récupération clients Salesforce uniquement")
        
        clients = await client_lister.get_all_salesforce_clients()
        
        return {
            "success": True,
            "source": "salesforce",
            "count": len(clients),
            "clients": clients
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur Salesforce: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur Salesforce: {str(e)}")

@router.get("/sap_clients")
async def get_sap_clients_only():
    """
    Liste uniquement les clients SAP
    """
    try:
        logger.info("🔍 Récupération clients SAP uniquement")
        
        clients = await client_lister.get_all_sap_clients()
        
        return {
            "success": True,
            "source": "sap",
            "count": len(clients),
            "clients": clients
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur SAP: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur SAP: {str(e)}")

@router.get("/search_client/{client_name}")
async def search_specific_client(client_name: str):
    """
    Recherche approfondie d'un client spécifique dans les deux systèmes
    """
    try:
        logger.info(f"🔍 Recherche approfondie du client: {client_name}")
        
        if not client_name or len(client_name.strip()) < 2:
            raise HTTPException(status_code=400, detail="Nom du client trop court (minimum 2 caractères)")
        
        result = await find_client_everywhere(client_name.strip())
        
        return {
            "success": True,
            "search_results": result,
            "found": result["total_found"] > 0,
            "message": f"Recherche terminée - {result['total_found']} clients trouvés"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.post("/search_client_advanced")
async def search_client_advanced(request: ClientSearchRequest):
    """
    Recherche avancée avec options
    """
    try:
        logger.info(f"🔍 Recherche avancée: {request.client_name} (mode: {request.search_mode})")
        
        result = await find_client_everywhere(request.client_name)
        
        # Filtrage selon le mode de recherche
        if request.search_mode == "exact":
            # Garder seulement les correspondances exactes
            sf_exact = [c for c in result["salesforce"]["clients"] 
                       if c.get("Name", "").lower() == request.client_name.lower()]
            sap_exact = [c for c in result["sap"]["clients"] 
                        if c.get("CardName", "").lower() == request.client_name.lower()]
            
            result["salesforce"]["clients"] = sf_exact
            result["sap"]["clients"] = sap_exact
            result["total_found"] = len(sf_exact) + len(sap_exact)
        
        return {
            "success": True,
            "search_mode": request.search_mode,
            "search_results": result,
            "found": result["total_found"] > 0
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche avancée: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.get("/client_summary")
async def get_client_summary():
    """
    Résumé rapide des clients sans récupérer toutes les données
    """
    try:
        logger.info("📊 Génération résumé clients")
        
        # Compter les clients sans récupérer toutes les données
        sf_count_result = await client_lister.mcp_connector.call_mcp(
            "salesforce_mcp",
            "salesforce_query",
            {"query": "SELECT COUNT() FROM Account"}
        )
        
        sap_count_result = await client_lister.mcp_connector.call_mcp(
            "sap_mcp",
            "sap_read",
            {
                "endpoint": "/BusinessPartners/$count?$filter=CardType eq 'cCustomer'",
                "method": "GET"
            }
        )
        
        sf_count = sf_count_result.get("totalSize", 0) if sf_count_result.get("success") else 0
        sap_count = sap_count_result.get("value", 0) if sap_count_result.get("success") else 0
        
        return {
            "success": True,
            "summary": {
                "salesforce_count": sf_count,
                "sap_count": sap_count,
                "total_count": sf_count + sap_count
            },
            "message": "Résumé généré avec succès"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur résumé: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

@router.get("/find_rondot")
async def find_rondot_specifically():
    """
    Endpoint spécifique pour diagnostiquer le problème avec RONDOT
    """
    try:
        logger.info("🔍 DIAGNOSTIC SPÉCIFIQUE - Recherche RONDOT")
        
        result = await find_client_everywhere("RONDOT")
        
        # Log détaillé pour diagnostic
        logger.info(f"=== DIAGNOSTIC RONDOT ===")
        logger.info(f"Salesforce trouvé: {result['salesforce']['found']}")
        logger.info(f"SAP trouvé: {result['sap']['found']}")
        logger.info(f"Total trouvé: {result['total_found']}")
        
        if result["salesforce"]["found"]:
            for client in result["salesforce"]["clients"]:
                logger.info(f"SF Client: {client.get('Name')} (ID: {client.get('Id')})")
        
        if result["sap"]["found"]:
            for client in result["sap"]["clients"]:
                logger.info(f"SAP Client: {client.get('CardName')} (Code: {client.get('CardCode')})")
        
        return {
            "success": True,
            "diagnostic": "RONDOT",
            "search_results": result,
            "debug_info": {
                "sf_found": result["salesforce"]["found"],
                "sap_found": result["sap"]["found"],
                "total": result["total_found"]
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur diagnostic RONDOT: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")