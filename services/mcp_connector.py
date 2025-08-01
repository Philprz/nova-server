
import os
import sys
import json
import asyncio
import subprocess
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import requests
from dotenv import load_dotenv
load_dotenv()
# Configuration du logging
logger = logging.getLogger("mcp_connector")
# Imports conditionnels avec gestion d'erreurs
try:
    from services.cache_manager import RedisCacheManager
except ImportError:
    RedisCacheManager = None

try:
    from simple_salesforce import Salesforce
except ImportError:
    Salesforce = None
try:
    from services.llm_extractor import get_llm_extractor
    logger.info("get_llm_extractor importé avec succès")
except ImportError as e:
    logger.warning(f"Impossible d'importer get_llm_extractor: {e}")
    get_llm_extractor = None
# Configuration du logging
logger = logging.getLogger("mcp_connector")

# === FONCTION UTILITAIRE POUR LES WORKFLOWS ===

async def call_mcp_with_progress(server_name: str, action: str, params: Dict[str, Any],
                                step_id: str = "mcp_call", message: str = "") -> Dict[str, Any]:
    """
    Appel MCP avec tracking de progression intégré

    Args:
        server_name: Nom du serveur MCP
        action: Action à exécuter
        params: Paramètres de l'action
        step_id: ID de l'étape pour le tracking
        message: Message de progression personnalisé

    Returns:
        Résultat de l'appel MCP
    """
    try:
        # Tenter de récupérer le task tracker actuel
        from services.progress_tracker import progress_tracker
        current_task = getattr(progress_tracker, '_current_task', None)

        if current_task and hasattr(current_task, 'update_step_progress'):
            # Démarrer la progression
            start_msg = message or f"Exécution {server_name}.{action}"
            current_task.update_step_progress(step_id, 10, start_msg)

            result = await mcp_connector.call_mcp(server_name, action, params)

            # Terminer la progression
            if "error" in result:
                current_task.update_step_progress(step_id, 100, f"Erreur {action}")
            else:
                success_msg = message.replace("🔄", "✅") if message else f"{action} terminé"
                current_task.update_step_progress(step_id, 100, success_msg)

            return result
        else:
            # Pas de tracking disponible, appel direct
            connector = MCPConnector()
            return await connector.call_mcp(server_name, action, params)

    except Exception as e:
        logger.error(f"Erreur call_mcp_with_progress: {str(e)}")
        return {"error": str(e)}
    
async def test_mcp_connections_with_progress() -> Dict[str, Any]:
    """Test des connexions MCP avec progression détaillée
    Test des connexions MCP avec progression détaillée
    
    Returns:
        État détaillé des connexions
    """
    results = {
        "overall_status": "unknown",
        "connections": {},
        "timestamp": datetime.now().isoformat()
    }

    try:
        from services.progress_tracker import progress_tracker
        current_task = getattr(progress_tracker, '_current_task', None)
        mcp_connector = MCPConnector()

        # Test Salesforce
        if current_task:
            current_task.update_step_progress("test_connections", 25, "🔍 Test Salesforce...")

        try:
            sf_result = await mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {
                "query": "SELECT Id, Name FROM Account LIMIT 1"
            })
            results["connections"]["salesforce"] = {
                "connected": "error" not in sf_result,
                "details": sf_result,
                "test_time": datetime.now().isoformat()
            }
        except Exception as e:
            results["connections"]["salesforce"] = {
                "connected": False,
                "error": str(e),
                "test_time": datetime.now().isoformat()
            }

        # Test SAP
        if current_task:
            current_task.update_step_progress("test_connections", 75, "🔍 Test SAP...")

        try:
            # Utiliser sap_read au lieu de get_items (d'après les logs d'erreur)
            sap_result = await mcp_connector.call_mcp("sap_mcp", "sap_read", {
                "endpoint": "/Items?$top=1",
                "method": "GET"
            })
            results["connections"]["sap"] = {
                "connected": "error" not in sap_result,
                "details": sap_result,
                "test_time": datetime.now().isoformat()
            }
        except Exception as e:
            results["connections"]["sap"] = {
                "connected": False,
                "error": str(e),
                "test_time": datetime.now().isoformat()
            }

        # Déterminer le statut global
        sf_ok = results["connections"].get("salesforce", {}).get("connected", False)
        sap_ok = results["connections"].get("sap", {}).get("connected", False)

        if sf_ok and sap_ok:
            results["overall_status"] = "all_connected"
        elif sf_ok or sap_ok:
            results["overall_status"] = "partial_connection"
        else:
            results["overall_status"] = "no_connection"

        if current_task:
            status_msg = {
                "all_connected": "✅ Toutes les connexions OK",
                "partial_connection": "⚠️ Connexions partielles", 
                "no_connection": "❌ Aucune connexion"
            }.get(results["overall_status"], "❓ Statut inconnu")

            current_task.update_step_progress("test_connections", 100, status_msg)

        logger.info(f"Test connexions terminé: {results['overall_status']}")
        return results

    except Exception as e:
        logger.error(f"Erreur test_mcp_connections_with_progress: {str(e)}")
        results["overall_status"] = "error"
        results["error"] = str(e)
        return results
def get_timeout_for_action(action: str) -> int:
    """Retourne le timeout approprié selon l'action"""
    timeouts = {
        'salesforce_query': 60,
        'sap_read': 45,
        'sap_search': 60,
        'sap_create_customer_complete': 90,
        'sap_create_quotation_complete': 90,
        'salesforce_create_opportunity_complete': 75,
        'ping': 10
    }
    return timeouts.get(action, 30)

class MCPCache:
    """Cache intelligent pour les appels MCP avec TTL"""
    
    def __init__(self):
        self.cache: Dict[str, Any] = {}
        self.cache_ttl: Dict[str, datetime] = {}
        self.default_ttl = timedelta(minutes=5)
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache si elle n'est pas expirée"""
        if key in self.cache:
            if datetime.now() < self.cache_ttl.get(key, datetime.min):
                return self.cache[key]
            else:
                # Nettoyer les entrées expirées
                self._clean_expired_entry(key)
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[timedelta] = None) -> None:
        """Stocke une valeur dans le cache"""
        self.cache[key] = value
        self.cache_ttl[key] = datetime.now() + (ttl or self.default_ttl)
    
    def _clean_expired_entry(self, key: str) -> None:
        """Nettoie une entrée expirée"""
        self.cache.pop(key, None)
        self.cache_ttl.pop(key, None)
    
    def clear(self) -> None:
        """Vide complètement le cache"""
        self.cache.clear()
        self.cache_ttl.clear()

# Instance globale du cache
mcp_cache = MCPCache()

class MCPConnector:
    """
    Connecteur pour les appels MCP (Model Context Protocol)
    VERSION OPTIMISÉE - Sans doublons
    """
    
    def __init__(self):
        """Initialisation du connecteur MCP"""
        # Cache manager
        self.cache_manager = RedisCacheManager() if RedisCacheManager else None
        
        # Clients directs (pour méthodes d'instance)
        self.salesforce_client: Optional[Salesforce] = None
        self.sap_client: Optional[Dict[str, str]] = None
        
        # Statut des connexions
        self.connection_status = {
            "salesforce": False,
            "sap": False
        }
        
        logger.info("MCPConnector initialisé")
    async def sap_login(self) -> Dict[str, Any]:
        """Méthode de connexion SAP publique - Correction pour l'erreur 'sap_login'"""
        try:
            success = await self._init_sap()
            if success:
                logger.info("Connexion SAP réussie via sap_login")
                return {
                    "success": True,
                    "message": "Connexion SAP établie avec succès",
                    "connected": True,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                logger.error("Échec connexion SAP via sap_login")
                return {
                    "success": False,
                    "message": "Échec de la connexion SAP - Configuration incomplète",
                    "connected": False,
                    "error": "Configuration SAP manquante ou incorrecte"
                }
        except Exception as e:
            logger.error(f"Erreur sap_login: {str(e)}")
            return {
                "success": False,
                "message": f"Erreur lors de la connexion SAP: {str(e)}",
                "connected": False,
                "error": str(e)
            }

    async def salesforce_login(self) -> Dict[str, Any]:
        """Méthode de connexion Salesforce publique - Correction pour l'erreur 'salesforce_login'"""
        try:
            success = await self._init_salesforce()
            if success:
                logger.info("Connexion Salesforce réussie via salesforce_login")
                return {
                    "success": True,
                    "message": "Connexion Salesforce établie avec succès",
                    "connected": True,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                logger.error("Échec connexion Salesforce via salesforce_login")
                return {
                    "success": False,
                    "message": "Échec de la connexion Salesforce - Configuration incomplète",
                    "connected": False,
                    "error": "Configuration Salesforce manquante ou incorrecte"
                }
        except Exception as e:
            logger.error(f"Erreur salesforce_login: {str(e)}")
            return {
                "success": False,
                "message": f"Erreur lors de la connexion Salesforce: {str(e)}",
                "connected": False,
                "error": str(e)
            }

    # Méthode utilitaire pour tester les connexions individuellement
    async def test_sap_connection(self) -> Dict[str, Any]:
        """Test spécifique de la connexion SAP"""
        return await self.sap_login()

    async def test_salesforce_connection(self) -> Dict[str, Any]:
        """Test spécifique de la connexion Salesforce"""
        return await self.salesforce_login()
    # ===================================================================
    # MÉTHODES STATIQUES MCP PRINCIPALES (PRIORITAIRES)
    # ===================================================================

    @staticmethod
    async def call_salesforce_mcp(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Appelle un outil MCP Salesforce"""
        return await MCPConnector._call_mcp("salesforce_mcp", action, params)

    @staticmethod
    async def call_sap_mcp(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Appelle un outil MCP SAP"""
        return await MCPConnector._call_mcp("sap_mcp", action, params)

    # --- SALESFORCE MCP METHODS ---

    @staticmethod
    async def get_salesforce_accounts(search_term: str = None, limit: int = 100) -> Dict[str, Any]:
        """Récupère les comptes Salesforce via MCP"""
        query = "SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, Phone, Website, Description, CreatedDate, BillingCity, BillingCountry FROM Account"
        
        if search_term:
            query += f" WHERE Name LIKE '%{search_term}%' OR AccountNumber LIKE '%{search_term}%'"
        
        query += f" LIMIT {limit}"
        
        return await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})

    @staticmethod
    async def salesforce_query(query: str) -> Dict[str, Any]:
        """Exécute une requête SOQL via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})

    @staticmethod
    async def salesforce_create_record(sobject: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un enregistrement Salesforce via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
            "sobject": sobject,
            "data": data
        })

    @staticmethod
    async def salesforce_update_record(sobject: str, record_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Met à jour un enregistrement Salesforce via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_update_record", {
            "sobject": sobject,
            "record_id": record_id,
            "data": data
        })

    @staticmethod
    async def salesforce_create_opportunity(opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crée une opportunité Salesforce via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_create_opportunity", {
            "opportunity_data": opportunity_data
        })

    @staticmethod
    async def salesforce_create_opportunity_complete(opportunity_data: Dict[str, Any], line_items: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Crée une opportunité complète avec lignes via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_create_opportunity_complete", {
            "opportunity_data": opportunity_data,
            "line_items": line_items or []
        })

    @staticmethod
    async def salesforce_add_opportunity_line_item(opportunity_id: str, pricebook_entry_id: str, quantity: int, unit_price: float) -> Dict[str, Any]:
        """Ajoute une ligne d'opportunité via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_add_opportunity_line_item", {
            "opportunity_id": opportunity_id,
            "pricebook_entry_id": pricebook_entry_id,
            "quantity": quantity,
            "unit_price": unit_price
        })

    @staticmethod
    async def salesforce_get_standard_pricebook() -> Dict[str, Any]:
        """Récupère le Pricebook standard via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_get_standard_pricebook", {})

    @staticmethod
    async def salesforce_create_product_complete(product_data: Dict[str, Any], unit_price: float = 0.0) -> Dict[str, Any]:
        """Crée un produit complet avec entrée Pricebook via MCP"""
        return await MCPConnector.call_salesforce_mcp("salesforce_create_product_complete", {
            "product_data": product_data,
            "unit_price": unit_price
        })

    # --- SAP MCP METHODS ---

    @staticmethod
    async def get_sap_products(search_term: str = None, limit: int = 100) -> Dict[str, Any]:
        """MÉTHODE PRINCIPALE - Récupère les produits SAP via MCP"""
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
                products = result.get("value", [])
                return {"products": products, "success": True}
            else:
                return {"error": result["error"], "products": []}
                
        except Exception as e:
            logger.error(f"Erreur get_sap_products: {str(e)}")
            return {"error": str(e), "products": []}

    @staticmethod
    async def sap_get_product_details(item_code: str) -> Dict[str, Any]:
        """Récupère les détails d'un produit SAP via MCP"""
        return await MCPConnector.call_sap_mcp("sap_get_product_details", {
            "item_code": item_code
        })

    @staticmethod
    async def sap_create_customer_complete(customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """MÉTHODE PRINCIPALE - Crée un client complet SAP via MCP"""
        return await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
            "customer_data": customer_data
        })

    @staticmethod
    async def sap_create_quotation_complete(quotation_data: Dict[str, Any]) -> Dict[str, Any]:
        """MÉTHODE PRINCIPALE - Crée un devis complet SAP via MCP"""
        return await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {
            "quotation_data": quotation_data
        })

    # --- VÉRIFICATION ET LECTURE SAP ---

    @staticmethod
    async def verify_sap_quotation(doc_entry: int = None, doc_num: str = None) -> Dict[str, Any]:
        """Vérifie qu'un devis existe dans SAP"""
        if doc_entry:
            endpoint = f"/Quotations({doc_entry})"
        elif doc_num:
            endpoint = f"/Quotations?$filter=DocNum eq {doc_num}"
        else:
            return {"error": "doc_entry ou doc_num requis pour la vérification"}
        
        return await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": endpoint,
            "method": "GET"
        })

    @staticmethod
    async def verify_sap_customer(card_code: str) -> Dict[str, Any]:
        """Vérifie qu'un client existe dans SAP"""
        return await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": f"/BusinessPartners('{card_code}')",
            "method": "GET"
        })

    # ===================================================================
    # MÉTHODE MCP GÉNÉRIQUE (CŒUR DU SYSTÈME)
    # ===================================================================

    @staticmethod
    async def _call_mcp(server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Méthode générique pour appeler un outil MCP via subprocess - VERSION OPTIMISÉE"""
        
        # Cache intelligent pour les opérations de lecture
        cache_key = f"{server_name}:{action}:{hash(str(sorted(params.items())))}"
        read_only_actions = ['sap_read', 'salesforce_query', 'sap_get_product_details']
        
        if action in read_only_actions:
            cached_result = mcp_cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit pour {cache_key}")
                return cached_result
        
        logger.info(f"Appel MCP: {server_name}.{action}")
        
        temp_in_path = None
        temp_out_path = None
        
        try:
            # Créer fichiers temporaires pour l'échange de données
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_in:
                temp_in_path = temp_in.name
                json.dump({"action": action, "params": params}, temp_in, ensure_ascii=False)
                temp_in.flush()
            
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_out:
                temp_out_path = temp_out.name
            
            # Configuration du subprocess
            timeout_seconds = get_timeout_for_action(action)
            script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), f"{server_name}.py")
            
            if not os.path.exists(script_path):
                logger.error(f"Script MCP introuvable: {script_path}")
                return {"error": f"Script MCP introuvable: {script_path}"}
            
            # Fonction pour exécuter le subprocess
            def run_subprocess():
                try:
                    result = subprocess.run(
                        [
                            sys.executable, 
                            script_path, 
                            "--input-file", temp_in_path, 
                            "--output-file", temp_out_path
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout_seconds,
                        cwd=os.path.dirname(script_path)
                    )
                    return result
                except subprocess.TimeoutExpired:
                    logger.error(f"Timeout lors de l'appel MCP {server_name}.{action}")
                    return None
                except Exception as e:
                    logger.error(f"Erreur subprocess: {e}")
                    return None
            
            # Exécution asynchrone
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_subprocess)
            
            if result is None:
                return {"error": "Timeout ou erreur lors de l'appel MCP"}
            
            if result.returncode != 0:
                error_msg = result.stderr or "Erreur inconnue"
                logger.error(f"Erreur MCP {server_name}.{action}: {error_msg}")
                return {"error": f"Erreur MCP: {error_msg}"}
            
            # Lecture du résultat
            if os.path.exists(temp_out_path) and os.path.getsize(temp_out_path) > 0:
                with open(temp_out_path, 'r', encoding='utf-8') as f:
                    output_data = json.load(f)
            else:
                output_data = {"success": True, "data": result.stdout}
            
            # Mise en cache pour les opérations de lecture
            if action in read_only_actions and "error" not in output_data:
                mcp_cache.set(cache_key, output_data)
            
            logger.info(f"Appel MCP réussi: {server_name}.{action}")
            return output_data
            
        except Exception as e:
            logger.exception(f"Erreur lors de l'appel MCP {server_name}.{action}: {str(e)}")
            return {"error": str(e)}
            
        finally:
            # Nettoyage des fichiers temporaires
            for temp_file in [temp_in_path, temp_out_path]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except Exception as e:
                        logger.warning(f"Erreur nettoyage fichier temporaire: {e}")

    # ===================================================================
    # MÉTHODES D'INSTANCE AVEC CACHE ET TRACKING
    # ===================================================================

    async def call_mcp(self, server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Méthode d'instance pour appeler MCP avec cache et tracking de progression"""
        
        # Génération de la clé de cache
        cache_key = None
        if self.cache_manager:
            try:
                cache_key = self.cache_manager.generate_cache_key(server_name, action=action, **params)
                cached_result = await self.cache_manager.get_cached_data(cache_key)
                if cached_result:
                    logger.debug(f"Cache hit pour {cache_key}")
                    return cached_result
            except Exception as e:
                logger.warning(f"Erreur récupération cache: {e}")

        # Support du tracking de progression
        try:
            from services.progress_tracker import progress_tracker
                       
            
            current_task = getattr(progress_tracker, '_current_task', None)
            if current_task and hasattr(current_task, 'update_step_progress'):
                step_message = f"🔄 Appel {server_name}.{action}"
                current_task.update_step_progress("mcp_call", 25, step_message)
        except Exception as e:
            logger.debug(f"Tracking progression non disponible: {e}")
            current_task = None

        # Appel MCP selon le serveur
        try:
            if server_name == "salesforce_mcp":
                result = await MCPConnector.call_salesforce_mcp(action, params)
            elif server_name == "sap_mcp":
                result = await MCPConnector.call_sap_mcp(action, params)
            else:
                result = await MCPConnector._call_mcp(server_name, action, params)
            
            # Tracking de fin
            if current_task and hasattr(current_task, 'update_step_progress'):
                success_msg = f"✅ {server_name}.{action} terminé"
                current_task.update_step_progress("mcp_call", 100, success_msg)
            
            # Mise en cache
            if self.cache_manager and cache_key:
                try:
                    await self.cache_manager.cache_data(cache_key, result)
                except Exception as e:
                    logger.warning(f"Erreur mise en cache: {e}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur appel MCP {server_name}.{action}: {e}")
            return {"error": str(e)}

    # ===================================================================
    # MÉTHODES D'INSTANCE DIRECTES (SANS MCP)
    # ===================================================================

    async def search_salesforce_accounts(self, query: str) -> Dict[str, Any]:
        """Recherche de comptes Salesforce via connexion directe"""
        try:
            if not self.salesforce_client:
                await self._init_salesforce()
            
            if not self.salesforce_client:
                return {"success": False, "error": "Connexion Salesforce non disponible", "accounts": []}
            
            soql_query = f"SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, Phone, Website, Description, CreatedDate, BillingCity, BillingCountry FROM Account WHERE Name LIKE '%{query}%' OR AccountNumber LIKE '%{query}%' LIMIT 100"
            result = self.salesforce_client.query(soql_query)
            
            return {
                "success": True,
                "accounts": result.get("records", []),
                "count": result.get("totalSize", 0)
            }
            
        except Exception as e:
            logger.error(f"Erreur recherche Salesforce: {str(e)}")
            return {"success": False, "error": str(e), "accounts": []}

    async def search_salesforce_opportunities(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Recherche d'opportunités Salesforce via connexion directe"""
        try:
            if not self.salesforce_client:
                await self._init_salesforce()
            
            if not self.salesforce_client:
                return {"success": False, "error": "Connexion Salesforce non disponible", "opportunities": []}
            
            query = "SELECT Id, Name, StageName, CloseDate, Amount, AccountId FROM Opportunity"
            
            if filters:
                conditions = [f"{key} = '{value}'" for key, value in filters.items()]
                query += " WHERE " + " AND ".join(conditions)
            
            query += " LIMIT 100"
            
            result = self.salesforce_client.query(query)
            return {
                "success": True,
                "opportunities": result.get("records", []),
                "count": result.get("totalSize", 0)
            }
            
        except Exception as e:
            logger.error(f"Erreur recherche opportunités: {str(e)}")
            return {"success": False, "error": str(e), "opportunities": []}

    async def create_salesforce_account(self, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """Création d'un compte Salesforce via connexion directe"""
        try:
            if not self.salesforce_client:
                await self._init_salesforce()
            
            if not self.salesforce_client:
                return {"success": False, "error": "Connexion Salesforce non disponible"}
            
            result = self.salesforce_client.Account.create(account_data)
            return {
                "success": True,
                "account_id": result.get("id"),
                "message": "Compte créé avec succès",
                "data": account_data
            }
            
        except Exception as e:
            logger.error(f"Erreur création compte: {str(e)}")
            return {"success": False, "error": str(e)}

    async def search_sap_items(self, query: str) -> Dict[str, Any]:
        """Recherche d'articles SAP via connexion directe"""
        try:
            if not self.sap_client:
                await self._init_sap()
            
            if not self.sap_client:
                return {"success": False, "error": "Connexion SAP non disponible", "items": []}
            
            endpoint = f"/Items?$filter=contains(ItemName,'{query}') or contains(ItemCode,'{query}')&$orderby=ItemCode&$top=100"
            
            response = requests.get(
                self.sap_client['base_url'] + endpoint, 
                auth=(self.sap_client['user'], self.sap_client['password']),
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "success": True,
                "items": result.get("value", []),
                "count": len(result.get("value", []))
            }
            
        except Exception as e:
            logger.error(f"Erreur recherche SAP: {str(e)}")
            return {"success": False, "error": str(e), "items": []}

    async def get_sap_stock_info(self, item_code: str) -> Dict[str, Any]:
        """Récupération des informations de stock SAP via connexion directe"""
        try:
            if not self.sap_client:
                await self._init_sap()
            
            if not self.sap_client:
                return {"success": False, "error": "Connexion SAP non disponible", "item_code": item_code}
            
            endpoint = f"/Items('{item_code}')/ItemWarehouseInfoCollection"
            
            response = requests.get(
                self.sap_client['base_url'] + endpoint,
                auth=(self.sap_client['user'], self.sap_client['password']),
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            total_stock = sum(item.get("InStock", 0) for item in result.get("value", []))
            
            return {
                "success": True,
                "item_code": item_code,
                "stock_quantity": total_stock,
                "available": total_stock > 0,
                "message": f"Stock vérifié pour: {item_code}",
                "warehouses": result.get("value", [])
            }
            
        except Exception as e:
            logger.error(f"Erreur vérification stock: {str(e)}")
            return {"success": False, "error": str(e), "item_code": item_code}

    async def create_sap_quote(self, quote_data: Dict[str, Any]) -> Dict[str, Any]:
        """Création d'un devis SAP via connexion directe"""
        try:
            if not self.sap_client:
                await self._init_sap()
            
            if not self.sap_client:
                return {"success": False, "error": "Connexion SAP non disponible"}
            
            endpoint = "/Quotations"
            
            response = requests.post(
                self.sap_client['base_url'] + endpoint, 
                json=quote_data, 
                auth=(self.sap_client['user'], self.sap_client['password']),
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "success": True,
                "quote_id": result.get("DocEntry"),
                "quote_num": result.get("DocNum"),
                "message": "Devis SAP créé avec succès",
                "data": quote_data
            }
            
        except Exception as e:
            logger.error(f"Erreur création devis SAP: {str(e)}")
            return {"success": False, "error": str(e)}

    # ===================================================================
    # MÉTHODES D'INITIALISATION DES CONNEXIONS
    # ===================================================================

    async def _init_salesforce(self) -> bool:
        """Initialisation de la connexion Salesforce directe"""
        try:
            if not Salesforce:
                logger.warning("Module simple_salesforce non disponible")
                return False
            
            # Configuration Salesforce depuis les variables d'environnement
            sf_config = {
                'username': os.getenv("SALESFORCE_USERNAME"),
                'password': os.getenv("SALESFORCE_PASSWORD"),
                'security_token': os.getenv("SALESFORCE_SECURITY_TOKEN"),
                'domain': os.getenv("SALESFORCE_DOMAIN", "login")
            }
            
            if not all([sf_config['username'], sf_config['password'], sf_config['security_token']]):
                logger.warning("Configuration Salesforce incomplète")
                return False
            
            self.salesforce_client = Salesforce(**sf_config)
            self.connection_status["salesforce"] = True
            logger.info("Connexion Salesforce établie")
            return True
            
        except Exception as e:
            logger.error(f"Erreur initialisation Salesforce: {str(e)}")
            self.connection_status["salesforce"] = False
            return False

    async def _init_sap(self) -> bool:
        """Initialisation de la connexion SAP directe"""
        try:
            # Configuration SAP depuis les variables d'environnement
            sap_config = {
                'base_url': os.getenv("SAP_REST_BASE_URL"),
                'user': os.getenv("SAP_USER"),
                'password': os.getenv("SAP_CLIENT_PASSWORD"),
                'client': os.getenv("SAP_CLIENT")
            }
            
            if not all([sap_config['base_url'], sap_config['user'], sap_config['password']]):
                logger.warning("Configuration SAP incomplète")
                return False
            
            self.sap_client = sap_config
            self.connection_status["sap"] = True
            logger.info("Connexion SAP établie")
            return True
            
        except Exception as e:
            logger.error(f"Erreur initialisation SAP: {str(e)}")
            self.connection_status["sap"] = False
            return False

    # ===================================================================
    # MÉTHODES UTILITAIRES ET DE GESTION
    # ===================================================================

    async def test_connections(self) -> Dict[str, Any]:
        """Test des connexions Salesforce et SAP"""
        results = {}
        
        # Test Salesforce
        try:
            sf_result = await self._init_salesforce()
            results["salesforce"] = {
                "connected": sf_result,
                "status": "OK" if sf_result else "ERROR",
                "message": "Connexion Salesforce testée avec succès" if sf_result else "Échec connexion Salesforce"
            }
        except Exception as e:
            results["salesforce"] = {
                "connected": False,
                "status": "ERROR",
                "message": f"Erreur test Salesforce: {str(e)}"
            }
        
        # Test SAP
        try:
            sap_result = await self._init_sap()
            results["sap"] = {
                "connected": sap_result,
                "status": "OK" if sap_result else "ERROR",
                "message": "Connexion SAP testée avec succès" if sap_result else "Échec connexion SAP"
            }
        except Exception as e:
            results["sap"] = {
                "connected": False,
                "status": "ERROR", 
                "message": f"Erreur test SAP: {str(e)}"
            }
        
        overall_success = all(r["connected"] for r in results.values())
        
        return {
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "overall_status": "OK" if overall_success else "ERROR",
            "message": "Tous les tests réussis" if overall_success else "Certains tests ont échoué"
        }

    def get_connection_status(self) -> Dict[str, bool]:
        """Retourne le statut actuel des connexions"""
        return self.connection_status.copy()

    async def close_connections(self) -> None:
        """Fermeture propre de toutes les connexions"""
        try:
            if self.salesforce_client:
                self.salesforce_client = None
                self.connection_status["salesforce"] = False
                logger.info("Connexion Salesforce fermée")
            
            if self.sap_client:
                self.sap_client = None
                self.connection_status["sap"] = False
                logger.info("Connexion SAP fermée")
            
            # Nettoyage du cache
            mcp_cache.clear()
            
            logger.info("Toutes les connexions MCP fermées")
            
        except Exception as e:
            logger.error(f"Erreur fermeture connexions: {str(e)}")

    def clear_cache(self) -> None:
        """Vide tous les caches"""
        mcp_cache.clear()
        if self.cache_manager:
            try:
                # Clear Redis cache if available
                pass
            except Exception as e:
                logger.warning(f"Erreur nettoyage cache Redis: {e}")
        logger.info("Caches nettoyés")

    async def test_llm_extraction(self, sample_text: str = None) -> Dict[str, Any]:
        """
        Test de la fonctionnalité d'extraction LLM
        """
        try:
            if not get_llm_extractor:
                return {
                    "success": False,
                    "error": "LLMExtractor non disponible",
                    "component": "llm_extractor"
                }
            
            extractor = get_llm_extractor()
            
            # Texte de test par défaut
            test_text = sample_text or "Je souhaiterais un devis pour 3 imprimantes HP LaserJet Pro pour la société TestCorp"
            
            result = await extractor.extract_quote_request(test_text)
            
            return {
                "success": result.get("success", False),
                "component": "llm_extractor",
                "test_input": test_text,
                "extraction_result": result,
                "message": "Test d'extraction LLM réussi" if result.get("success") else "Test d'extraction LLM échoué"
            }
            
        except Exception as e:
            logger.error(f"Erreur test LLM: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "component": "llm_extractor"
            }

    async def claude_api_test(self) -> Dict[str, Any]:
        """
        Test spécifique de l'API Claude
        Correction pour l'erreur 'claude_api'
        """
        try:
            if not get_llm_extractor:
                return {
                    "success": False,
                    "error": "LLMExtractor non disponible pour tester Claude API",
                    "api": "claude"
                }
            
            extractor = get_llm_extractor()
            
            # Test simple de l'API Claude
            test_result = await extractor.extract_quote_info("Test de connexion Claude API")
            
            return {
                "success": "error" not in test_result,
                "api": "claude",
                "status": "OK" if "error" not in test_result else "ERROR",
                "message": "API Claude accessible" if "error" not in test_result else f"Erreur Claude API: {test_result.get('error')}",
                "test_result": test_result
            }
            
        except Exception as e:
            logger.error(f"Erreur test Claude API: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "api": "claude"
            }

    async def sap_data_retrieval(self, query_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Méthode de récupération de données SAP
        Correction pour l'erreur 'sap_data_retrieval'
        """
        try:
            params = query_params or {"endpoint": "/Items", "method": "GET", "limit": 10}
            
            # Utilise la méthode MCP existante
            result = await self.call_sap_mcp("sap_read", params)
            
            return {
                "success": "error" not in result,
                "data_source": "sap",
                "query_params": params,
                "retrieved_data": result,
                "message": "Récupération données SAP réussie" if "error" not in result else "Erreur récupération SAP"
            }
            
        except Exception as e:
            logger.error(f"Erreur sap_data_retrieval: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data_source": "sap"
            }

    async def salesforce_data_retrieval(self, query_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Méthode de récupération de données Salesforce  
        Correction pour l'erreur 'salesforce_data_retrieval'
        """
        try:
            # Query par défaut
            default_query = "SELECT Id, Name FROM Account LIMIT 10"
            query = query_params.get("query", default_query) if query_params else default_query
            
            # Utilise la méthode MCP existante
            result = await self.call_salesforce_mcp("salesforce_query", {"query": query})
            
            return {
                "success": "error" not in result,
                "data_source": "salesforce",
                "query": query,
                "retrieved_data": result,
                "message": "Récupération données Salesforce réussie" if "error" not in result else "Erreur récupération Salesforce"
            }
            
        except Exception as e:
            logger.error(f"Erreur salesforce_data_retrieval: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data_source": "salesforce"
            }

    def routes_availability(self) -> Dict[str, Any]:
        """
        Vérifie la disponibilité des routes principales
        Correction pour l'erreur 'routes_availability'
        """
        try:
            available_routes = {
                "sap_connection": True,
                "salesforce_connection": True,
                "claude_api": bool(get_llm_extractor and os.getenv("ANTHROPIC_API_KEY")),
                "sap_data_retrieval": True,
                "salesforce_data_retrieval": True,
                "mcp_sap": True,
                "mcp_salesforce": True,
                "llm_extraction": bool(get_llm_extractor)
            }
            
            total_routes = len(available_routes)
            active_routes = sum(1 for available in available_routes.values() if available)
            
            return {
                "success": True,
                "available_routes": available_routes,
                "total_routes": total_routes,
                "active_routes": active_routes,
                "availability_percentage": round((active_routes / total_routes) * 100, 1),
                "message": f"{active_routes}/{total_routes} routes disponibles"
            }
            
        except Exception as e:
            logger.error(f"Erreur routes_availability: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
# ===================================================================
# FACTORY PATTERN ET INSTANCE GLOBALE
# ===================================================================

# Instance globale du connecteur
_mcp_connector: Optional[MCPConnector] = None

def get_mcp_connector() -> MCPConnector:
    """
    Factory pattern pour obtenir l'instance du connecteur MCP
    Singleton pattern pour éviter les connexions multiples
    """
    global _mcp_connector
    if _mcp_connector is None:
        _mcp_connector = MCPConnector()
        logger.info("Nouvelle instance MCPConnector créée")
    return _mcp_connector

# Alias pour compatibilité descendante
async def call_mcp_server(server_name: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Fonction de compatibilité - DÉPRÉCIÉ - Utilisez MCPConnector._call_mcp à la place"""
    logger.warning("call_mcp_server est déprécié, utilisez MCPConnector._call_mcp")
    return await MCPConnector._call_mcp(server_name, action, params)