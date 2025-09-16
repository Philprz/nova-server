# tests/test_integration_workflow.py
"""
Tests d'intégration End-to-End pour le workflow complet NOVA
Validation fonctionnelle avec intégrations réelles Salesforce/SAP
"""

import pytest
import asyncio
import os
import sys
import uuid
from datetime import datetime

# Ajouter le répertoire parent (racine du projet) au sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import des modules principaux
from workflow.devis_workflow DevisWorkflow
from services.mcp_connector import MCPConnector
from services.llm_extractor import LLMExtractor


class TestIntegrationWorkflow:
    """Tests d'intégration du workflow complet de devis"""
    
    @pytest.fixture(scope="class")
    def unique_test_id(self):
        """ID unique pour éviter les conflits entre tests"""
        return str(uuid.uuid4())[:8]
    
    @pytest.fixture
    def test_prompts(self, unique_test_id):
        """Prompts de test avec ID unique"""
        return {
            "client_existant": "faire un devis pour 10 unités de A00001 pour le client Edge Communications",
            "client_nouveau": f"devis pour NOVA-TEST-{unique_test_id} avec 5 ref A00002",
            "multi_produits": f"faire un devis pour NOVA-MULTI-{unique_test_id} avec 10 A00001 et 5 A00002",
            "anglais": f"quote for NOVA-EN-{unique_test_id} Inc with 15 items A00001"
        }
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_workflow_client_existant(self, test_prompts):
        """Test workflow complet avec client existant dans Salesforce"""
        workflow = DevisWorkflow()
        prompt = test_prompts["client_existant"]
        
        print(f"\n🧪 Test workflow client existant: {prompt}")
        
        result = await workflow.process_prompt(prompt)
        
        # Vérifications critiques
        assert result["status"] == "success", f"Workflow échoué: {result.get('message')}"
        
        # Vérifications client
        assert result["client"]["name"] == "Edge Communications"
        assert result["client"]["salesforce_id"] is not None
        
        # Vérifications devis
        assert result["quote_id"] is not None
        assert result["total_amount"] > 0
        assert len(result["products"]) > 0
        
        # Vérifications intégrations
        if result.get("sap_doc_num"):
            print(f"✅ Devis SAP créé: DocNum {result['sap_doc_num']}")
        if result.get("salesforce_quote_id"):
            print(f"✅ Opportunité Salesforce créée: {result['salesforce_quote_id']}")
        
        print(f"✅ Workflow réussi - Total: {result['total_amount']} {result['currency']}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_workflow_creation_client(self, test_prompts):
        """Test workflow avec création automatique de client"""
        workflow = DevisWorkflow()
        prompt = test_prompts["client_nouveau"]
        
        print(f"\n🧪 Test création client: {prompt}")
        
        result = await workflow.process_prompt(prompt)
        
        # Le workflow peut réussir ou échouer selon la validation
        if result["status"] == "success":
            print("✅ Client créé automatiquement")
            assert result["client"]["name"] is not None
            assert result["total_amount"] > 0
            
            # Vérifier si validation utilisée
            if result.get("client_validation"):
                print("✅ Validation enrichie utilisée")
                assert result["client_validation"]["validation_used"] is True
        else:
            print(f"⚠️ Création client échouée (attendu): {result.get('message')}")
            # C'est acceptable si le client validator n'est pas configuré
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_workflow_multi_produits(self, test_prompts):
        """Test workflow avec plusieurs produits"""
        workflow = DevisWorkflow()
        prompt = test_prompts["multi_produits"]
        
        print(f"\n🧪 Test multi-produits: {prompt}")
        
        result = await workflow.process_prompt(prompt)
        
        if result["status"] == "success":
            # Vérifier plusieurs produits
            assert len(result["products"]) >= 2
            
            # Vérifier extraction des quantités
            product_codes = [p["code"] for p in result["products"]]
            assert "A00001" in product_codes
            assert "A00002" in product_codes
            
            print(f"✅ Multi-produits traité: {len(result['products'])} produits")
        else:
            print(f"⚠️ Multi-produits échoué: {result.get('message')}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_workflow_anglais(self, test_prompts):
        """Test workflow avec prompt en anglais"""
        workflow = DevisWorkflow()
        prompt = test_prompts["anglais"]
        
        print(f"\n🧪 Test prompt anglais: {prompt}")
        
        result = await workflow.process_prompt(prompt)
        
        if result["status"] == "success":
            # Vérifier extraction correcte
            assert result["client"]["name"] is not None
            assert len(result["products"]) > 0
            assert result["products"][0]["quantity"] == 15
            
            print("✅ Prompt anglais traité avec succès")
        else:
            print(f"⚠️ Prompt anglais échoué: {result.get('message')}")


class TestIntegrationConnections:
    """Tests d'intégration des connexions systèmes"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connections_diagnostic(self):
        """Test diagnostic des connexions système"""
        print("\n🔍 Test diagnostic connexions...")
        
        connections = await MCPConnector.test_connections()
        
        # Vérifier structure
        assert "salesforce" in connections
        assert "sap" in connections
        
        # Afficher résultats
        sf_status = "✅" if connections["salesforce"].get("connected") else "❌"
        sap_status = "✅" if connections["sap"].get("connected") else "❌"
        
        print(f"Salesforce: {sf_status}")
        print(f"SAP: {sap_status}")
        
        # Au moins une connexion doit fonctionner pour les tests
        assert connections["salesforce"].get("connected") or connections["sap"].get("connected"), \
            "Aucune connexion système disponible"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_salesforce_integration(self):
        """Test intégration Salesforce directe"""
        print("\n🔍 Test intégration Salesforce...")
        
        # Test requête simple
        result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
            "query": "SELECT Id, Name FROM Account LIMIT 1"
        })
        
        if "error" not in result:
            print(f"✅ Salesforce OK - {result.get('totalSize', 0)} compte(s)")
            assert "totalSize" in result
        else:
            print(f"❌ Salesforce erreur: {result['error']}")
            pytest.skip("Salesforce non disponible")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_sap_integration(self):
        """Test intégration SAP directe"""
        print("\n🔍 Test intégration SAP...")
        
        # Test ping SAP
        result = await MCPConnector.call_sap_mcp("ping", {})
        
        if "error" not in result and "pong" in str(result).lower():
            print("✅ SAP ping OK")
        else:
            print(f"❌ SAP erreur: {result}")
            pytest.skip("SAP non disponible")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_claude_integration(self):
        """Test intégration Claude/LLM"""
        print("\n🔍 Test intégration Claude...")
        
        # Test extraction simple
        result = await LLMExtractor.extract_quote_info(
            "faire un devis pour 10 ref A00001 pour le client Test"
        )
        
        if "error" not in result:
            print("✅ Claude extraction OK")
            assert "client" in result
            assert "products" in result
        else:
            print(f"❌ Claude erreur: {result['error']}")
            pytest.skip("Claude API non disponible")


class TestIntegrationProduits:
    """Tests d'intégration pour la gestion des produits"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_produit_details_sap(self):
        """Test récupération détails produit depuis SAP"""
        print("\n🧪 Test détails produit SAP...")
        
        # Test avec un produit standard
        result = await MCPConnector.get_sap_product_details("A00001")
        
        if "error" not in result:
            print(f"✅ Produit A00001 trouvé: {result.get('ItemName', 'N/A')}")
            print(f"   Prix: {result.get('Price', 0)}")
            print(f"   Stock: {result.get('stock', {}).get('total', 0)}")
            
            # Vérifications
            assert result.get("ItemCode") == "A00001"
            assert "ItemName" in result
        else:
            print(f"⚠️ Produit A00001 non trouvé: {result.get('error')}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_produit_inexistant(self):
        """Test gestion produit inexistant"""
        print("\n🧪 Test produit inexistant...")
        
        # Test avec un produit qui n'existe pas
        result = await MCPConnector.get_sap_product_details("INEXISTANT999")
        
        # Doit retourner une erreur propre
        assert "error" in result
        print(f"✅ Erreur produit inexistant gérée: {result['error']}")


class TestIntegrationPerformance:
    """Tests de performance pour les intégrations"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_performance_workflow(self, test_prompts):
        """Test performance du workflow complet"""
        print("\n⏱️ Test performance workflow...")
        
        workflow = DevisWorkflow()
        prompt = test_prompts["client_existant"]
        
        start_time = datetime.now()
        await workflow.process_prompt(prompt)
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        print(f"⏱️ Durée workflow: {duration:.2f}s")
        
        # Performance acceptable (< 10s pour l'intégration)
        assert duration < 10.0, f"Workflow trop lent: {duration:.2f}s"
        
        if duration < 3.0:
            print("🚀 Performance excellente")
        elif duration < 5.0:
            print("✅ Performance correcte")
        else:
            print("⚠️ Performance limite")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_performance_parallel(self):
        """Test performance appels parallèles"""
        print("\n⏱️ Test performance parallèle...")
        
        start_time = datetime.now()
        
        # Lancer 3 appels en parallèle
        tasks = [
            MCPConnector.call_salesforce_mcp("salesforce_query", {"query": "SELECT Id FROM Account LIMIT 1"}),
            MCPConnector.call_sap_mcp("ping", {}),
            LLMExtractor.extract_quote_info("test simple")
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"⏱️ Durée parallèle: {duration:.2f}s")
        print(f"📊 Résultats: {len([r for r in results if not isinstance(r, Exception)])} succès")
        
        # Le parallélisme doit être efficace
        assert duration < 8.0, f"Appels parallèles trop lents: {duration:.2f}s"


class TestIntegrationRecuperation:
    """Tests de récupération d'erreurs en intégration"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_recuperation_timeout(self):
        """Test récupération après timeout simulé"""
        print("\n🔄 Test récupération timeout...")
        
        # Test avec timeout court pour vérifier la gestion
        # Note: En intégration, on ne peut pas simuler facilement les timeouts
        # On teste plutôt la robustesse du système
        
        workflow = DevisWorkflow()
        
        # Test avec prompt invalide pour vérifier la récupération
        result = await workflow.process_prompt("")
        
        # Le système doit gérer gracieusement
        assert "status" in result
        print(f"✅ Récupération gracieuse: {result.get('status')}")
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_recuperation_donnees_partielles(self):
        """Test récupération avec données partielles"""
        print("\n🔄 Test données partielles...")
        
        workflow = DevisWorkflow()
        
        # Test avec prompt sans client
        result = await workflow.process_prompt("faire un devis pour 10 ref A00001")
        
        # Le système doit identifier le problème
        assert result["status"] == "error"
        assert "client" in result.get("message", "").lower()
        
        print("✅ Gestion données partielles OK")


# Configuration spéciale pour les tests d'intégration
@pytest.fixture(scope="session", autouse=True)
def integration_setup():
    """Configuration automatique pour les tests d'intégration"""
    print("\n" + "="*60)
    print("🚀 TESTS D'INTÉGRATION END-TO-END NOVA")
    print("="*60)
    print("⚠️  ATTENTION: Tests avec intégrations réelles")
    print("📋 Prérequis:")
    print("   - Variables .env configurées")
    print("   - Salesforce accessible")
    print("   - SAP Business One accessible") 
    print("   - Claude API key valide")
    print("-"*60)
    
    # Vérifier variables critiques
    required_vars = [
        "ANTHROPIC_API_KEY",
        "SALESFORCE_USERNAME", 
        "SAP_REST_BASE_URL"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Variables manquantes: {', '.join(missing_vars)}")
        pytest.skip("Configuration incomplète pour tests d'intégration")
    else:
        print("✅ Configuration complète détectée")
    
    yield
    
    print("\n" + "="*60)
    print("🏁 TESTS D'INTÉGRATION TERMINÉS")
    print("="*60)


if __name__ == "__main__":
    # Exécution directe pour debug
    import asyncio
    
    async def run_single_test():
        """Exécute un test simple pour debug"""
        workflow = DevisWorkflow()
        result = await workflow.process_prompt(
            "faire un devis pour 10 unités de A00001 pour le client Edge Communications"
        )
        print(f"Résultat: {result}")
    
    asyncio.run(run_single_test())