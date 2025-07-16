# 🔍 Script de validation NOVA - test_nova_fix.py

import asyncio
import aiohttp
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://178.33.233.120:8000"
# BASE_URL = "http://localhost:8000"  # Pour tests locaux

class NovaValidator:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    def log_result(self, test_name, success, message="", data=None):
        """Enregistrer le résultat d'un test"""
        status = "✅ PASS" if success else "❌ FAIL"
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        result = {
            "test": test_name,
            "status": status,
            "timestamp": timestamp,
            "message": message,
            "data": data
        }
        
        self.results.append(result)
        
        if success:
            self.passed += 1
        else:
            self.failed += 1
            
        print(f"[{timestamp}] {status} - {test_name}: {message}")
    
    async def test_health_endpoint(self, session):
        """Test 1: Endpoint de santé"""
        try:
            async with session.get(f"{BASE_URL}/health") as response:
                data = await response.json()
                
                if response.status == 200:
                    self.log_result(
                        "Health Endpoint", 
                        True, 
                        f"Server healthy (status: {response.status})",
                        data
                    )
                else:
                    self.log_result(
                        "Health Endpoint", 
                        False, 
                        f"Health check failed (status: {response.status})"
                    )
                    
        except Exception as e:
            self.log_result("Health Endpoint", False, f"Exception: {str(e)}")
    
    async def test_interface_loading(self, session):
        """Test 2: Chargement de l'interface"""
        try:
            async with session.get(f"{BASE_URL}/api/assistant/interface") as response:
                
                if response.status == 200:
                    content = await response.text()
                    
                    # Vérifier que l'interface contient les éléments essentiels
                    required_elements = [
                        'generateBtn',
                        'mainInput',
                        'generateQuote',
                        'fetch('
                    ]
                    
                    missing_elements = [elem for elem in required_elements if elem not in content]
                    
                    if not missing_elements:
                        self.log_result(
                            "Interface Loading", 
                            True, 
                            "Interface loads with all required elements"
                        )
                    else:
                        self.log_result(
                            "Interface Loading", 
                            False, 
                            f"Missing elements: {', '.join(missing_elements)}"
                        )
                else:
                    self.log_result(
                        "Interface Loading", 
                        False, 
                        f"Interface failed to load (status: {response.status})"
                    )
                    
        except Exception as e:
            self.log_result("Interface Loading", False, f"Exception: {str(e)}")
    
    async def test_generate_quote_endpoints(self, session):
        """Test 3: Endpoints de génération de devis"""
        test_payload = {
            "prompt": "devis pour 3 imprimantes laser",
            "draft_mode": False
        }
        
        endpoints = [
            "/api/assistant/generate_quote",
            "/generate_quote",
            "/devis/generate_quote"
        ]
        
        for endpoint in endpoints:
            try:
                async with session.post(
                    f"{BASE_URL}{endpoint}",
                    json=test_payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Vérifier la structure de la réponse
                        has_success = 'success' in data or 'status' in data
                        has_error_handling = 'error' in data or 'message' in data
                        
                        if has_success and has_error_handling:
                            self.log_result(
                                f"Endpoint {endpoint}", 
                                True, 
                                f"Endpoint functional (status: {response.status})",
                                {"response_keys": list(data.keys())}
                            )
                        else:
                            self.log_result(
                                f"Endpoint {endpoint}", 
                                False, 
                                "Response structure invalid"
                            )
                    else:
                        self.log_result(
                            f"Endpoint {endpoint}", 
                            False, 
                            f"HTTP error (status: {response.status})"
                        )
                        
            except Exception as e:
                self.log_result(f"Endpoint {endpoint}", False, f"Exception: {str(e)}")
    
    async def test_error_handling(self, session):
        """Test 4: Gestion d'erreurs"""
        
        # Test avec prompt vide
        try:
            async with session.post(
                f"{BASE_URL}/generate_quote",
                json={"prompt": "", "draft_mode": False},
                headers={"Content-Type": "application/json"}
            ) as response:
                
                data = await response.json()
                
                if 'error' in data or 'message' in data:
                    self.log_result(
                        "Error Handling (Empty Prompt)", 
                        True, 
                        "Empty prompt correctly handled"
                    )
                else:
                    self.log_result(
                        "Error Handling (Empty Prompt)", 
                        False, 
                        "Empty prompt not handled properly"
                    )
                    
        except Exception as e:
            self.log_result("Error Handling (Empty Prompt)", False, f"Exception: {str(e)}")
        
        # Test avec payload invalide
        try:
            async with session.post(
                f"{BASE_URL}/generate_quote",
                json={"invalid": "payload"},
                headers={"Content-Type": "application/json"}
            ) as response:
                
                data = await response.json()
                
                if 'error' in data or 'message' in data:
                    self.log_result(
                        "Error Handling (Invalid Payload)", 
                        True, 
                        "Invalid payload correctly handled"
                    )
                else:
                    self.log_result(
                        "Error Handling (Invalid Payload)", 
                        False, 
                        "Invalid payload not handled properly"
                    )
                    
        except Exception as e:
            self.log_result("Error Handling (Invalid Payload)", False, f"Exception: {str(e)}")
    
    async def test_diagnostic_interface(self, session):
        """Test 5: Interface de diagnostic"""
        try:
            async with session.get(f"{BASE_URL}/static/diagnostic.html") as response:
                
                if response.status == 200:
                    content = await response.text()
                    
                    # Vérifier que l'interface de diagnostic contient les éléments clés
                    required_elements = [
                        'testHealth',
                        'testEndpoints',
                        'testQuoteGeneration',
                        'fetch('
                    ]
                    
                    missing_elements = [elem for elem in required_elements if elem not in content]
                    
                    if not missing_elements:
                        self.log_result(
                            "Diagnostic Interface", 
                            True, 
                            "Diagnostic interface available and functional"
                        )
                    else:
                        self.log_result(
                            "Diagnostic Interface", 
                            False, 
                            f"Diagnostic interface missing elements: {', '.join(missing_elements)}"
                        )
                else:
                    self.log_result(
                        "Diagnostic Interface", 
                        False, 
                        f"Diagnostic interface not accessible (status: {response.status})"
                    )
                    
        except Exception as e:
            self.log_result("Diagnostic Interface", False, f"Exception: {str(e)}")
    
    async def run_all_tests(self):
        """Exécuter tous les tests"""
        print("🚀 Démarrage des tests de validation NOVA")
        print("=" * 60)
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Tests séquentiels
            await self.test_health_endpoint(session)
            await self.test_interface_loading(session)
            await self.test_generate_quote_endpoints(session)
            await self.test_error_handling(session)
            await self.test_diagnostic_interface(session)
        
        # Résumé final
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DES TESTS")
        print("=" * 60)
        
        total_tests = self.passed + self.failed
        success_rate = (self.passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Tests exécutés: {total_tests}")
        print(f"✅ Réussis: {self.passed}")
        print(f"❌ Échoués: {self.failed}")
        print(f"📈 Taux de réussite: {success_rate:.1f}%")
        
        if self.failed > 0:
            print("\n❌ TESTS ÉCHOUÉS:")
            for result in self.results:
                if "FAIL" in result["status"]:
                    print(f"  - {result['test']}: {result['message']}")
        
        if success_rate >= 80:
            print("\n🎉 NOVA est opérationnel!")
            return True
        else:
            print("\n⚠️  NOVA nécessite des corrections supplémentaires")
            return False

async def main():
    """Fonction principale"""
    validator = NovaValidator()
    
    try:
        success = await validator.run_all_tests()
        
        # Sauvegarder les résultats
        with open("nova_validation_results.json", "w", encoding="utf-8") as f:
            json.dump(validator.results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Résultats sauvegardés dans nova_validation_results.json")
        
        # Code de sortie
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ Erreur lors des tests: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Vérifier la disponibilité des modules
    try:
        import aiohttp
    except ImportError:
        print("❌ Module aiohttp requis. Installez avec:")
        print("pip install aiohttp")
        sys.exit(1)
    
    # Lancer les tests
    asyncio.run(main())