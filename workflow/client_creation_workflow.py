"""
🏢 Workflow de Création de Client NOVA
=====================================

Workflow intelligent pour créer de nouveaux clients avec :
- Recherche automatique via INSEE (SIRET/SIREN)
- Enrichissement des données via Pappers
- Validation complète des informations
- Intégration avec Salesforce
"""

import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx

from services.client_validator import ClientValidator

logger = logging.getLogger(__name__)

class ClientCreationWorkflow:
    """Workflow complet de création de client avec recherche INSEE/Pappers"""
    
    def __init__(self):
        self.validator = ClientValidator()
        self.pappers_api_key = None  # À configurer si disponible
        
    async def search_company_by_name(self, company_name: str, city: str = None) -> Dict[str, Any]:
        """
        Recherche d'entreprise par nom avec INSEE et Pappers
        """
        logger.info(f"🔍 Recherche d'entreprise: {company_name}")
        
        results = {
            "success": False,
            "companies": [],
            "search_method": "multiple",
            "message": ""
        }
        
        try:
            # 1. Recherche via API Pappers si disponible
            pappers_results = await self._search_pappers(company_name, city)
            if pappers_results.get("companies"):
                results["companies"].extend(pappers_results["companies"])
                results["search_method"] = "pappers"
                logger.info(f"✅ Trouvé {len(pappers_results['companies'])} entreprises via Pappers")
            
            # 2. Si pas de résultats Pappers, essayer une recherche INSEE basique
            if not results["companies"]:
                insee_results = await self._search_insee_basic(company_name)
                if insee_results.get("companies"):
                    results["companies"].extend(insee_results["companies"])
                    results["search_method"] = "insee"
                    logger.info(f"✅ Trouvé {len(insee_results['companies'])} entreprises via INSEE")
            
            if results["companies"]:
                results["success"] = True
                results["message"] = f"Trouvé {len(results['companies'])} entreprise(s) correspondante(s)"
            else:
                results["message"] = "Aucune entreprise trouvée avec ce nom"
                
        except Exception as e:
            logger.error(f"Erreur lors de la recherche d'entreprise: {e}")
            results["message"] = f"Erreur lors de la recherche: {str(e)}"
            
        return results
    
    async def _search_pappers(self, company_name: str, city: str = None) -> Dict[str, Any]:
        """Recherche via API Pappers"""
        # TODO: Implémenter la recherche Pappers si l'API key est disponible
        logger.info("🔍 Recherche Pappers non implémentée (API key manquante)")
        return {"companies": []}
    
    async def _search_insee_basic(self, company_name: str) -> Dict[str, Any]:
        """Recherche basique via INSEE (simulation pour le POC)"""
        # Pour le POC, on simule une recherche INSEE
        # En production, il faudrait utiliser l'API de recherche INSEE
        logger.info("🔍 Recherche INSEE basique (simulation POC)")
        
        # Simulation de résultats pour le POC
        simulated_companies = [
            {
                "siret": "12345678901234",
                "siren": "123456789",
                "company_name": f"{company_name} (Simulation)",
                "activity_code": "6201Z",
                "activity_label": "Programmation informatique",
                "address": "123 Rue de la Technologie",
                "postal_code": "75001",
                "city": "Paris",
                "status": "Actif",
                "creation_date": "2020-01-01",
                "source": "insee_simulation"
            }
        ]
        
        return {"companies": simulated_companies}
    
    async def validate_and_enrich_company(self, siret: str) -> Dict[str, Any]:
        """
        Valide et enrichit les données d'une entreprise via SIRET
        """
        logger.info(f"🔍 Validation et enrichissement SIRET: {siret}")
        
        try:
            # Utiliser la validation SIRET existante
            validation_result = await self.validator._validate_siret_insee(siret)
            
            if validation_result.get("valid"):
                company_data = validation_result.get("data", {})
                
                # Enrichir avec des données supplémentaires
                enriched_data = await self._enrich_company_data(company_data)
                
                return {
                    "success": True,
                    "company_data": enriched_data,
                    "message": "Entreprise validée et enrichie avec succès"
                }
            else:
                return {
                    "success": False,
                    "error": validation_result.get("error", "SIRET invalide"),
                    "message": "Impossible de valider ce SIRET"
                }
                
        except Exception as e:
            logger.error(f"Erreur lors de la validation SIRET: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Erreur lors de la validation"
            }
    
    async def _enrich_company_data(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichit les données d'entreprise avec des informations supplémentaires"""
        
        enriched = company_data.copy()
        
        # Générer un code client suggéré
        company_name = company_data.get("company_name", "")
        if company_name:
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', company_name)[:8].upper()
            timestamp = str(int(datetime.now().timestamp()))[-4:]
            enriched["suggested_client_code"] = f"C{clean_name}{timestamp}"
        
        # Enrichir l'adresse email si possible
        if not enriched.get("email"):
            # Essayer de deviner un email basé sur le nom de l'entreprise
            if company_name:
                domain_guess = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())
                enriched["suggested_email"] = f"contact@{domain_guess}.fr"
        
        # Ajouter des métadonnées
        enriched["enrichment_date"] = datetime.now().isoformat()
        enriched["data_source"] = "insee_api"
        
        return enriched
    
    async def create_client_in_salesforce(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée le client dans Salesforce
        """
        logger.info(f"🏢 Création client Salesforce: {client_data.get('company_name')}")
        
        try:
            # TODO: Implémenter l'intégration Salesforce réelle
            # Pour le POC, on simule la création
            
            # Validation complète des données avant création
            validation_result = await self.validator.validate_complete(client_data)
            
            if not validation_result.get("valid"):
                return {
                    "success": False,
                    "errors": validation_result.get("errors", []),
                    "message": "Données client invalides"
                }
            
            # Simulation de création Salesforce
            client_id = f"001{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            return {
                "success": True,
                "client_id": client_id,
                "account_number": client_data.get("suggested_client_code", client_id),
                "message": "Client créé avec succès dans Salesforce",
                "validation_result": validation_result
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la création client Salesforce: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Erreur lors de la création du client"
            }
    
    async def process_client_creation_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traite une demande complète de création de client
        """
        logger.info("🚀 Début du workflow de création de client")
        
        company_name = request_data.get("company_name", "").strip()
        city = request_data.get("city", "").strip()
        siret = request_data.get("siret", "").strip()
        
        if not company_name and not siret:
            return {
                "success": False,
                "error": "Nom d'entreprise ou SIRET requis",
                "step": "validation_input"
            }
        
        try:
            # Étape 1: Recherche d'entreprise
            if siret:
                # Validation directe par SIRET
                logger.info("📋 Validation directe par SIRET")
                validation_result = await self.validate_and_enrich_company(siret)
                
                if validation_result.get("success"):
                    company_data = validation_result["company_data"]
                    
                    # Étape 2: Création dans Salesforce
                    creation_result = await self.create_client_in_salesforce(company_data)
                    
                    return {
                        "success": creation_result.get("success", False),
                        "step": "client_created" if creation_result.get("success") else "creation_failed",
                        "client_data": company_data,
                        "client_id": creation_result.get("client_id"),
                        "account_number": creation_result.get("account_number"),
                        "message": creation_result.get("message"),
                        "validation_details": creation_result.get("validation_result")
                    }
                else:
                    return {
                        "success": False,
                        "step": "siret_validation_failed",
                        "error": validation_result.get("error"),
                        "message": validation_result.get("message")
                    }
            else:
                # Recherche par nom d'entreprise
                logger.info("🔍 Recherche par nom d'entreprise")
                search_result = await self.search_company_by_name(company_name, city)
                
                if search_result.get("success") and search_result.get("companies"):
                    return {
                        "success": True,
                        "step": "companies_found",
                        "companies": search_result["companies"],
                        "message": search_result["message"],
                        "search_method": search_result["search_method"]
                    }
                else:
                    return {
                        "success": False,
                        "step": "no_companies_found",
                        "message": search_result.get("message", "Aucune entreprise trouvée"),
                        "suggestion": "Essayez avec un SIRET ou vérifiez l'orthographe"
                    }
                    
        except Exception as e:
            logger.error(f"Erreur dans le workflow de création: {e}")
            return {
                "success": False,
                "step": "workflow_error",
                "error": str(e),
                "message": "Erreur interne du workflow"
            }

# Instance globale pour réutilisation
client_creation_workflow = ClientCreationWorkflow()