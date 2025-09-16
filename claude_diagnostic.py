# 🔍 Diagnostic API Claude et Workflow - claude_diagnostic.py

import asyncio
import httpx
import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class ClaudeDiagnostic:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        
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
    
    def test_api_key_format(self):
        """Test 1: Format de la clé API"""
        if not self.api_key:
            self.log_result("API Key Format", False, "ANTHROPIC_API_KEY manquante dans .env")
            return False
        
        if not self.api_key.startswith("sk-ant-"):
            self.log_result("API Key Format", False, "Format de clé API invalide")
            return False
        
        # Masquer la clé pour la sécurité
        masked_key = self.api_key[:10] + "..." + self.api_key[-10:]
        self.log_result("API Key Format", True, f"Clé API valide: {masked_key}")
        return True
    
    async def test_claude_api_connectivity(self):
        """Test 2: Connectivité API Claude"""
        if not self.api_key:
            self.log_result("Claude API Connectivity", False, "Clé API manquante")
            return False
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Test simple avec le modèle utilisé
        payload = {
            "model": "claude-3-7-sonnet-20250219",
            "max_tokens": 100,
            "system": "Tu es un assistant de test. Réponds simplement 'TEST OK'.",
            "messages": [
                {"role": "user", "content": "Test de connectivité"}
            ],
            "temperature": 0.0
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("content", [{}])[0].get("text", "")
                    
                    self.log_result(
                        "Claude API Connectivity", 
                        True, 
                        f"Connexion réussie - Réponse: {content[:50]}..."
                    )
                    return True
                else:
                    try:
                        error_data = response.json()
                        self.log_result(
                            "Claude API Connectivity", 
                            False, 
                            f"Erreur HTTP {response.status_code}: {error_data}"
                        )
                    except:
                        self.log_result(
                            "Claude API Connectivity", 
                            False, 
                            f"Erreur HTTP {response.status_code}: {response.text}"
                        )
                    return False
                    
        except Exception as e:
            self.log_result("Claude API Connectivity", False, f"Exception: {str(e)}")
            return False
    
    async def test_llm_extractor_function(self):
        """Test 3: Fonction LLMExtractor"""
        try:
            # Importer la fonction depuis le module
            sys.path.insert(0, '.')
            from services.llm_extractor import LLMExtractor
            
            # Test avec un prompt simple
            test_prompt = "faire un devis pour 3 imprimantes laser pour la société Test Corp"
            
            result = await LLMExtractor.extract_quote_info(test_prompt)
            
            if "error" in result:
                self.log_result(
                    "LLMExtractor Function", 
                    False, 
                    f"Erreur dans extract_quote_info: {result['error']}"
                )
                return False
            else:
                self.log_result(
                    "LLMExtractor Function", 
                    True, 
                    f"Extraction réussie: {json.dumps(result, indent=2)}"
                )
                return True
                
        except Exception as e:
            self.log_result("LLMExtractor Function", False, f"Exception: {str(e)}")
            return False
    
    async def test_workflow_basic(self):
        """Test 4: Workflow de base"""
        try:
            # Importer le workflow
            sys.path.insert(0, '.')
            from workflow.devis_workflow import DevisWorkflow
            
            # Test avec un workflow simplifié
            workflow = DevisWorkflow()
            
            # Test de la méthode _extract_info_basic_robust (fallback)
            result = await workflow._extract_info_basic_robust("devis pour 3 imprimantes pour Test Corp")
            
            if result and "client" in result:
                self.log_result(
                    "Workflow Basic", 
                    True, 
                    f"Fallback fonctionne: {json.dumps(result, indent=2)}"
                )
                return True
            else:
                self.log_result(
                    "Workflow Basic", 
                    False, 
                    f"Fallback échoue: {result}"
                )
                return False
                
        except Exception as e:
            self.log_result("Workflow Basic", False, f"Exception: {str(e)}")
            return False
    
    async def test_full_workflow(self):
        """Test 5: Workflow complet"""
        try:
            # Importer le workflow
            sys.path.insert(0, '.')
            from workflow.devis_workflow import DevisWorkflow
            
            # Test complet avec un prompt réaliste
            workflow = DevisWorkflow()
            
            result = await workflow.process_prompt(
                "faire un devis pour 3 imprimantes laser pour la société Test Corporation"
            )
            
            if result.get("success") or result.get("status") == "user_interaction_required":
                self.log_result(
                    "Full Workflow", 
                    True, 
                    f"Workflow fonctionne: {result.get('status', 'success')}"
                )
                return True
            else:
                self.log_result(
                    "Full Workflow", 
                    False, 
                    f"Workflow échoue: {result.get('error', 'Erreur inconnue')}"
                )
                return False
                
        except Exception as e:
            self.log_result("Full Workflow", False, f"Exception: {str(e)}")
            return False
    
    async def test_dependencies(self):
        """Test 6: Dépendances système"""
        try:
            # Test des imports critiques
            import httpx
            import dotenv
            
            # Vérifier les services
            services_to_test = [
                ("services.llm_extractor", "LLMExtractor"),
                ("workflow.devis_workflow", "DevisWorkflow"),
                ("services.mcp_connector", "MCPConnector")
            ]
            
            missing_services = []
            
            for module_name, class_name in services_to_test:
                try:
                    module = __import__(module_name, fromlist=[class_name])
                    getattr(module, class_name)
                except ImportError as e:
                    missing_services.append(f"{module_name}: {str(e)}")
            
            if missing_services:
                self.log_result(
                    "Dependencies", 
                    False, 
                    f"Services manquants: {', '.join(missing_services)}"
                )
                return False
            else:
                self.log_result("Dependencies", True, "Tous les services sont disponibles")
                return True
                
        except Exception as e:
            self.log_result("Dependencies", False, f"Exception: {str(e)}")
            return False
    
    async def run_all_tests(self):
        """Exécuter tous les tests"""
        print("🔍 Démarrage du diagnostic Claude et Workflow")
        print("=" * 60)
        
        # Tests séquentiels
        self.test_api_key_format()
        await self.test_claude_api_connectivity()
        await self.test_dependencies()
        await self.test_llm_extractor_function()
        await self.test_workflow_basic()
        await self.test_full_workflow()
        
        # Résumé final
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DU DIAGNOSTIC")
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
        
        # Recommandations
        print("\n🔧 RECOMMANDATIONS:")
        
        failed_tests = [r for r in self.results if "FAIL" in r["status"]]
        
        if any("API Key" in r["test"] for r in failed_tests):
            print("  1. Vérifiez votre clé API Claude dans le fichier .env")
            print("  2. Assurez-vous que la clé commence par 'sk-ant-'")
        
        if any("Connectivity" in r["test"] for r in failed_tests):
            print("  3. Vérifiez votre connexion Internet")
            print("  4. Testez l'accès à https://api.anthropic.com")
        
        if any("LLMExtractor" in r["test"] for r in failed_tests):
            print("  5. Vérifiez le code de services/llm_extractor.py")
            print("  6. Activez les logs DEBUG pour plus de détails")
        
        if any("Workflow" in r["test"] for r in failed_tests):
            print("  7. Vérifiez la configuration du workflow")
            print("  8. Testez les connexions Salesforce/SAP")
        
        return success_rate >= 80

async def main():
    """Fonction principale"""
    diagnostic = ClaudeDiagnostic()
    
    try:
        success = await diagnostic.run_all_tests()
        
        # Sauvegarder les résultats
        with open("claude_diagnostic_results.json", "w", encoding="utf-8") as f:
            json.dump(diagnostic.results, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Résultats sauvegardés dans claude_diagnostic_results.json")
        
        # Code de sortie
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ Erreur lors du diagnostic: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Vérifier httpx
    try:
        import httpx
    except ImportError:
        print("❌ Module httpx requis. Installez avec:")
        print("pip install httpx")
        sys.exit(1)
    
    # Lancer le diagnostic
    asyncio.run(main())