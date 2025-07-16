#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests d'intégration pour l'agent de recherche d'entreprises dans NOVA
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Ajout du répertoire parent pour l'import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.company_search_service import company_search_service
from services.client_validator import ClientValidator

class CompanySearchIntegrationTest:
    """Tests d'intégration pour l'agent de recherche d'entreprises"""
    
    def __init__(self):
        self.test_results = []
    
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log des résultats de test"""
        result = {
            'test_name': test_name,
            'success': success,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
    
    async def test_service_initialization(self):
        """Test d'initialisation du service"""
        try:
            # Test que le service est initialisé
            self.log_test(
                "Service Initialization", 
                company_search_service.agent is not None,
                "Service d'agent de recherche initialisé"
            )
            
            # Test des statistiques du cache
            stats = await company_search_service.get_cache_stats()
            self.log_test(
                "Cache Stats", 
                'total_entries' in stats,
                f"Cache stats: {stats}"
            )
            
        except Exception as e:
            self.log_test("Service Initialization", False, str(e))
    
    async def test_siren_validation(self):
        """Test de validation SIREN"""
        test_cases = [
            ("542051180", True),   # SIREN valide (Total)
            ("123456789", False),  # SIREN invalide
            ("", False),           # SIREN vide
            ("ABC123456", False),  # SIREN avec lettres
        ]
        
        for siren, expected in test_cases:
            try:
                result = await company_search_service.validate_siren(siren)
                success = result['valid'] == expected
                self.log_test(
                    f"SIREN Validation ({siren})",
                    success,
                    f"Expected: {expected}, Got: {result['valid']}"
                )
            except Exception as e:
                self.log_test(f"SIREN Validation ({siren})", False, str(e))
    
    async def test_company_search_by_siren(self):
        """Test de recherche par SIREN"""
        try:
            # Test avec SIREN Total
            result = await company_search_service.get_company_by_siren("542051180")
            
            success = result['success'] and result['company']['siren'] == "542051180"
            self.log_test(
                "Company Search by SIREN",
                success,
                f"Trouvé: {result['company']['denomination'] if success else 'Non trouvé'}"
            )
            
        except Exception as e:
            self.log_test("Company Search by SIREN", False, str(e))
    
    async def test_company_search_by_name(self):
        """Test de recherche par nom"""
        test_companies = [
            "Total",
            "Société Générale",
            "Orange",
            "Rondot Group",  # Votre exemple
        ]
        
        for company_name in test_companies:
            try:
                result = await company_search_service.search_company(company_name)
                
                success = result['success'] and result['companies_found'] > 0
                self.log_test(
                    f"Company Search by Name ({company_name})",
                    success,
                    f"Trouvé: {result['companies_found']} entreprises"
                )
                
            except Exception as e:
                self.log_test(f"Company Search by Name ({company_name})", False, str(e))
    
    async def test_suggestions(self):
        """Test des suggestions"""
        try:
            suggestions = await company_search_service.get_suggestions("Total")
            
            success = len(suggestions) > 0
            self.log_test(
                "Suggestions",
                success,
                f"Suggestions: {suggestions}"
            )
            
        except Exception as e:
            self.log_test("Suggestions", False, str(e))
    
    async def test_client_enrichment(self):
        """Test d'enrichissement client"""
        test_client = {
            'company_name': 'Total',
            'email': 'contact@total.com',
            'phone': '01 23 45 67 89'
        }
        
        try:
            enriched_data = await company_search_service.enrich_client_data(test_client)
            
            success = 'enriched_data' in enriched_data
            self.log_test(
                "Client Enrichment",
                success,
                f"Enrichi: {success}, SIREN: {enriched_data.get('enriched_data', {}).get('siren')}"
            )
            
        except Exception as e:
            self.log_test("Client Enrichment", False, str(e))
    
    async def test_integration_with_validator(self):
        """Test d'intégration avec le validateur client"""
        try:
            # Test avec le validateur client enrichi
            validator = ClientValidator()
            
            test_client = {
                'company_name': 'Société Générale',
                'email': 'contact@sg.com'
            }
            
            # Si la méthode enrichie existe
            if hasattr(validator, 'validate_client_data_enriched'):
                result = await validator.validate_client_data_enriched(test_client)
                success = 'enhanced_with_agent' in result
                self.log_test(
                    "Integration with Validator",
                    success,
                    f"Validation enrichie: {success}"
                )
            else:
                self.log_test(
                    "Integration with Validator",
                    False,
                    "Méthode validate_client_data_enriched non trouvée"
                )
            
        except Exception as e:
            self.log_test("Integration with Validator", False, str(e))
    
    async def test_export_functionality(self):
        """Test de fonctionnalité d'export"""
        try:
            # Recherche d'entreprises à exporter
            search_result = await company_search_service.search_company("Total")
            
            if search_result['success'] and search_result['companies']:
                # Test export JSON
                json_filename = await company_search_service.export_search_results(
                    search_result['companies'], 
                    'json'
                )
                
                success = json_filename and os.path.exists(json_filename)
                self.log_test(
                    "Export JSON",
                    success,
                    f"Fichier: {json_filename}"
                )
                
                # Test export CSV
                csv_filename = await company_search_service.export_search_results(
                    search_result['companies'], 
                    'csv'
                )
                
                success = csv_filename and os.path.exists(csv_filename)
                self.log_test(
                    "Export CSV",
                    success,
                    f"Fichier: {csv_filename}"
                )
                
            else:
                self.log_test("Export Functionality", False, "Aucune entreprise trouvée pour l'export")
                
        except Exception as e:
            self.log_test("Export Functionality", False, str(e))
    
    async def run_all_tests(self):
        """Exécute tous les tests"""
        print("🧪 TESTS D'INTÉGRATION AGENT DE RECHERCHE D'ENTREPRISES")
        print("=" * 60)
        
        # Liste des tests à exécuter
        tests = [
            self.test_service_initialization,
            self.test_siren_validation,
            self.test_company_search_by_siren,
            self.test_company_search_by_name,
            self.test_suggestions,
            self.test_client_enrichment,
            self.test_integration_with_validator,
            self.test_export_functionality,
        ]
        
        # Exécution des tests
        for test in tests:
            try:
                await test()
            except Exception as e:
                self.log_test(test.__name__, False, f"Erreur test: {e}")
        
        # Résumé des résultats
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DES TESTS")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"Total: {total_tests} tests")
        print(f"✅ Réussis: {passed_tests}")
        print(f"❌ Échoués: {failed_tests}")
        print(f"📈 Taux de réussite: {(passed_tests/total_tests)*100:.1f}%")
        
        # Sauvegarde des résultats
        await self.save_test_results()
        
        return passed_tests == total_tests
    
    async def save_test_results(self):
        """Sauvegarde les résultats de test"""
        try:
            # Créer le dossier de logs s'il n'existe pas
            os.makedirs("logs", exist_ok=True)
            
            # Nom du fichier avec timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"logs/company_search_integration_test_{timestamp}.json"
            
            # Sauvegarde
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            
            print(f"📁 Résultats sauvegardés dans: {filename}")
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde: {e}")


async def main():
    """Fonction principale"""
    tester = CompanySearchIntegrationTest()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 TOUS LES TESTS SONT PASSÉS!")
        print("✅ L'agent de recherche d'entreprises est prêt pour l'intégration.")
    else:
        print("\n⚠️  CERTAINS TESTS ONT ÉCHOUÉ")
        print("❌ Vérifiez les erreurs et corrigez avant l'intégration.")
    
    return success


if __name__ == "__main__":
    # Exécution des tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)