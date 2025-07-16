# services/mcp_connector.py - VERSION CORRIGÉE SANS DUPLICATION

import os
import sys
import json
import asyncio
import subprocess
import tempfile
from typing import Dict, Any, List
import logging

logger = logging.getLogger("mcp_connector")

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
    """Connecteur pour les appels MCP (Model Context Protocol)"""
    # === ALIAS D'INSTANCE (pour compatibilité workflow) ===
    
    def __init__(self):
        # Créer des références vers les méthodes statiques
        self.get_salesforce_accounts = MCPConnector.get_salesforce_accounts
        self.get_sap_products = MCPConnector.get_sap_products

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
        """Appelle un outil MCP SAP"""
        return await MCPConnector._call_mcp("sap_mcp", action, params)

    @staticmethod
    async def call_mcp_server(server_name, action, params):
        """Mode direct sans WebSocket - fallback pour compatibilité"""
        # Cette méthode est conservée pour compatibilité mais délègue à _call_mcp
        logger.warning("Utilisation de call_mcp_server (déprécié) - redirection vers _call_mcp")
        return await MCPConnector._call_mcp(server_name, action, params)
    
    @staticmethod
    async def _call_mcp(server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Méthode générique pour appeler un outil MCP via subprocess - VERSION OPTIMISEE"""
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
                # Exécuter le script avec les arguments appropriés
                script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{server_name}.py")
                logger.info(f"Chemin du script MCP: {script_path}")
                
                if not os.path.exists(script_path):
                    logger.error(f"Script MCP introuvable: {script_path}")
                    return {"error": f"Script MCP introuvable: {script_path}"}
                
                # Utiliser subprocess.run() dans un thread séparé
                
                def run_subprocess():
                    try:
                        # Configuration spécifique Windows pour éviter l'erreur 0xC0000142
                        startupinfo = None
                        creationflags = 0
                        if sys.platform == "win32":
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                            startupinfo.wShowWindow = subprocess.SW_HIDE
                            # Créer un nouveau groupe de processus pour éviter les conflits
                            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

                        result = subprocess.run(
                            [sys.executable, script_path, "--input-file", temp_in_path, "--output-file", temp_out_path],
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=120,
                            encoding='utf-8',
                            errors='replace',
                            startupinfo=startupinfo,
                            creationflags=creationflags
                        )
                        return result.returncode, result.stdout, result.stderr
                    except subprocess.TimeoutExpired:
                        logger.error("Timeout lors de l'exécution du script MCP")
                        return -1, "", "Timeout lors de l'exécution"
                    except Exception as e:
                        logger.error(f"Erreur lors de l'exécution du subprocess: {e}")
                        return -1, "", str(e)
                
                # Exécuter dans un ThreadPoolExecutor pour éviter de bloquer la boucle asyncio
                loop = asyncio.get_event_loop()
                returncode, stdout, stderr = await loop.run_in_executor(
                    None, run_subprocess
                )
                
                logger.info(f"Retour subprocess: code={returncode}")
                if stdout:
                    logger.debug(f"Stdout: {stdout}")
                if stderr:
                    logger.warning(f"Stderr: {stderr}")
                
                if returncode != 0:
                    logger.error(f"Erreur exécution MCP: code {returncode}")
                    return {"error": f"Échec appel MCP: code {returncode}. Erreur: {stderr}"}
                
                # Lire le résultat depuis le fichier de sortie
                if os.path.exists(temp_out_path):
                    try:
                        with open(temp_out_path, 'r', encoding='utf-8') as f:
                            result = json.load(f)
                        
                        logger.info(f"Appel MCP réussi: {action}")
                        if action in ['sap_read', 'salesforce_query', 'sap_get_product_details'] and "error" not in result:
                            mcp_cache.set(cache_key, result)
                    
                        return result
                    except json.JSONDecodeError as je:
                        logger.error(f"Erreur JSON dans le fichier de sortie: {je}")
                        try:
                            with open(temp_out_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            logger.error(f"Contenu brut du fichier: {content}")
                        # Catch any exception when reading the file for logging purposes only.
                        except Exception:
                            pass
                        return {"error": f"Format JSON invalide dans la réponse MCP: {je}"}
                else:
                    logger.error(f"Fichier de sortie inexistant: {temp_out_path}")
                    return {"error": "Fichier de sortie MCP non créé"}
                    
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"Exception lors de l'appel MCP: {str(e)}\n{tb}")
                return {"error": str(e)}
            finally:
                # Nettoyer les fichiers temporaires
                for path in [temp_in_path, temp_out_path]:
                    if os.path.exists(path):
                        try:
                            os.unlink(path)
                        # Only OSError should be caught here, as os.unlink raises this if deletion fails.
                        except OSError:
                            pass
                            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Erreur critique: {str(e)}\n{tb}")
            return {"error": str(e)}
    
    # === MÉTHODES UTILITAIRES POUR SALESFORCE (nouvelles) ===
    
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
    
    # === MÉTHODES DE VÉRIFICATION (extension des fonctionnalités existantes) ===
    
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
    
    # === MÉTHODES DE DIAGNOSTIC (nouvelles mais cohérentes) ===
    
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
            sap_result = await MCPConnector.call_sap_mcp("ping", {})
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
    
    # === MÉTHODES DE RECHERCHE (amélioration des existantes) ===
    
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
    @staticmethod
    async def get_salesforce_accounts(limit: int = 100) -> Dict[str, Any]:
        """
        Récupère les comptes Salesforce
        
        Args:
            limit: Nombre maximum de comptes à récupérer
            
        Returns:
            Dict avec les comptes trouvés
        """
        try:
            query = f"""
            SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, 
                   Phone, Website, Description, CreatedDate
            FROM Account 
            ORDER BY Name
            LIMIT {limit}
            """
            
            return await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": query
            })
            
        except Exception as e:
            logger.error(f"Erreur get_salesforce_accounts: {str(e)}")
            return {"error": str(e), "records": []}
    
    @staticmethod
    async def get_sap_products(limit: int = 100) -> Dict[str, Any]:
        """
        Récupère les produits SAP
        
        Args:
            limit: Nombre maximum de produits à récupérer
            
        Returns:
            Dict avec les produits trouvés
        """
        try:
            result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$orderby=ItemCode&$top={limit}",
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
    async def get_sap_product_details(item_code: str) -> Dict[str, Any]:
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
    
    # === MÉTHODES UTILITAIRES GÉNÉRALES ===
    
    @staticmethod
    def is_connection_error(result: Dict[str, Any]) -> bool:
        """
        Vérifie si un résultat indique une erreur de connexion
        
        Args:
            result: Résultat d'un appel MCP
            
        Returns:
            True si erreur de connexion
        """
        if "error" not in result:
            return False
        
        error_msg = str(result["error"]).lower()
        connection_errors = [
            "connexion", "connection", "timeout", "unreachable", 
            "refused", "network", "dns", "socket"
        ]
        
        return any(err in error_msg for err in connection_errors)
    
    @staticmethod
    def extract_error_message(result: Dict[str, Any]) -> str:
        """
        Extrait un message d'erreur lisible d'un résultat MCP
        
        Args:
            result: Résultat d'un appel MCP
            
        Returns:
            Message d'erreur formaté
        """
        if "error" not in result:
            return "Aucune erreur"
        
        error = result["error"]
        if isinstance(error, dict):
            # Erreur SAP structurée
            if "message" in error:
                return error["message"]["value"] if isinstance(error["message"], dict) else str(error["message"])
            elif "error" in error:
                return str(error["error"])
            else:
                return str(error)
        else:
            return str(error)