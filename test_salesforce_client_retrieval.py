# Test de la méthode de récupération client Salesforce
# Fichier: test_salesforce_client_method.py

import asyncio
import sys
import os
from datetime import datetime

# Ajout du chemin parent pour importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from managers.client_manager import ClientManager
from services.mcp_connector import MCPConnector
import logging

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SalesforceClientRetrievalTest:
    """Test unitaire pour la récupération client Salesforce"""
    
    def __init__(self):
        self.mcp_connector = MCPConnector()
        self.client_manager = ClientManager()
        self.test_results = []
    
    async def test_salesforce_connection(self):
        """Test de connexion Salesforce"""
        logger.info("🔍 Test connexion Salesforce...")
        
        try:
            result = await self.mcp_connector.test_connections()
            
            sf_status = result.get("salesforce", {})
            if sf_status.get("success", False):
                logger.info("✅ Connexion Salesforce OK")
                return True
            else:
                # AMÉLIORATION : Diagnostic détaillé
                error_detail = sf_status.get("error", "Erreur inconnue")
                logger.error(f"❌ Connexion Salesforce échouée: {error_detail}")
                
                # Test alternatif direct
                test_query = "SELECT Id, Name FROM Account LIMIT 1"
                direct_test = await self.mcp_connector.call_salesforce_mcp("salesforce_query", {"query": test_query})
                
                if "error" not in direct_test and direct_test.get("records"):
                    logger.info("✅ Test direct Salesforce réussi - connexion fonctionnelle")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception test connexion: {str(e)}")
            return False
    
    async def test_direct_soql_query(self):
        """Test requête SOQL directe"""
        logger.info("🔍 Test requête SOQL directe...")
        
        try:
            # Requête simple pour récupérer quelques comptes
            query = """
                SELECT Id, Name, AccountNumber, Phone,  
                       BillingCity, BillingCountry, CreatedDate
                FROM Account 
                LIMIT 5
            """
            
            result = await self.mcp_connector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            if "error" not in result and result.get("records"):
                records_count = len(result.get("records", []))
                logger.info(f"✅ Requête SOQL réussie: {records_count} enregistrements")
                
                # Afficher les détails du premier enregistrement
                if records_count > 0:
                    first_record = result["records"][0]
                    logger.info(f"Premier enregistrement: {first_record.get('Name')} (ID: {first_record.get('Id')})")
                
                return True
            else:
                error = result.get("error", "Aucun enregistrement trouvé")
                logger.error(f"❌ Requête SOQL échouée: {error}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception requête SOQL: {str(e)}")
            return False
    
    async def test_client_search_by_name(self, client_name: str = "Edge"):
        """Test recherche client par nom"""
        logger.info(f"🔍 Test recherche client: {client_name}")
        
        try:
            # Utiliser la méthode _search_salesforce_client du ClientManager
            result = await self.client_manager._search_salesforce_client(client_name)
            
            if result.get("found"):
                client_data = result.get("data", {})
                logger.info(f"✅ Client trouvé: {client_data.get('Name')} (ID: {client_data.get('Id')})")
                logger.info(f"   Ville: {client_data.get('BillingCity', 'N/A')}")
                logger.info(f"   Téléphone: {client_data.get('Phone', 'N/A')}")
                return True
            else:
                logger.warning(f"⚠️ Client '{client_name}' non trouvé")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception recherche client: {str(e)}")
            return False
    
    async def test_client_search_with_special_chars(self):
        """Test recherche avec caractères spéciaux"""
        logger.info("🔍 Test recherche avec caractères spéciaux...")
        
        test_names = [
            "D'Artagnan & Co",
            "L'Entreprise",
            "société-test"
        ]
        
        success_count = 0
        for name in test_names:
            try:
                result = await self.client_manager._search_salesforce_client(name)
                # Même si non trouvé, l'important est qu'il n'y ait pas d'erreur
                if "error" not in result:
                    success_count += 1
                    logger.info(f"✅ Recherche '{name}' sans erreur")
                else:
                    logger.error(f"❌ Erreur recherche '{name}': {result.get('error')}")
                    
            except Exception as e:
                logger.error(f"❌ Exception recherche '{name}': {str(e)}")
        
        return success_count == len(test_names)
    
    async def test_client_manager_search_method(self):
        """Test méthode search_client du ClientManager"""
        logger.info("🔍 Test méthode ClientManager.search_client...")
        
        try:
            # Test avec un nom générique
            result = await self.client_manager.search_client("Communications")
            
            if result.get("found"):
                source = result.get("source", "unknown")
                client_name = result.get("data", {}).get("Name", "N/A")
                logger.info(f"✅ Client trouvé via {source}: {client_name}")
                return True
            elif "suggestions" in result:
                suggestions_count = len(result.get("suggestions", []))
                logger.info(f"⚠️ Client non trouvé, {suggestions_count} suggestions générées")
                return True  # Les suggestions sont aussi un succès
            else:
                logger.warning("⚠️ Aucun résultat ni suggestion")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception test ClientManager: {str(e)}")
            return False
    
    async def test_comprehensive_client_data_extraction(self):
        """Test extraction complète des données client"""
        logger.info("🔍 Test extraction données complètes...")
        
        try:
            # ⚠️ CORRECTION : Supprimer Email, Website non disponible
            query = """
                SELECT Id, Name, AccountNumber, Phone,
                    BillingStreet, BillingCity, BillingPostalCode, BillingCountry, BillingState,
                    ShippingStreet, ShippingCity, ShippingPostalCode, ShippingCountry, ShippingState,
                    Industry, Type, NumberOfEmployees,
                    CreatedDate, LastModifiedDate, Description
                FROM Account 
                WHERE Name != '' 
                LIMIT 3
            """
            
            result = await self.mcp_connector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            if result.get("records"):
                for i, record in enumerate(result["records"]):
                    logger.info(f"📋 Enregistrement {i+1}:")
                    logger.info(f"   Nom: {record.get('Name', 'N/A')}")
                    logger.info(f"   Secteur: {record.get('Industry', 'N/A')}")
                    logger.info(f"   Ville: {record.get('BillingCity', 'N/A')}")
                    logger.info(f"   Pays: {record.get('BillingCountry', 'N/A')}")
                
                logger.info("✅ Extraction données complètes réussie")
                return True
            else:
                logger.error("❌ Aucune donnée extraite")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception extraction données: {str(e)}")
            return False
    
    async def run_all_tests(self):
        """Exécuter tous les tests"""
        logger.info("🚀 Début des tests de récupération client Salesforce")
        logger.info("="*60)
        
        tests = [
            ("Connexion Salesforce", self.test_salesforce_connection),
            ("Requête SOQL directe", self.test_direct_soql_query),
            ("Recherche client par nom", self.test_client_search_by_name),
            ("Recherche caractères spéciaux", self.test_client_search_with_special_chars),
            ("Méthode ClientManager", self.test_client_manager_search_method),
            ("Extraction données complètes", self.test_comprehensive_client_data_extraction)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_method in tests:
            logger.info(f"\n📝 {test_name}...")
            try:
                success = await test_method()
                if success:
                    passed_tests += 1
                    self.test_results.append(f"✅ {test_name}: PASSED")
                else:
                    self.test_results.append(f"❌ {test_name}: FAILED")
            except Exception as e:
                logger.error(f"❌ Erreur critique dans {test_name}: {str(e)}")
                self.test_results.append(f"💥 {test_name}: ERROR - {str(e)}")
        
        # Résumé final
        logger.info("\n" + "="*60)
        logger.info("📊 RÉSULTATS DES TESTS")
        logger.info("="*60)
        
        for result in self.test_results:
            logger.info(result)
        
        success_rate = (passed_tests / total_tests) * 100
        logger.info(f"\n🎯 Taux de réussite: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        if success_rate >= 80:
            logger.info("🎉 Tests majoritairement réussis - Méthode récupération client opérationnelle")
        elif success_rate >= 50:
            logger.info("⚠️ Tests partiellement réussis - Améliorations nécessaires")
        else:
            logger.info("🚨 Tests majoritairement échoués - Révision complète requise")
        
        return success_rate >= 80

async def main():
    """Point d'entrée principal"""
    tester = SalesforceClientRetrievalTest()
    success = await tester.run_all_tests()
    return success

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        print(f"\n🏁 Tests terminés - Succès: {result}")
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrompus par l'utilisateur")
    except Exception as e:
        print(f"\n💥 Erreur fatale: {str(e)}")