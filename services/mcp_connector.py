# services/mcp_connector.py - VERSION COMPLÈTE CORRIGÉE SANS SUPPRESSION DE FONCTIONNALITÉS

import os
import sys
import json
import asyncio
import subprocess
import tempfile
from typing import Dict, Any, List, Optional
import logging
from services.cache_manager import RedisCacheManager

logger = logging.getLogger("mcp_connector")
def get_timeout_for_action(action):
    """Retourne le timeout approprié selon l'action"""
    timeouts = {
        'salesforce_query': 60,  # Recherche peut être lente
        'sap_read': 45,         # Lecture SAP
        'sap_search': 60,       # Recherche SAP
        'ping': 10              # Test rapide
    }
    return timeouts.get(action, 30)  # Default 30s
class MCPCache:
    """Cache intelligent pour les appels MCP"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = {}
        from datetime import datetime, timedelta
        self.default_ttl = timedelta(minutes=5)
    
    def get(self, key: str):
        """Récupère une valeur du cache si elle n'est pas expirée"""
        if key in self.cache:
            from datetime import datetime
            if datetime.now() < self.cache_ttl.get(key, datetime.min):
                return self.cache[key]
            else:
                # Nettoyer les entrées expirées
                del self.cache[key]
                del self.cache_ttl[key]
        return None
    
    def set(self, key: str, value, ttl=None):
        """Stocke une valeur dans le cache"""
        from datetime import datetime
        self.cache[key] = value
        self.cache_ttl[key] = datetime.now() + (ttl or self.default_ttl)
        
mcp_cache = MCPCache()

class MCPConnector:
    """Connecteur pour les appels MCP (Model Context Protocol) - VERSION COMPLÈTE"""
    
    def __init__(self):
        self.cache_manager = RedisCacheManager()
        # Créer des références vers les méthodes statiques pour compatibilité
        self.get_salesforce_accounts = MCPConnector.get_salesforce_accounts
        self.get_sap_products = MCPConnector.get_sap_products
    
    # === MÉTHODES PRINCIPALES CORRIGÉES ===
    
    @staticmethod
    async def call_salesforce_mcp(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appelle un outil MCP Salesforce
        
        Args:
            action: Nom de l'action MCP (ex: "salesforce_query")
            params: Paramètres de l'action
            
        Returns:
            Résultat de l'appel MCP
        """
        return await MCPConnector._call_mcp("salesforce_mcp", action, params)
    
    @staticmethod
    async def call_sap_mcp(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 CORRECTION : Méthode statique sans self
        
        Appelle un outil MCP SAP
        
        Args:
            action: Nom de l'action MCP (ex: "sap_read")
            params: Paramètres de l'action
            
        Returns:
            Résultat de l'appel MCP
        """
        return await MCPConnector._call_mcp("sap_mcp", action, params)
    
    # === MÉTHODES D'INSTANCE POUR COMPATIBILITÉ ===
    
    async def call_mcp(self, server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 CORRECTION : Ajout de la méthode call_mcp manquante
        
        Méthode d'instance pour appeler MCP avec cache
        """
        # Vérifier cache en premier
        cache_key = self.cache_manager.generate_cache_key(server_name, action=action, **params)
        
        try:
            cached_result = await self.cache_manager.get_cached_data(cache_key)
            if cached_result:
                logger.debug(f"Cache hit pour {cache_key}")
                return cached_result
        except Exception as e:
            logger.warning(f"Erreur récupération cache: {e}")
        
        # Appel normal puis mise en cache
        if server_name == "salesforce_mcp":
            result = await MCPConnector.call_salesforce_mcp(action, params)
        elif server_name == "sap_mcp":
            result = await MCPConnector.call_sap_mcp(action, params)
        else:
            result = await MCPConnector._call_mcp(server_name, action, params)
        
        try:
            await self.cache_manager.cache_data(cache_key, result)
        except Exception as e:
            logger.warning(f"Erreur mise en cache: {e}")
        
        return result

    @staticmethod
    async def call_mcp_server(server_name, action, params):
        """Mode direct sans WebSocket - fallback pour compatibilité"""
        # Cette méthode est conservée pour compatibilité mais délègue à _call_mcp
        logger.warning("Utilisation de call_mcp_server (déprécié) - redirection vers _call_mcp")
        return await MCPConnector._call_mcp(server_name, action, params)
    
    @staticmethod
    async def _call_mcp(server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Méthode générique pour appeler un outil MCP via subprocess - VERSION OPTIMISÉE"""
        
        # Cache pour les appels lecture seule
        cache_key = f"{server_name}:{action}:{hash(str(params))}"
        if action in ['sap_read', 'salesforce_query', 'sap_get_product_details']:
            cached_result = mcp_cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit pour {cache_key}")
                return cached_result
        
        logger.info(f"Appel MCP: {server_name}.{action}")
        
        try:
            # Créer fichier temporaire pour les paramètres d'entrée
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_in:
                temp_in_path = temp_in.name
                json.dump({"action": action, "params": params}, temp_in)
                temp_in.flush()
            
            # Créer fichier temporaire pour la sortie
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_out:
                temp_out_path = temp_out.name
            
            try:
                # Avant le bloc try avec subprocess.run(), ajouter :
                timeout_seconds = get_timeout_for_action(action)

                # Exécuter le script avec les arguments appropriés
                script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{server_name}.py")
                logger.info(f"Chemin du script MCP: {script_path}")

                if not os.path.exists(script_path):
                    logger.error(f"Script MCP introuvable: {script_path}")
                    return {"error": f"Script MCP introuvable: {script_path}"}

                # Utiliser subprocess.run() dans un thread séparé pour éviter le blocage
                def run_subprocess():
                    try:
                        result = subprocess.run(
                            [sys.executable, script_path, "--input-file", temp_in_path, "--output-file", temp_out_path],  # 🔧 Arguments nommés
                            capture_output=True,
                            text=True,
                            timeout=timeout_seconds,  # ✅ Variable maintenant définie
                            cwd=os.path.dirname(script_path)
                        )
                        return result
                    except subprocess.TimeoutExpired:
                        logger.error(f"Timeout lors de l'appel MCP {server_name}.{action}")
                        return None
                    except Exception as e:
                        logger.error(f"Erreur subprocess: {e}")
                        return None
                
                # Exécuter dans un thread séparé
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, run_subprocess)
                
                if result is None:
                    return {"error": "Timeout ou erreur lors de l'appel MCP"}
                
                logger.info(f"Retour subprocess: code={result.returncode}")
                
                if result.returncode != 0:
                    logger.error(f"Erreur MCP {server_name}.{action}: {result.stderr}")
                    return {"error": f"Erreur MCP: {result.stderr}"}
                
                # Lire le fichier de sortie
                if os.path.exists(temp_out_path):
                    with open(temp_out_path, 'r', encoding='utf-8') as f:
                        output_data = json.load(f)
                else:
                    output_data = {"success": True, "data": result.stdout}
                
                # Mettre en cache si succès
                if action in ['sap_read', 'salesforce_query', 'sap_get_product_details']:
                    mcp_cache.set(cache_key, output_data)
                
                logger.info(f"Appel MCP réussi: {action}")
                return output_data
                
            finally:
                # Nettoyer les fichiers temporaires
                for temp_file in [temp_in_path, temp_out_path]:
                    try:
                        if os.path.exists(temp_file):
                            os.unlink(temp_file)
                    except Exception as e:
                        logger.warning(f"Erreur nettoyage fichier temporaire: {e}")
                        
        except Exception as e:
            logger.exception(f"Erreur lors de l'appel MCP {server_name}.{action}: {str(e)}")
            return {"error": str(e)}
    
    # === MÉTHODES SALESFORCE COMPLÈTES ===
    
    @staticmethod
    async def get_salesforce_accounts(search_term: str = None, limit: int = 100) -> Dict[str, Any]:
        """
        Récupère les comptes Salesforce
        
        Args:
            search_term: Terme de recherche (optionnel)
            limit: Nombre maximum de comptes à récupérer
            
        Returns:
            Dict avec les comptes trouvés
        """
        try:
            query = f"""
            SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, 
                   Phone, Website, Description, CreatedDate, BillingCity, BillingCountry
            FROM Account 
            """
            
            if search_term:
                query += f"WHERE Name LIKE '%{search_term}%' OR AccountNumber LIKE '%{search_term}%' "
            
            query += f"ORDER BY Name LIMIT {limit}"
            
            return await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": query
            })
            
        except Exception as e:
            logger.error(f"Erreur get_salesforce_accounts: {str(e)}")
            return {"error": str(e), "records": []}
    
    @staticmethod
    async def salesforce_create_record(sobject: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un enregistrement dans Salesforce
        
        Args:
            sobject: Nom de l'objet Salesforce (ex: "Opportunity", "Product2")
            data: Données de l'enregistrement
            
        Returns:
            Résultat de la création
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
            "sobject": sobject,
            "data": data
        })
    
    @staticmethod
    async def salesforce_update_record(sobject: str, record_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Met à jour un enregistrement dans Salesforce
        
        Args:
            sobject: Nom de l'objet Salesforce
            record_id: ID de l'enregistrement
            data: Nouvelles données
            
        Returns:
            Résultat de la mise à jour
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_update_record", {
            "sobject": sobject,
            "record_id": record_id,
            "data": data
        })
    
    @staticmethod
    async def salesforce_query(query: str) -> Dict[str, Any]:
        """
        Alias pour salesforce_query - compatibilité
        
        Args:
            query: Requête SOQL
            
        Returns:
            Résultats de la requête
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_query", {
            "query": query
        })
    
    @staticmethod
    async def salesforce_create_opportunity(opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée une opportunité dans Salesforce
        
        Args:
            opportunity_data: Données de l'opportunité
            
        Returns:
            Résultat de la création
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_create_opportunity", {
            "opportunity_data": opportunity_data
        })
    
    @staticmethod
    async def salesforce_add_opportunity_line_item(opportunity_id: str, pricebook_entry_id: str, quantity: int, unit_price: float) -> Dict[str, Any]:
        """
        Ajoute une ligne à une opportunité
        
        Args:
            opportunity_id: ID de l'opportunité
            pricebook_entry_id: ID de l'entrée pricebook
            quantity: Quantité
            unit_price: Prix unitaire
            
        Returns:
            Résultat de l'ajout
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_add_opportunity_line_item", {
            "opportunity_id": opportunity_id,
            "pricebook_entry_id": pricebook_entry_id,
            "quantity": quantity,
            "unit_price": unit_price
        })
    
    @staticmethod
    async def salesforce_create_opportunity_complete(opportunity_data: Dict[str, Any], line_items: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Crée une opportunité complète avec ses lignes
        
        Args:
            opportunity_data: Données de l'opportunité
            line_items: Lignes d'opportunité (optionnel)
            
        Returns:
            Résultat de la création complète
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_create_opportunity_complete", {
            "opportunity_data": opportunity_data,
            "line_items": line_items or []
        })
    
    @staticmethod
    async def salesforce_get_standard_pricebook() -> Dict[str, Any]:
        """
        Récupère l'ID du Pricebook standard
        
        Returns:
            Informations du Pricebook standard
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_get_standard_pricebook", {})
    
    @staticmethod
    async def salesforce_create_product_complete(product_data: Dict[str, Any], unit_price: float = 0.0) -> Dict[str, Any]:
        """
        Crée un produit complet dans Salesforce avec entrée Pricebook
        
        Args:
            product_data: Données du produit
            unit_price: Prix unitaire
            
        Returns:
            Résultat de la création complète
        """
        return await MCPConnector.call_salesforce_mcp("salesforce_create_product_complete", {
            "product_data": product_data,
            "unit_price": unit_price
        })
    
    # === MÉTHODES SAP COMPLÈTES ===
    
    @staticmethod
    async def get_sap_products(search_term: str = None, limit: int = 100) -> Dict[str, Any]:
        """
        Récupère les produits SAP
        
        Args:
            search_term: Terme de recherche (optionnel)
            limit: Nombre maximum de produits à récupérer
            
        Returns:
            Dict avec les produits trouvés
        """
        try:
            endpoint = "/Items"
            
            if search_term:
                endpoint += f"?$filter=contains(ItemName,'{search_term}') or contains(ItemCode,'{search_term}')"
                endpoint += f"&$orderby=ItemCode&$top={limit}"
            else:
                endpoint += f"?$orderby=ItemCode&$top={limit}"
            
            result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": endpoint,
                "method": "GET"
            })
            
            if "error" not in result:
                # Reformater pour correspondre à l'attente du workflow
                products = result.get("value", [])
                return {"products": products, "success": True}
            else:
                return {"error": result["error"], "products": []}
                
        except Exception as e:
            logger.error(f"Erreur get_sap_products: {str(e)}")
            return {"error": str(e), "products": []}
    
    @staticmethod
    async def sap_get_product_details(item_code: str) -> Dict[str, Any]:
        """
        Récupère les détails complets d'un produit SAP
        
        Args:
            item_code: Code du produit
            
        Returns:
            Détails du produit
        """
        return await MCPConnector.call_sap_mcp("sap_get_product_details", {
            "item_code": item_code
        })
    
    @staticmethod
    async def sap_search_products(search_term: str, limit: int = 10) -> Dict[str, Any]:
        """
        Recherche de produits SAP par terme
        
        Args:
            search_term: Terme de recherche
            limit: Nombre maximum de résultats
            
        Returns:
            Résultats de la recherche
        """
        return await MCPConnector.call_sap_mcp("sap_search", {
            "query": search_term,
            "entity_type": "Items",
            "limit": limit
        })
    
    @staticmethod
    async def sap_create_customer_complete(customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un client complet dans SAP en utilisant la nouvelle méthode MCP
        
        Args:
            customer_data: Dictionnaire avec toutes les données du client
            
        Returns:
            Résultat de la création
        """
        return await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
            "customer_data": customer_data
        })
    
    @staticmethod
    async def sap_create_quotation_complete(quotation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un devis complet dans SAP en utilisant la nouvelle méthode MCP
        
        Args:
            quotation_data: Dictionnaire avec toutes les données du devis
            
        Returns:
            Résultat de la création
        """
        return await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {
            "quotation_data": quotation_data
        })
    
    # === MÉTHODES DE VÉRIFICATION ===
    
    @staticmethod
    async def verify_sap_quotation(doc_entry: int = None, doc_num: str = None) -> Dict[str, Any]:
        """
        Vérifie qu'un devis existe dans SAP
        
        Args:
            doc_entry: Numéro d'entrée du document
            doc_num: Numéro du document
            
        Returns:
            Données du devis ou erreur
        """
        if doc_entry:
            return await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations({doc_entry})",
                "method": "GET"
            })
        elif doc_num:
            return await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations?$filter=DocNum eq {doc_num}",
                "method": "GET"
            })
        else:
            return {"error": "Doc_entry ou doc_num requis pour la vérification"}
    
    @staticmethod
    async def verify_sap_customer(card_code: str) -> Dict[str, Any]:
        """
        Vérifie qu'un client existe dans SAP
        
        Args:
            card_code: Code du client SAP
            
        Returns:
            Données du client ou erreur
        """
        return await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": f"/BusinessPartners('{card_code}')",
            "method": "GET"
        })
    
    # === MÉTHODES DE DIAGNOSTIC ===
    
    @staticmethod
    async def test_connections() -> Dict[str, Any]:
        """
        Test de connexion à tous les services MCP
        
        Returns:
            État des connexions
        """
        results = {}
        
        # Test Salesforce
        try:
            sf_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": "SELECT Id, Name FROM Account LIMIT 1"
            })
            results["salesforce"] = {
                "connected": "error" not in sf_result,
                "details": sf_result
            }
        except Exception as e:
            results["salesforce"] = {
                "connected": False,
                "error": str(e)
            }
        
        # Test SAP
        try:
            sap_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": "/Items?$top=1",
                "method": "GET"
            })
            results["sap"] = {
                "connected": "error" not in sap_result,
                "details": sap_result
            }
        except Exception as e:
            results["sap"] = {
                "connected": False,
                "error": str(e)
            }
        
        return results
    
    @staticmethod
    async def get_recent_sap_data(limit: int = 5) -> Dict[str, Any]:
        """
        Récupère des données récentes de SAP pour vérification
        
        Args:
            limit: Nombre d'éléments à récupérer
            
        Returns:
            Données récentes (clients, devis)
        """
        results = {}
        
        try:
            # Clients récents
            recent_customers = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/BusinessPartners?$filter=CardType eq 'cCustomer'&$orderby=CreateDate desc&$top={limit}",
                "method": "GET"
            })
            results["recent_customers"] = recent_customers
            
            # Devis récents
            recent_quotations = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations?$orderby=DocEntry desc&$top={limit}",
                "method": "GET"
            })
            results["recent_quotations"] = recent_quotations
            
        except Exception as e:
            results["error"] = str(e)
        
        return results
    
    # === MÉTHODES DE RECHERCHE ===
    
    @staticmethod
    async def search_sap_entity(query: str, entity_type: str = "Items", limit: int = 5) -> Dict[str, Any]:
        """
        Recherche unifiée dans SAP (amélioration de la méthode existante)
        
        Args:
            query: Terme de recherche
            entity_type: Type d'entité (Items, BusinessPartners, etc.)
            limit: Nombre de résultats
            
        Returns:
            Résultats de la recherche
        """
        return await MCPConnector.call_sap_mcp("sap_search", {
            "query": query,
            "entity_type": entity_type,
            "limit": limit
        })
    
    # === MÉTHODES UTILITAIRES ===
    
    @staticmethod
    def is_connection_error(result: Dict[str, Any]) -> bool:
        """
        Vérifie si le résultat indique une erreur de connexion
        
        Args:
            result: Résultat d'un appel MCP
            
        Returns:
            True si c'est une erreur de connexion
        """
        if "error" not in result:
            return False
        
        error_msg = str(result["error"]).lower()
        connection_keywords = [
            "connection", "network", "timeout", "unreachable", 
            "connexion", "réseau", "délai", "inaccessible"
        ]
        
        return any(keyword in error_msg for keyword in connection_keywords)
    
    @staticmethod
    def format_error_message(error: str, context: str = "") -> str:
        """
        Formate un message d'erreur de façon lisible
        
        Args:
            error: Message d'erreur
            context: Contexte de l'erreur
            
        Returns:
            Message d'erreur formaté
        """
        if context:
            return f"Erreur {context}: {error}"
        return f"Erreur: {error}"
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Retourne les statistiques du cache
        
        Returns:
            Statistiques du cache
        """
        return {
            "cache_manager_available": self.cache_manager is not None,
            "memory_cache_size": len(mcp_cache.cache),
            "memory_cache_keys": list(mcp_cache.cache.keys())
        }