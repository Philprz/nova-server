"""
Validateur unifié pour centraliser toutes les validations
"""

import logging
from typing import Dict, Any, Optional
from services.client_validator import ClientValidator
from services.mcp_connector import MCPConnector

logger = logging.getLogger(__name__)

class UnifiedValidator:
    """Validateur centralisé pour toutes les entités"""
    
    def __init__(self):
        self.client_validator = ClientValidator()
        self.cache = {}
    
    async def validate_client_complete(self, client_name: str, create_if_missing: bool = True) -> Dict[str, Any]:
        """
        Validation client unifiée avec création automatique
        """
        # Cache pour éviter les appels multiples
        cache_key = f"client:{client_name}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # 1. Recherche dans Salesforce
            sf_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": f"SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 5"
            })
            
            if "error" not in sf_result and sf_result.get('totalSize', 0) > 0:
                # Client trouvé
                client_data = sf_result['records'][0]
                result = {
                    "found": True,
                    "data": client_data,
                    "source": "salesforce",
                    "validation_method": "direct_match"
                }
                self.cache[cache_key] = result
                return result
            
            # 2. Si pas trouvé et création demandée
            if create_if_missing:
                # Validation enrichie
                validation_result = await self.client_validator.validate_complete({
                    "company_name": client_name,
                    "billing_country": "FR",  # Défaut
                    "email": f"contact@{client_name.lower().replace(' ', '')}.com"
                })
                
                if validation_result.get("valid", False):
                    # Créer dans Salesforce
                    create_result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                        "sobject": "Account",
                        "data": {
                            "Name": client_name,
                            "Type": "Customer",
                            "BillingCountry": "France"
                        }
                    })
                    
                    if "error" not in create_result:
                        result = {
                            "found": True,
                            "data": {
                                "Id": create_result.get("id"),
                                "Name": client_name,
                                "Type": "Customer"
                            },
                            "source": "created",
                            "validation_method": "enriched_creation"
                        }
                        self.cache[cache_key] = result
                        return result
            
            # 3. Client non trouvé
            result = {
                "found": False,
                "error": f"Client '{client_name}' non trouvé",
                "suggestions": []
            }
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Erreur validation client: {e}")
            return {
                "found": False,
                "error": f"Erreur système: {str(e)}"
            }
    
    async def validate_product_complete(self, product_code: str) -> Dict[str, Any]:
        """
        Validation produit unifiée
        """
        cache_key = f"product:{product_code}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Recherche dans SAP
            sap_result = await MCPConnector.call_sap_mcp("sap_get_product_details", {
                "item_code": product_code
            })
            
            if "error" not in sap_result:
                result = {
                    "found": True,
                    "data": sap_result,
                    "source": "sap"
                }
                self.cache[cache_key] = result
                return result
            
            result = {
                "found": False,
                "error": f"Produit '{product_code}' non trouvé"
            }
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Erreur validation produit: {e}")
            return {
                "found": False,
                "error": f"Erreur système: {str(e)}"
            }

# Instance globale
unified_validator = UnifiedValidator()