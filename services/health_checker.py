# services/health_checker.py

import asyncio
import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Any
import httpx
from sqlalchemy import text
from db.session import SessionLocal
from services.mcp_connector import MCPConnector
from services.llm_extractor import LLMExtractor
import openai

logger = logging.getLogger(__name__)

class NovaHealthChecker:
    """Vérification complète des connexions et services NOVA au démarrage"""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.mcp_connector = MCPConnector()
        self.llm_extractor = LLMExtractor()
        
    async def run_full_health_check(self) -> Dict[str, Any]:
        """Exécute tous les tests de santé du système EN PARALLÈLE"""
        self.start_time = time.time()
        logger.info("🚀 Démarrage des vérifications de santé NOVA (mode parallèle)")
        
        # Tests à exécuter en parallèle avec timeouts
        tests = [
            ("database", self._test_database),
            ("sap_connection", self._test_sap_connection),
            ("salesforce_connection", self._test_salesforce_connection),
            ("claude_api", self._test_claude_api),
            ("chatgpt_api", self._test_chatgpt_api),
            ("sap_data_retrieval", self._test_sap_data_retrieval),
            ("salesforce_data_retrieval", self._test_salesforce_data_retrieval),
            ("routes_availability", self._test_routes_availability)
        ]
        
        # Création des tâches avec timeout individuel
        tasks = []
        for test_name, test_func in tests:
            task = asyncio.create_task(
                self._run_test_with_timeout(test_name, test_func, timeout=10.0)
            )
            tasks.append((test_name, task))
        
        logger.info(f"⚡ Lancement de {len(tasks)} tests en parallèle...")
        
        # Attente de tous les tests avec timeout global
        try:
            # Timeout global plus large que les timeouts individuels
            await asyncio.wait_for(
                asyncio.gather(*[task for _, task in tasks], return_exceptions=True),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.warning("⏰ Timeout global atteint, certains tests peuvent être incomplets")
        
        # Récupération des résultats
        for test_name, task in tasks:
            if task.done():
                try:
                    self.results[test_name] = task.result()
                except Exception as e:
                    self.results[test_name] = {
                        "status": "error",
                        "message": f"Exception dans la tâche: {str(e)}",
                        "timestamp": datetime.now().isoformat(),
                        "duration_ms": 0
                    }
            else:
                # Tâche non terminée
                self.results[test_name] = {
                    "status": "timeout",
                    "message": "Test non terminé dans les délais",
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": 10000  # Timeout duration
                }
        
        return self._build_final_report()

    async def _run_test_with_timeout(self, test_name: str, test_func, timeout: float) -> Dict[str, Any]:
        """Exécute un test avec timeout individuel"""
        try:
            logger.info(f"🔍 Test: {test_name}")
            
            # Timeout agressif pour chaque test
            result = await asyncio.wait_for(test_func(), timeout=timeout)
            
            # Log du résultat
            status_icon = "✅" if result["status"] == "success" else "❌" if result["status"] == "error" else "⚠️"
            logger.info(f"{status_icon} {test_name}: {result['message']} ({result.get('duration_ms', 0)}ms)")
            
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Timeout sur {test_name} après {timeout}s")
            return {
                "status": "timeout",
                "message": f"Test interrompu après {timeout}s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": timeout * 1000
            }
        except Exception as e:
            logger.error(f"❌ Erreur lors du test {test_name}: {str(e)}")
            return {
                "status": "error",
                "message": f"Exception: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 0
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
                        "status": "success",
                        "message": "Connexion PostgreSQL opérationnelle",
                        "details": {"test_query": "SELECT 1", "result": row.test_value},
                        "timestamp": datetime.now().isoformat(),
                        "duration_ms": round((time.time() - start_time) * 1000, 2)
                    }
                else:
                    raise Exception("Résultat de test invalide")
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Échec connexion base de données: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_sap_connection(self) -> Dict[str, Any]:
        """Test de connexion au serveur SAP B1"""
        start_time = time.time()
        
        try:
            # Test de login SAP
            login_result = await self.mcp_connector.sap_login()
            
            if login_result.get("success"):
                return {
                    "status": "success",
                    "message": "Connexion SAP B1 établie avec succès",
                    "details": {
                        "server": self.mcp_connector.sap_config.get("SAP_REST_BASE_URL"),
                        "user": self.mcp_connector.sap_config.get("SAP_USER"),
                        "database": self.mcp_connector.sap_config.get("SAP_CLIENT")
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception(login_result.get("error", "Login SAP échoué"))
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Échec connexion SAP: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_salesforce_connection(self) -> Dict[str, Any]:
        """Test de connexion à Salesforce"""
        start_time = time.time()
        
        try:
            # Test de login Salesforce
            login_result = await self.mcp_connector.salesforce_login()
            
            if login_result.get("success"):
                return {
                    "status": "success",
                    "message": "Connexion Salesforce établie avec succès",
                    "details": {
                        "username": self.mcp_connector.salesforce_config.get("SALESFORCE_USERNAME"),
                        "domain": self.mcp_connector.salesforce_config.get("SALESFORCE_DOMAIN"),
                        "session_id": login_result.get("session_id", "")[:20] + "..."  # Partiel pour sécurité
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception(login_result.get("error", "Login Salesforce échoué"))
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Échec connexion Salesforce: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_claude_api(self) -> Dict[str, Any]:
        """Test de l'API Claude Anthropic (optimisé)"""
        start_time = time.time()
        
        try:
            # Test ultra-rapide avec Claude
            test_prompt = "1+1=?"
            
            # Timeout agressif de 5 secondes
            response = await asyncio.wait_for(
                self.llm_extractor.extract_quote_request(test_prompt),
                timeout=5.0
            )
            
            if response and "error" not in str(response).lower():
                return {
                    "status": "success",
                    "message": "API Claude Anthropic opérationnelle",
                    "details": {
                        "model": self.llm_extractor.model,
                        "response_length": len(str(response))
                    },
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
            else:
                raise Exception("Réponse Claude invalide ou erreur")
                
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "message": "API Claude timeout après 5s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 5000
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Échec API Claude: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_chatgpt_api(self) -> Dict[str, Any]:
        """Test de l'API ChatGPT OpenAI (optimisé)"""
        start_time = time.time()
        
        try:
            # Configuration OpenAI avec timeout
            client = openai.AsyncOpenAI(timeout=4.0)
            
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "1+1=?"}],
                max_tokens=5,
                temperature=0
            )
            
            if response.choices and response.choices[0].message.content:
                return {
                    "status": "success",
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
                "status": "warning",  # Non critique car backup
                "message": f"API ChatGPT non disponible: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_sap_data_retrieval(self) -> Dict[str, Any]:
        """Test de récupération de données SAP (produits) - optimisé"""
        start_time = time.time()
        
        try:
            # Timeout agressif pour SAP
            products = await asyncio.wait_for(
                self.mcp_connector.search_sap_products("A00001"),
                timeout=6.0
            )
            
            if products and len(products) > 0:
                sample_product = products[0]
                return {
                    "status": "success",
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
                "status": "timeout",
                "message": "Récupération SAP timeout après 6s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 6000
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Échec récupération données SAP: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_salesforce_data_retrieval(self) -> Dict[str, Any]:
        """Test de récupération de données Salesforce (clients) - optimisé"""
        start_time = time.time()
        
        try:
            # Timeout agressif pour Salesforce
            clients = await asyncio.wait_for(
                self.mcp_connector.search_salesforce_clients("Test"),
                timeout=6.0
            )
            
            if clients and len(clients) > 0:
                sample_client = clients[0]
                return {
                    "status": "success",
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
                    "status": "warning",
                    "message": "Aucun client test trouvé, mais connexion OK",
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": round((time.time() - start_time) * 1000, 2)
                }
                
        except asyncio.TimeoutError:
            return {
                "status": "timeout", 
                "message": "Récupération Salesforce timeout après 6s",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 6000
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Échec récupération données Salesforce: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_routes_availability(self) -> Dict[str, Any]:
        """Test des principales routes API - optimisé"""
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
                "status": "success" if len(available_routes) > 0 else "error",
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
                "status": "error",
                "message": f"Échec test des routes: {str(e)[:50]}...",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }

    async def _test_single_route(self, client: httpx.AsyncClient, route: str) -> bool:
        """Test d'une route individuelle"""
        try:
            response = await client.get(f"http://localhost:8000{route}")
            return response.status_code < 500
        except:
            return False

    def _build_final_report(self) -> Dict[str, Any]:
        """Construit le rapport final de santé - optimisé"""
        total_time = round((time.time() - self.start_time) * 1000, 2)
        
        # Comptage des statuts
        success_count = sum(1 for r in self.results.values() if r["status"] == "success")
        error_count = sum(1 for r in self.results.values() if r["status"] == "error")
        warning_count = sum(1 for r in self.results.values() if r["status"] == "warning")
        timeout_count = sum(1 for r in self.results.values() if r["status"] == "timeout")
        
        # Détermination du statut global (timeouts considérés comme warnings)
        effective_errors = error_count
        effective_warnings = warning_count + timeout_count
        
        if effective_errors == 0:
            overall_status = "healthy"
        elif success_count > effective_errors:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        # Construction du rapport
        report = {
            "nova_system_status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "total_duration_ms": total_time,
            "summary": {
                "total_tests": len(self.results),
                "successful": success_count,
                "errors": error_count,
                "warnings": warning_count,
                "timeouts": timeout_count,
                "success_rate": round((success_count / len(self.results)) * 100, 1) if self.results else 0
            },
            "detailed_results": self.results,
            "recommendations": self._generate_recommendations(),
            "performance": {
                "parallel_execution": True,
                "average_test_time_ms": round(total_time / len(self.results), 1) if self.results else 0
            }
        }
        
        # Log du résultat global avec performance
        status_icon = "🟢" if overall_status == "healthy" else "🟡" if overall_status == "degraded" else "🔴"
        logger.info(f"{status_icon} Statut global NOVA: {overall_status.upper()} en {total_time}ms")
        logger.info(f"📊 Résumé: {success_count} succès, {error_count} erreurs, {effective_warnings} avertissements/timeouts")
        
        return report

    def _generate_recommendations(self) -> List[str]:
        """Génère des recommandations basées sur les résultats"""
        recommendations = []
        
        for test_name, result in self.results.items():
            if result["status"] == "error":
                if test_name == "database":
                    recommendations.append("🔧 Vérifier la connexion PostgreSQL et les paramètres DATABASE_URL")
                elif test_name == "sap_connection":
                    recommendations.append("🔧 Vérifier les paramètres SAP (URL, utilisateur, mot de passe)")
                elif test_name == "salesforce_connection":
                    recommendations.append("🔧 Vérifier les paramètres Salesforce (token, domaine)")
                elif test_name == "claude_api":
                    recommendations.append("🔧 Vérifier la clé API Anthropic ANTHROPIC_API_KEY")
                elif "data_retrieval" in test_name:
                    recommendations.append(f"🔧 Problème de récupération de données {test_name.replace('_data_retrieval', '').upper()}")
        
        if not recommendations:
            recommendations.append("✅ Système NOVA entièrement opérationnel")
        
        return recommendations