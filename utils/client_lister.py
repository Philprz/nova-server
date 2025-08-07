# utils/client_lister.py - VERSION CORRIGÉE
"""
Fonctions utilitaires pour lister tous les clients de Salesforce et SAP
CORRECTION: Traitement approprié des réponses MCP
"""

import logging
import asyncio
from typing import List, Dict, Any
from services.mcp_connector import MCPConnector

logger = logging.getLogger(__name__)

class ClientLister:
    """Classe pour lister les clients des deux systèmes - VERSION CORRIGÉE"""
    
    def __init__(self):
        self.mcp_connector = MCPConnector()
    
    async def get_all_salesforce_clients(self) -> List[Dict[str, Any]]:
        """Récupère tous les comptes Salesforce - CORRIGÉ"""
        logger.info("Récupération de tous les comptes Salesforce...")
        
        try:
            query = """
            SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, 
                   Phone, Fax, Website, Description,
                   BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry,
                   ShippingStreet, ShippingCity, ShippingState, ShippingPostalCode, ShippingCountry,
                   CreatedDate, LastModifiedDate
            FROM Account 
            ORDER BY Name
            """
            
            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp", 
                "salesforce_query",
                {"query": query}
            )
            
            # CORRECTION: Vérifier d'abord si 'success' est False ou 'error' existe
            if result.get("success") is False or "error" in result:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur Salesforce explicite: {error_msg}")
                return []
            
            # CORRECTION: Vérifier 'records' au lieu de success
            if "records" in result:
                clients = result["records"]
                logger.info(f"✅ {len(clients)} comptes Salesforce récupérés")
                return clients
            
            # CORRECTION: Essayer aussi 'data' comme fallback
            if "data" in result:
                clients = result["data"]
                logger.info(f"✅ {len(clients)} comptes Salesforce récupérés (via data)")
                return clients
            
            # Aucun champ attendu trouvé
            logger.warning(f"⚠️ Réponse Salesforce inattendue. Clés disponibles: {list(result.keys())}")
            logger.debug(f"Contenu complet de la réponse: {result}")
            return []
                
        except Exception as e:
            logger.error(f"❌ Exception lors de la récupération Salesforce: {str(e)}")
            return []
    
    async def get_all_sap_clients(self) -> List[Dict[str, Any]]:
        """Récupère tous les clients SAP (BusinessPartners) - CORRIGÉ"""
        logger.info("Récupération de tous les clients SAP...")
        
        try:
            result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_read", 
                {
                    "endpoint": "/BusinessPartners?$filter=CardType eq 'cCustomer'&$orderby=CardCode",
                    "method": "GET"
                }
            )
            
            # CORRECTION: Vérification explicite des erreurs uniquement
            if result.get("error") or result.get("success") is False:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur SAP explicite: {error_msg}")
                return []

            # Extraction des données dans l'ordre de priorité
            if "value" in result and isinstance(result["value"], list):
                clients = result["value"]
                logger.info(f"✅ {len(clients)} clients SAP récupérés")
                return clients
            elif "results" in result and isinstance(result["results"], list):
                clients = result["results"]
                logger.info(f"✅ {len(clients)} clients SAP récupérés (via results)")
                return clients
            elif "data" in result and isinstance(result["data"], list):
                clients = result["data"]
                logger.info(f"✅ {len(clients)} clients SAP récupérés (via data)")
                return clients
            elif isinstance(result, list):
                logger.info(f"✅ {len(result)} clients SAP récupérés (liste directe)")
                return result
            
            # Aucun champ attendu trouvé
            logger.warning(f"⚠️ Réponse SAP inattendue. Clés disponibles: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            logger.debug(f"Contenu complet de la réponse: {result}")
            return []
                
        except Exception as e:
            logger.error(f"❌ Exception lors de la récupération SAP: {str(e)}")
            return []
    
    async def _search_salesforce_by_name(self, client_name: str) -> List[Dict[str, Any]]:
        """Recherche dans Salesforce avec différentes variantes - CORRIGÉ"""
        try:
            # Recherche exacte
            exact_query = f"SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry, Sic FROM Account WHERE Name = '{client_name}' LIMIT 5"
            
            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp",
                "salesforce_query",
                {"query": exact_query}
            )
            
            # CORRECTION: Vérifier d'abord les données, puis les erreurs
            if "records" in result and result["records"]:
                logger.info(f"✅ Recherche exacte Salesforce: {len(result['records'])} résultats")
                return result["records"]
            elif "data" in result and result["data"]:
                logger.info(f"✅ Recherche exacte Salesforce: {len(result['data'])} résultats")
                return result["data"]
            
            # Vérifier les erreurs seulement après avoir testé les données
            if result.get("success") is False or "error" in result:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur recherche exacte Salesforce: {error_msg}")
                # Ne pas retourner ici, continuer avec la recherche approximative
            
            # Si pas de résultat exact, recherche approximative
            fuzzy_query = f"SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry, Sic FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 10"
            
            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp",
                "salesforce_query",
                {"query": fuzzy_query}
            )
            
            # CORRECTION: Même logique pour la recherche approximative
            if "records" in result and result["records"]:
                logger.info(f"✅ Recherche approximative Salesforce: {len(result['records'])} résultats")
                return result["records"]
            elif "data" in result and result["data"]:
                logger.info(f"✅ Recherche approximative Salesforce: {len(result['data'])} résultats")
                return result["data"]
            
            # Vérifier les erreurs
            if result.get("success") is False or "error" in result:
                error_msg = result.get("error", "Erreur inconnue")
                logger.error(f"❌ Erreur recherche approximative Salesforce: {error_msg}")
            else:
                logger.warning(f"⚠️ Aucun client Salesforce trouvé pour '{client_name}'")
            
            logger.info(f"⚠️ Aucun résultat Salesforce pour: {client_name}")
            return []
            
        except Exception as e:
            logger.error(f"❌ Erreur recherche Salesforce: {str(e)}")
            return []
    
    async def _search_sap_by_name(self, client_name: str) -> List[Dict[str, Any]]:
        """Recherche dans SAP avec différentes variantes et diagnostics améliorés"""
        try:
            # Utiliser sap_read avec OData filter au lieu de sap_search
            result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_read",
                {
                    "endpoint": f"/BusinessPartners?$filter=contains(CardName,'{client_name}') or startswith(CardName,'{client_name}')&$top=10",
                    "method": "GET"
                }
            )

            # diagnostics
            logger.debug(f"🔍 Réponse SAP brute pour {client_name}: {result}")
            logger.debug(f"Type de réponse: {type(result)}")
            if isinstance(result, dict):
                logger.debug(f"Clés disponibles: {list(result.keys())}")

            # garde-fou si None ou type inattendu
            if result is None or not isinstance(result, (dict, list)):
                logger.warning(f"⚠️ Résultat SAP invalide pour: {client_name}")
                return []

            # vérification explicite d’erreur
            if isinstance(result, dict) and (result.get("error") or result.get("success") is False):
                logger.warning(f"⚠️ Erreur SAP explicite: {result.get('error', 'Erreur inconnue')}")
                return []

            # parsing adaptatif des clés possibles
            data_keys = ["results", "value", "data", "odata.metadata"]
            clients: List[Dict[str, Any]] = []

            for key in data_keys:
                if isinstance(result, dict) and key in result and isinstance(result[key], list) and result[key]:
                    clients = result[key]
                    logger.info(f"✅ Recherche SAP: {len(clients)} résultats (clé: {key})")
                    break

            # fallback liste directe
            if not clients and isinstance(result, list):
                clients = result
                logger.info(f"✅ Recherche SAP: {len(clients)} résultats (liste directe)")

            # OData imbriqué sous 'd'
            if not clients and isinstance(result, dict) and isinstance(result.get("d"), dict):
                d_obj = result["d"]
                for key in data_keys:
                    if key in d_obj and isinstance(d_obj[key], list) and d_obj[key]:
                        clients = d_obj[key]
                        logger.info(f"✅ Recherche SAP OData: {len(clients)} résultats (d.{key})")
                        break
            # fallback tous les champs contenant des listes imbriquées dans le résultat     
            if not clients and isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, list) and v and any(
                        isinstance(item, dict) and 
                        ('CardCode' in item or 'CardName' in item or 'Name' in item)
                        for item in v[:1]
                    ):
                        clients = v
                        logger.info(f"✅ Recherche SAP: {len(clients)} résultats (clé détectée: {k})")
                        break

            return clients or []

        except Exception as e:
            logger.exception(f"❌ Erreur recherche SAP: {e}")
            return []

    
    async def search_client_by_name(self, client_name: str) -> Dict[str, Any]:
        """Recherche spécifique d'un client par nom dans les deux systèmes - CORRIGÉ"""
        logger.info(f"🔍 Recherche spécifique du client: {client_name}")
        
        result = {
            "search_term": client_name,
            "salesforce": {"found": False, "clients": []},
            "sap": {"found": False, "clients": []},
            "total_found": 0
        }
        
        # Recherche parallèle dans les deux systèmes
        sf_task = self._search_salesforce_by_name(client_name)
        sap_task = self._search_sap_by_name(client_name)
        
        sf_clients, sap_clients = await asyncio.gather(sf_task, sap_task)
        
        # Traitement des résultats Salesforce
        if sf_clients:
            result["salesforce"] = {
                "found": True,
                "clients": sf_clients,
                "count": len(sf_clients)
            }
            result["total_found"] += len(sf_clients)
        
        # Traitement des résultats SAP
        if sap_clients:
            result["sap"] = {
                "found": True, 
                "clients": sap_clients,
                "count": len(sap_clients)
            }
            # Déduplication des clients avant calcul du total
        deduplicated_results = self._deduplicate_clients(sf_clients, sap_clients)
        result["deduplicated_clients"] = deduplicated_results
        result["total_found"] = len(deduplicated_results)
        
        logger.info(f"✅ Recherche terminée: {result['total_found']} clients trouvés")
        return result
    
    def format_client_summary(self, salesforce_clients: List[Dict], sap_clients: List[Dict]) -> Dict[str, Any]:
        """Formate un résumé des clients pour affichage - CORRIGÉ"""
        
        # CORRECTION: Protection contre les clients None ou vides
        sf_clients = salesforce_clients or []
        sap_clients = sap_clients or []
        
        summary = {
            "salesforce": {
                "total": len(sf_clients),
                "sample": sf_clients[:5] if sf_clients else [],
                "names": [c.get("Name", "Sans nom") for c in sf_clients[:10] if c]
            },
            "sap": {
                "total": len(sap_clients),
                "sample": sap_clients[:5] if sap_clients else [],
                "names": [c.get("CardName", "Sans nom") for c in sap_clients[:10] if c]
            },
            "total_combined": len(sf_clients) + len(sap_clients)
        }
        
        return summary
    def _deduplicate_clients(self, sf_clients: List[Dict], sap_clients: List[Dict]) -> List[Dict]:
        """Déduplique les clients basé sur la similarité des noms"""
        from difflib import SequenceMatcher
        
        unique_clients = []
        used_sap_indices = set()
        
        # Traiter clients Salesforce
        for sf_client in sf_clients:
            sf_name = sf_client.get('Name', '').strip().upper()
            
            # Chercher correspondance SAP
            best_match_idx = None
            best_similarity = 0
            
            for idx, sap_client in enumerate(sap_clients):
                if idx in used_sap_indices:
                    continue
                    
                sap_name = sap_client.get('CardName', '').strip().upper()
                similarity = SequenceMatcher(None, sf_name, sap_name).ratio()
                
                if similarity > 0.85 and similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = idx
            
            # Fusionner si correspondance trouvée
            if best_match_idx is not None:
                used_sap_indices.add(best_match_idx)
                unique_clients.append({
                    **sf_client,
                    'sap_data': sap_clients[best_match_idx],
                    'source': 'both',
                    'match_score': best_similarity
                })
            else:
                unique_clients.append({**sf_client, 'source': 'salesforce'})
        
        # Ajouter clients SAP non correspondus
        for idx, sap_client in enumerate(sap_clients):
            if idx not in used_sap_indices:
                unique_clients.append({**sap_client, 'source': 'sap'})
        
        return unique_clients
# Instance globale
client_lister = ClientLister()

# Fonctions pratiques pour utilisation directe - CORRIGÉES
async def list_all_clients() -> Dict[str, Any]:
    """Fonction principale pour lister tous les clients - CORRIGÉE"""
    logger.info("=== DÉMARRAGE LISTING COMPLET DES CLIENTS ===")
    
    # Récupération parallèle des deux systèmes
    sf_task = client_lister.get_all_salesforce_clients()
    sap_task = client_lister.get_all_sap_clients()
    
    salesforce_clients, sap_clients = await asyncio.gather(sf_task, sap_task)
    
    # CORRECTION: Protection contre None
    salesforce_clients = salesforce_clients or []
    sap_clients = sap_clients or []
    
    # Formatage du résumé
    summary = client_lister.format_client_summary(salesforce_clients, sap_clients)
    
    logger.info(f"=== RÉSUMÉ: {summary['total_combined']} clients total ===")
    logger.info(f"    Salesforce: {summary['salesforce']['total']}")
    logger.info(f"    SAP: {summary['sap']['total']}")
    
    return {
        "summary": summary,
        "salesforce_clients": salesforce_clients,
        "sap_clients": sap_clients,
        "timestamp": logger.info("Liste générée")
    }

async def find_client_everywhere(client_name: str) -> Dict[str, Any]:
    """Recherche approfondie d'un client spécifique - CORRIGÉE"""
    return await client_lister.search_client_by_name(client_name)

async def debug_raw_responses(client_name: str = "RONDOT") -> Dict[str, Any]:
    """Fonction de debug pour voir les réponses brutes des API"""
    logger.info(f"=== DEBUG: Réponses brutes pour {client_name} ===")
    
    connector = MCPConnector()
    
    # Test Salesforce
    sf_query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 3"
    sf_result = await connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": sf_query})
    
    # Test SAP
    sap_result = await connector.call_mcp("sap_mcp", "sap_search", {
        "query": client_name,
        "entity_type": "BusinessPartners",
        "limit": 3
    })
    
    debug_info = {
        "salesforce_raw": sf_result,
        "sap_raw": sap_result,
        "salesforce_keys": list(sf_result.keys()) if isinstance(sf_result, dict) else str(type(sf_result)),
        "sap_keys": list(sap_result.keys()) if isinstance(sap_result, dict) else str(type(sap_result))
    }
    
    logger.info(f"SF Keys: {debug_info['salesforce_keys']}")
    logger.info(f"SAP Keys: {debug_info['sap_keys']}")
    
    return debug_info