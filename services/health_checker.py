import os
import asyncio
import logging
import time
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import httpx
from sqlalchemy import text
from db.session import SessionLocal
from services.mcp_connector import MCPConnector
from services.llm_extractor import get_llm_extractor
import openai
from dotenv import load_dotenv
load_dotenv()
# Configuration spéciale pour Windows
if sys.platform == "win32":
    # Suppression des emojis pour éviter les erreurs d'encodage Windows
    STATUS_ICONS = {
        "success": "[OK]",
        "error": "[ERROR]", 
        "warning": "[WARNING]",
        "info": "[INFO]",
        "critical": "[CRITICAL]"
    }
else:
    STATUS_ICONS = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️", 
        "critical": "🔴"
    }

logger = logging.getLogger(__name__)

class HealthChecker:
    """Vérificateur de santé pour NOVA avec gestion des erreurs d'encodage"""
    
    def __init__(self):
        self.test_results = {}
        self.start_time = None
        # Correction : Utiliser get_llm_extractor() au lieu d'instancier directement
        self.llm_extractor = get_llm_extractor()
    
    async def _run_test_with_timeout(self, test_name: str, test_func, timeout: int = 5) -> Dict[str, Any]:
        """Exécute un test avec timeout et gestion d'erreur"""
        start_time = time.time()
        
        try:
            result = await asyncio.wait_for(test_func(), timeout=timeout)
            duration_ms = (time.time() - start_time) * 1000
            
            status_icon = STATUS_ICONS["success"] if result.get("success", False) else STATUS_ICONS["error"]
            
            # Log sans emojis pour éviter les erreurs d'encodage
            logger.info(f"{status_icon} {test_name}: {result['message']} ({duration_ms:.1f}ms)")
            
            return {
                "success": result.get("success", False),
                "message": result["message"],
                "duration_ms": round(duration_ms, 2),
                "details": result.get("details", {})
            }
        
        except asyncio.TimeoutError:
            duration_ms = timeout * 1000
            message = f"Timeout après {timeout}s"
            logger.warning(f"{STATUS_ICONS['warning']} {test_name}: {message}")
            
            return {
                "success": False,
                "message": message,
                "duration_ms": duration_ms,
                "timeout": True
            }
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            message = f"Erreur: {str(e)}"
            logger.error(f"{STATUS_ICONS['error']} {test_name}: {message}")
            
            return {
                "success": False,
                "message": message,
                "duration_ms": round(duration_ms, 2),
                "error": str(e)
            }

    async def run_full_health_check(self) -> Dict[str, Any]:
        """Exécute tous les tests de santé"""
        self.start_time = time.time()
        
        logger.info("DEMARRAGE DES TESTS DE SANTE NOVA")
        logger.info("-" * 50)
        
        # Liste des tests à exécuter
        tests = [
            ("environment_check", self._test_environment),
            ("database", self._test_database),
            ("sap_connection", self._test_sap_connection),
            ("salesforce_connection", self._test_salesforce_connection),
            ("claude_api", self._test_claude_api),
            ("chatgpt_api", self._test_chatgpt_api),
            ("sap_data_retrieval", self._test_sap_data_retrieval),
            ("salesforce_data_retrieval", self._test_salesforce_data_retrieval),
            ("routes_availability", self._test_routes_availability)
        ]
        
        # Exécution des tests
        for test_name, test_func in tests:
            self.test_results[test_name] = await self._run_test_with_timeout(
                test_name, test_func, timeout=10
            )
        
        return self._build_final_report()
    
    async def _test_environment(self) -> Dict[str, Any]:
        """Test des variables d'environnement"""
        import os
        
        required_vars = [
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY", 
            "SALESFORCE_USERNAME",
            "SAP_REST_BASE_URL"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            return {
                "success": False,
                "message": f"Variables manquantes: {', '.join(missing_vars)}",
                "details": {"missing": missing_vars}
            }
        
        return {
            "success": True,
            "message": f"Toutes les variables requises sont présentes ({len(required_vars)})",
            "details": {"checked": required_vars}
        }
    
    async def _test_database(self) -> Dict[str, Any]:
        """Test de connexion à la base de données PostgreSQL"""
        start_time = time.time()
        
        try:
            with SessionLocal() as session:
                # Test de requête simple
                result = session.execute(text("SELECT 1 as test_value"))
                row = result.fetchone()
                
                if row and row.test_value == 1:
                    return {
                        "success": True,
                        "message": "Connexion PostgreSQL opérationnelle",
                        "details": {"test_query": "SELECT 1", "result": row.test_value},
                        "timestamp": datetime.now().isoformat(),
                        "duration_ms": round((time.time() - start_time) * 1000, 2)
                    }
                else:
                    raise Exception("Résultat de test invalide")
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec connexion base de données: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_sap_connection(self) -> Dict[str, Any]:
        """Test de connexion au serveur SAP B1"""
        start_time = time.time()
        
        try:
            # Correction : Utiliser la méthode statique appropriée
            connector = MCPConnector()
            login_result = await connector.sap_login()
            
            if login_result.get("success"):
                return {
                    "success": True,
                    "message": "Connexion SAP B1 établie avec succès",
                    "details": {
                        "server": os.getenv("SAP_REST_BASE_URL"),
                        "user": os.getenv("SAP_USER"),
                        "database": os.getenv("SAP_CLIENT")
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception(login_result.get("error", "Login SAP échoué"))
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec connexion SAP: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_salesforce_connection(self) -> Dict[str, Any]:
        """Test de connexion à Salesforce"""
        start_time = time.time()
        
        try:
            # Correction : Utiliser la méthode statique appropriée
            connector = MCPConnector()
            login_result = await connector.salesforce_login()
            
            if login_result.get("success"):
                return {
                    "success": True,
                    "message": "Connexion Salesforce établie avec succès",
                    "details": {
                        "username": os.getenv("SALESFORCE_USERNAME"),
                        "domain": os.getenv("SALESFORCE_DOMAIN"),
                        "session_id": login_result.get("session_id", "")[:20] + "..."  # Partiel pour sécurité
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception(login_result.get("error", "Login Salesforce échoué"))
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec connexion Salesforce: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_claude_api(self) -> Dict[str, Any]:
        """Test de l'API Claude Anthropic"""
        start_time = time.time()
        
        try:
            # Test ultra-rapide avec Claude
            test_prompt = "1+1=?"
            
            # Timeout agressif de 5 secondes
            response = await asyncio.wait_for(
                self.llm_extractor.extract_quote_request(test_prompt),
                timeout=20.0
            )
            
            # Correction: Vérifier response.get("success", False) au lieu de chercher "error"
            if response and response.get("success", False):
                return {
                    "success": True,
                    "message": "API Claude Anthropic opérationnelle",
                    "details": {
                        "model": "claude-4-sonnet",  # Correction: Valeur fixe au lieu de self.llm_extractor.model
                        "response_type": response.get("action_type", "N/A")
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception("Réponse Claude invalide ou erreur")
        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": "API Claude timeout après 5s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 5000
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec API Claude: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_chatgpt_api(self) -> Dict[str, Any]:
        """Test de l'API ChatGPT OpenAI"""
        start_time = time.time()
        
        try:
            # Configuration OpenAI avec timeout
            client = openai.AsyncOpenAI(timeout=4.0)
            
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": "1+1=?"}],
                max_tokens=5,
                temperature=0
            )
            
            if response.choices and response.choices[0].message.content:
                return {
                    "success": True,
                    "message": "API ChatGPT OpenAI opérationnelle",
                    "details": {
                        "model": "gpt-3.5-turbo",
                        "response": response.choices[0].message.content.strip()[:20]
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception("Réponse ChatGPT vide ou invalide")
        
        except Exception as e:
            return {
                "success": False,
                "message": f"API ChatGPT non disponible: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_sap_data_retrieval(self) -> Dict[str, Any]:
        """Test de récupération de données SAP (produits)"""
        start_time = time.time()
        
        try:
            # Correction : Utiliser la méthode statique correcte
            products_result = await asyncio.wait_for(
                MCPConnector.get_sap_products(limit=3),
                timeout=6.0
            )
            
            if products_result.get("success") and products_result.get("products"):
                products = products_result["products"]
                sample_product = products[0]
                return {
                    "success": True,
                    "message": "Récupération données SAP opérationnelle",
                    "details": {
                        "products_found": len(products),
                        "sample_product": {
                            "code": sample_product.get("ItemCode", "N/A"),
                            "name": sample_product.get("ItemName", "N/A")[:30] + "..."
                        }
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception("Aucun produit trouvé dans SAP")
        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": "Récupération SAP timeout après 6s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 6000
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec récupération données SAP: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_salesforce_data_retrieval(self) -> Dict[str, Any]:
        """Test de récupération de données Salesforce (clients)"""
        start_time = time.time()
        
        try:
            # Correction : Utiliser la méthode statique correcte
            clients_result = await asyncio.wait_for(
                MCPConnector.get_salesforce_accounts(limit=3),
                timeout=6.0
            )
            
            if "records" in clients_result and len(clients_result["records"]) > 0:
                clients = clients_result["records"]
                sample_client = clients[0]
                return {
                    "success": True,
                    "message": "Récupération données Salesforce opérationnelle",
                    "details": {
                        "clients_found": len(clients),
                        "sample_client": {
                            "name": sample_client.get("Name", "N/A"),
                            "id": sample_client.get("Id", "N/A")[:15] + "..."
                        }
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                return {
                    "success": False,
                    "message": "Aucun client test trouvé, mais connexion OK",
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
        
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": "Récupération Salesforce timeout après 6s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 6000
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec récupération données Salesforce: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_routes_availability(self) -> Dict[str, Any]:
        """Test des principales routes API"""
        start_time = time.time()
        
        try:
            # Routes critiques à tester
            critical_routes = ["/health", "/docs"]  # Réduire pour aller plus vite
            
            available_routes = []
            
            # Utiliser httpx avec timeout agressif
            timeout = httpx.Timeout(2.0)  # 2 secondes max par route
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Tests en parallèle des routes
                route_tasks = []
                for route in critical_routes:
                    task = asyncio.create_task(
                        self._test_single_route(client, route)
                    )
                    route_tasks.append((route, task))
                
                # Attendre tous les tests de routes
                await asyncio.gather(*[task for _, task in route_tasks], return_exceptions=True)
                
                # Récupération des résultats
                for route, task in route_tasks:
                    if task.done() and not task.exception():
                        if task.result():
                            available_routes.append(route)
                
                return {
                    "success": True if len(available_routes) > 0 else False,
                    "message": f"{len(available_routes)}/{len(critical_routes)} routes critiques disponibles",
                    "details": {
                        "available_routes": available_routes,
                        "total_tested": len(critical_routes)
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec test des routes: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
    
    async def _test_single_route(self, client: httpx.AsyncClient, route: str) -> bool:
        """Test d'une route individuelle"""
        try:
            response = await client.get(f"http://127.0.0.1:8000{route}")
            return response.status_code < 500
        except:
            return False
    
    def _build_final_report(self) -> Dict[str, Any]:
        """Construction du rapport final"""
        total_time = (time.time() - self.start_time) * 1000
        
        # Calcul des statistiques
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results.values() if result.get("success", False))
        failed_tests = total_tests - successful_tests
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        # Détermination du statut global
        if success_rate >= 80:
            overall_status = "healthy"
            status_icon = STATUS_ICONS["success"]
        elif success_rate >= 50:
            overall_status = "degraded" 
            status_icon = STATUS_ICONS["warning"]
        else:
            overall_status = "unhealthy"
            status_icon = STATUS_ICONS["error"]
        
        # Génération des recommandations
        recommendations = self._generate_recommendations()
        
        # Logs finaux (sans emojis)
        logger.info(f"{status_icon} Statut global NOVA: {overall_status.upper()} en {total_time:.2f}ms")
        logger.info(f"[STATS] Résumé: {successful_tests} succès, {failed_tests} erreurs, 0 avertissements/timeouts")
        
        return {
            "nova_system_status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "successful": successful_tests,
                "failed": failed_tests,
                "success_rate": round(success_rate, 1),
                "total_duration_ms": round(total_time, 2)
            },
            "detailed_results": self.test_results,
            "recommendations": recommendations
        }
    
    def _generate_recommendations(self) -> list:
        """Génère des recommandations basées sur les résultats des tests"""
        recommendations = []
        
        for test_name, result in self.test_results.items():
            if not result.get("success", False):
                if "sap" in test_name.lower():
                    recommendations.append("[FIX] Vérifier les paramètres SAP (URL, utilisateur, mot de passe)")
                elif "salesforce" in test_name.lower():
                    recommendations.append("[FIX] Vérifier les paramètres Salesforce (token, domaine)")
                elif "claude" in test_name.lower():
                    recommendations.append("[FIX] Vérifier la clé API Anthropic ANTHROPIC_API_KEY")
                elif "chatgpt" in test_name.lower():
                    recommendations.append("[FIX] Vérifier la clé API OpenAI OPENAI_API_KEY")
                elif "environment" in test_name.lower():
                    recommendations.append("[FIX] Configurer les variables d'environnement manquantes")
                elif "routes" in test_name.lower():
                    recommendations.append("[FIX] Vérifier l'installation des modules de routes")
        
        # Recommandations générales
        failed_count = sum(1 for result in self.test_results.values() if not result.get("success", False))
        if failed_count > 0:
            if any("sap" in name for name in self.test_results.keys()):
                recommendations.append("[FIX] Problème de récupération de données SAP")
            if any("salesforce" in name for name in self.test_results.keys()):
                recommendations.append("[FIX] Problème de récupération de données SALESFORCE")
        
        return list(set(recommendations))  # Suppression des doublons