# managers/client_manager.py
"""
ClientManager - Gestionnaire dédié aux clients
Extrait et optimisé depuis DevisWorkflow
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

from services.client_validator import ClientValidator
from services.mcp_connector import MCPConnector
from services.suggestion_engine import SuggestionEngine
from services.security_helpers import escape_soql
from utils.common_utils import ResponseBuilder, ErrorHandler
from models.data_models import ClientData, ValidationResult

logger = logging.getLogger(__name__)

class ClientManager:
    """Gestionnaire dédié aux opérations client"""
    
    def __init__(self):
        self.validator = ClientValidator()
        self.mcp_connector = MCPConnector()
        self.suggestion_engine = SuggestionEngine()
        self.response_builder = ResponseBuilder()
        self.error_handler = ErrorHandler()
        
        # Cache simple pour les clients fréquemment utilisés
        self.client_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def find_client(self, client_name: str) -> Dict[str, Any]:
        """
        Recherche un client dans Salesforce et SAP
        
        Args:
            client_name: Nom du client à rechercher
            
        Returns:
            Dict avec les données client ou suggestions
        """
        try:
            logger.info(f"🔍 Recherche client: {client_name}")
            
            # Vérifier le cache
            cache_key = f"client_{client_name.lower()}"
            if cache_key in self.client_cache:
                cached_data = self.client_cache[cache_key]
                if (datetime.now() - cached_data['timestamp']).seconds < self.cache_ttl:
                    logger.info("✅ Client trouvé dans le cache")
                    return cached_data['data']
            
            # Recherche parallèle Salesforce + SAP
            sf_task = self._search_salesforce_client(client_name)
            sap_task = self._search_sap_client(client_name)
            
            sf_result, sap_result = await asyncio.gather(sf_task, sap_task, return_exceptions=True)
            
            # Traitement des résultats
            if isinstance(sf_result, Exception):
                logger.warning(f"Erreur Salesforce: {sf_result}")
                sf_result = {"found": False, "error": str(sf_result)}
            
            if isinstance(sap_result, Exception):
                logger.warning(f"Erreur SAP: {sap_result}")
                sap_result = {"found": False, "error": str(sap_result)}
            
            # Prioriser Salesforce si trouvé
            if sf_result.get("found"):
                result = {
                    "found": True,
                    "data": sf_result["data"],
                    "source": "salesforce",
                    "sap_backup": sap_result.get("data") if sap_result.get("found") else None
                }
            elif sap_result.get("found"):
                result = {
                    "found": True,
                    "data": sap_result["data"],
                    "source": "sap",
                    "needs_salesforce_sync": True
                }
            else:
                # Client non trouvé, générer des suggestions
                result = await self._generate_client_suggestions(client_name)
            
            # Mise en cache
            self.client_cache[cache_key] = {
                'data': result,
                'timestamp': datetime.now()
            }
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur recherche client: {str(e)}")
            return self.error_handler.handle_client_search_error(client_name, str(e))
    
    async def validate_client(self, client_data: Dict[str, Any]) -> ValidationResult:
        """
        Validation complète des données client
        
        Args:
            client_data: Données du client à valider
            
        Returns:
            ValidationResult avec erreurs et suggestions
        """
        try:
            logger.info(f"🔍 Validation client: {client_data.get('company_name', 'N/A')}")
            
            # Validation via le ClientValidator existant
            validation_result = await self.validator.validate_complete(client_data)
            
            # Conversion en modèle typé
            return ValidationResult(
                is_valid=validation_result.get("valid", False),
                errors=validation_result.get("errors", []),
                warnings=validation_result.get("warnings", []),
                suggestions=validation_result.get("suggestions", []),
                enriched_data=validation_result.get("enriched_data", {}),
                duplicate_check=validation_result.get("duplicate_check", {})
            )
            
        except Exception as e:
            logger.exception(f"Erreur validation client: {str(e)}")
            return ValidationResult(
                is_valid=False,
                errors=[f"Erreur de validation: {str(e)}"],
                warnings=[],
                suggestions=[],
                enriched_data={},
                duplicate_check={}
            )
    
    async def create_client(self, client_data: ClientData) -> Dict[str, Any]:
        """
        Création d'un client dans Salesforce et SAP
        
        Args:
            client_data: Données du client à créer
            
        Returns:
            Dict avec le résultat de la création
        """
        try:
            logger.info(f"🆕 Création client: {client_data.name}")
            
            # Validation avant création
            validation = await self.validate_client(client_data.to_dict())
            if not validation.is_valid:
                return self.response_builder.build_error_response(
                    "Validation échouée",
                    f"Erreurs: {', '.join(validation.errors)}"
                )
            
            # Création parallèle dans Salesforce et SAP
            sf_task = self._create_salesforce_client(client_data)
            sap_task = self._create_sap_client(client_data)
            
            sf_result, sap_result = await asyncio.gather(sf_task, sap_task, return_exceptions=True)
            
            # Traitement des résultats
            success_count = 0
            results = {
                "salesforce": {"success": False, "error": None},
                "sap": {"success": False, "error": None}
            }
            
            if not isinstance(sf_result, Exception) and sf_result.get("success"):
                results["salesforce"] = sf_result
                success_count += 1
            elif isinstance(sf_result, Exception):
                results["salesforce"]["error"] = str(sf_result)
            else:
                results["salesforce"]["error"] = sf_result.get("error", "Erreur inconnue")
            
            if not isinstance(sap_result, Exception) and sap_result.get("success"):
                results["sap"] = sap_result
                success_count += 1
            elif isinstance(sap_result, Exception):
                results["sap"]["error"] = str(sap_result)
            else:
                results["sap"]["error"] = sap_result.get("error", "Erreur inconnue")
            
            # Évaluation du succès global
            if success_count == 2:
                status = "complete_success"
                message = "Client créé avec succès dans Salesforce et SAP"
            elif success_count == 1:
                status = "partial_success"
                message = "Client créé partiellement (un système en échec)"
            else:
                status = "complete_failure"
                message = "Échec de création dans tous les systèmes"
            
            # Invalider le cache
            cache_key = f"client_{client_data.name.lower()}"
            if cache_key in self.client_cache:
                del self.client_cache[cache_key]
            
            return {
                "success": success_count > 0,
                "status": status,
                "message": message,
                "results": results,
                "client_data": client_data.to_dict() if success_count > 0 else None
            }
            
        except Exception as e:
            logger.exception(f"Erreur création client: {str(e)}")
            return self.error_handler.handle_client_creation_error(client_data.name, str(e))
    
    async def _search_salesforce_client(self, client_name: str) -> Dict[str, Any]:
        """Recherche dans Salesforce - VERSION CORRIGÉE"""
        try:
            safe_name = escape_soql(client_name)
            
            # 🔧 REQUÊTE CORRIGÉE - CHAMPS VÉRIFIÉS
            query = f"""
                SELECT Id, Name, AccountNumber, Phone, 
                    BillingStreet, BillingCity, BillingPostalCode, BillingCountry,
                    ShippingStreet, ShippingCity, ShippingPostalCode, ShippingCountry,
                    Industry, Type, CreatedDate, LastModifiedDate
                FROM Account 
                WHERE Name LIKE '%{safe_name}%' 
                ORDER BY LastModifiedDate DESC
                LIMIT 1
            """
            
            result = await self.mcp_connector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            if "error" not in result and result.get("records"):
                client_data = result["records"][0]
                return {
                    "found": True,
                    "data": client_data,
                    "source": "salesforce"
                }
            else:
                return {
                    "found": False,
                    "error": result.get("error", "Client non trouvé"),
                    "suggestions": []
                }
                
        except Exception as e:
            logger.exception(f"Erreur recherche Salesforce: {str(e)}")
            return {
                "found": False,
                "error": str(e),
                "suggestions": []
            }

    # 2. AJOUTER MÉTHODE MANQUANTE
    async def search_client(self, client_name: str) -> Dict[str, Any]:
        """Point d'entrée principal recherche client"""
        logger.info(f"🔍 Recherche client: {client_name}")
        
        # Vérifier cache
        cache_key = f"client_{client_name.lower()}"
        if cache_key in self.client_cache:
            cached_data = self.client_cache[cache_key]
            cache_age = (datetime.now() - cached_data['timestamp']).seconds
            if cache_age < 300:  # 5 minutes
                logger.info("Client trouvé en cache")
                return cached_data['data']
        
        # Recherche Salesforce
        sf_result = await self._search_salesforce_client(client_name)
        
        if sf_result.get("found"):
            # Mise en cache
            self.client_cache[cache_key] = {
                'data': sf_result,
                'timestamp': datetime.now()
            }
            return sf_result
        
        # Fallback SAP si nécessaire
        try:
            sap_result = await self._search_sap_client(client_name)
            if sap_result.get("found"):
                sap_result["needs_salesforce_sync"] = True
                return sap_result
        except Exception as e:
            logger.warning("Erreur client_manager: %s", e, exc_info=True)
        
        # Générer suggestions si aucun résultat
        return {
            "found": False,
            "suggestions": await self._generate_client_suggestions(client_name),
            "message": f"Client '{client_name}' non trouvé"
        }
    
    async def _search_sap_client(self, client_name: str) -> Dict[str, Any]:
        """Recherche dans SAP"""
        try:
            result = await self.mcp_connector.call_sap_mcp("sap_search", {
                "query": client_name,
                "entity_type": "BusinessPartners",
                "limit": 1
            })
            
            if "error" not in result and result.get("results"):
                return {
                    "found": True,
                    "data": result["results"][0],
                    "source": "sap"
                }
            else:
                return {
                    "found": False,
                    "error": result.get("error", "Client non trouvé")
                }
                
        except Exception as e:
            logger.exception(f"Erreur recherche SAP: {str(e)}")
            return {"found": False, "error": str(e)}
    
    async def _generate_client_suggestions(self, client_name: str) -> Dict[str, Any]:
        """Génération de suggestions pour client non trouvé"""
        try:
            # Récupération des clients existants pour suggestions
            sf_clients = await self._get_all_salesforce_clients()
            sap_clients = await self._get_all_sap_clients()
            
            all_clients = sf_clients + sap_clients
            
            # Génération des suggestions via le SuggestionEngine
            suggestions = await self.suggestion_engine.suggest_client(client_name, all_clients)
            
            return {
                "found": False,
                "suggestions": suggestions.to_dict() if suggestions.has_suggestions else None,
                "message": f"Client '{client_name}' non trouvé",
                "actions": [
                    {"action": "create_new_client", "label": f"Créer '{client_name}'"},
                    {"action": "search_similar", "label": "Rechercher des clients similaires"},
                    {"action": "manual_entry", "label": "Saisie manuelle"}
                ]
            }
            
        except Exception as e:
            logger.exception(f"Erreur génération suggestions: {str(e)}")
            return {
                "found": False,
                "error": str(e),
                "message": f"Client '{client_name}' non trouvé et erreur lors de la génération de suggestions"
            }
    
    async def _create_salesforce_client(self, client_data: ClientData) -> Dict[str, Any]:
        """Création client dans Salesforce"""
        try:
            sf_data = {
                "Name": client_data.name,
                "Phone": client_data.phone,
                "Email": client_data.email,
                "BillingStreet": client_data.address,
                "BillingCity": client_data.city,
                "BillingCountry": client_data.country,
                "Industry": "Technology",  # Valeur par défaut
                "Type": "Customer"
            }
            
            result = await self.mcp_connector.call_salesforce_mcp("salesforce_create_record", {
                "sobject": "Account",
                "data": sf_data
            })
            
            if "error" not in result:
                return {
                    "success": True,
                    "client_id": result.get("id"),
                    "system": "salesforce",
                    "data": sf_data
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                    "system": "salesforce"
                }
                
        except Exception as e:
            logger.exception(f"Erreur création Salesforce: {str(e)}")
            return {"success": False, "error": str(e), "system": "salesforce"}
    
    async def _create_sap_client(self, client_data: ClientData) -> Dict[str, Any]:
        """Création client dans SAP"""
        try:
            sap_data = {
                "CardName": client_data.name,
                "Phone1": client_data.phone,
                "EmailAddress": client_data.email,
                "Address": client_data.address,
                "City": client_data.city,
                "Country": client_data.country,
                "CardType": "cCustomer",
                "Currency": "EUR"
            }
            
            result = await self.mcp_connector.call_sap_mcp("sap_create_customer_complete", {
                "customer_data": sap_data
            })
            
            if "error" not in result:
                return {
                    "success": True,
                    "client_code": result.get("CardCode"),
                    "system": "sap",
                    "data": sap_data
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                    "system": "sap"
                }
                
        except Exception as e:
            logger.exception(f"Erreur création SAP: {str(e)}")
            return {"success": False, "error": str(e), "system": "sap"}
    
    async def _get_all_salesforce_clients(self) -> List[Dict[str, Any]]:
        """Récupération de tous les clients Salesforce pour suggestions"""
        try:
            result = await self.mcp_connector.get_salesforce_accounts(limit=100)
            return result.get("records", [])
        except Exception as e:
            logger.warning(f"Erreur récupération clients SF: {str(e)}")
            return []
    
    async def _get_all_sap_clients(self) -> List[Dict[str, Any]]:
        """Récupération de tous les clients SAP pour suggestions"""
        try:
            result = await self.mcp_connector.call_sap_mcp("sap_read", {
                "endpoint": "/BusinessPartners?$filter=CardType eq 'cCustomer'&$top=100",
                "method": "GET"
            })
            return result.get("value", [])
        except Exception as e:
            logger.warning(f"Erreur récupération clients SAP: {str(e)}")
            return []
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Statistiques du cache client"""
        return {
            "cache_size": len(self.client_cache),
            "cache_keys": list(self.client_cache.keys()),
            "cache_ttl": self.cache_ttl
        }
    
    def clear_cache(self) -> None:
        """Vider le cache client"""
        self.client_cache.clear()
        logger.info("Cache client vidé")
        