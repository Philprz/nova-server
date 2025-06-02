#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test du module de validation client complet
"""

import sys
import os
import asyncio
import json
from datetime import datetime
from typing import Dict, Any

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from services.client_validator import ClientValidator
    print("✅ ClientValidator importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import ClientValidator: {e}")
    sys.exit(1)

# Données de test pour différents pays
TEST_CLIENTS = {
    "france_complet": {
        "company_name": "NOVA Technologies France",
        "email": "contact@nova-tech.fr",
        "phone": "+33 1 23 45 67 89",
        "website": "www.nova-tech.fr",
        "billing_street": "123 Avenue des Champs-Élysées",
        "billing_city": "Paris",
        "billing_postal_code": "75008",
        "billing_country": "France",
        "siret": "12345678901234",
        "industry": "Technology"
    },
    
    "usa_complet": {
        "company_name": "NOVA Tech USA Inc",
        "email": "info@novatech-usa.com",
        "phone": "+1 555 123 4567",
        "website": "https://www.novatech-usa.com",
        "billing_street": "123 Silicon Valley Blvd",
        "billing_city": "San Francisco",
        "billing_state": "CA",
        "billing_postal_code": "94105",
        "billing_country": "United States",
        "ein": "123456789"
    },
    
    "uk_complet": {
        "company_name": "NOVA Technologies UK Ltd",
        "email": "hello@nova-uk.co.uk",
        "phone": "+44 20 7123 4567",
        "website": "https://nova-uk.co.uk",
        "billing_street": "123 Oxford Street",
        "billing_city": "London",
        "billing_postal_code": "W1C 1DE",
        "billing_country": "United Kingdom",
        "company_number": "12345678"
    },
    
    "problematique": {
        "company_name": "Test<>&Co",  # Caractères problématiques
        "email": "invalid-email",  # Email invalide
        "phone": "123",  # Téléphone invalide
        "website": "not-a-url",  # URL invalide
        "billing_street": "",
        "billing_city": "",
        "billing_postal_code": "invalid",
        "billing_country": "France",
        "siret": "123"  # SIRET invalide
    },
    
    "minimal": {
        "company_name": "Entreprise Minimale"
        # Données minimales pour tester les avertissements
    }
}

async def test_validator_single(client_data: Dict[str, Any], country: str, test_name: str):
    """Test du validateur pour un client spécifique"""
    print(f"\n{'='*60}")
    print(f"🧪 TEST: {test_name.upper()} ({country})")
    print(f"{'='*60}")
    
    try:
        # Créer le validateur
        validator = ClientValidator()
        
        # Lancer la validation
        print("🔍 Validation en cours...")
        start_time = datetime.now()
        
        result = await validator.validate_complete(client_data, country)
        
        end_time = datetime.now()
        validation_time = (end_time - start_time).total_seconds()
        
        # Afficher les résultats
        print(f"\n📊 RÉSULTATS ({validation_time:.2f}s):")
        print(f"   Statut: {'✅ VALIDE' if result['valid'] else '❌ INVALIDE'}")
        print(f"   Erreurs: {len(result['errors'])}")
        print(f"   Avertissements: {len(result['warnings'])}")
        print(f"   Suggestions: {len(result['suggestions'])}")
        
        # Détails des erreurs
        if result['errors']:
            print("\n❌ ERREURS:")
            for i, error in enumerate(result['errors'], 1):
                print(f"   {i}. {error}")
        
        # Détails des avertissements
        if result['warnings']:
            print("\n⚠️ AVERTISSEMENTS:")
            for i, warning in enumerate(result['warnings'], 1):
                print(f"   {i}. {warning}")
        
        # Suggestions
        if result['suggestions']:
            print("\n💡 SUGGESTIONS:")
            for i, suggestion in enumerate(result['suggestions'], 1):
                print(f"   {i}. {suggestion}")
        
        # Contrôle de doublons
        duplicate_check = result.get('duplicate_check', {})
        if duplicate_check.get('duplicates_found'):
            print("\n🔍 DOUBLONS DÉTECTÉS:")
            for client in duplicate_check['similar_clients']:
                print(f"   - {client['name']} ({client['system']}) - Similarité: {client['similarity']}%")
        
        # Données enrichies
        enriched = result.get('enriched_data', {})
        if enriched:
            print("\n✨ DONNÉES ENRICHIES:")
            for key, value in enriched.items():
                print(f"   - {key}: {value}")
        
        # Statistiques du validateur
        stats = validator.get_stats()
        print("\n📈 STATS VALIDATEUR:")
        print(f"   - Validations totales: {stats['validation_stats']['total_validations']}")
        print(f"   - Réussies: {stats['validation_stats']['successful_validations']}")
        print(f"   - Échouées: {stats['validation_stats']['failed_validations']}")
        print(f"   - Dépendances: fuzzywuzzy={stats['dependencies']['fuzzywuzzy']}, email-validator={stats['dependencies']['email_validator']}")
        
        return result
        
    except Exception as e:
        print(f"💥 EXCEPTION: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {"valid": False, "error": str(e)}

async def test_all_validators():
    """Test de tous les validateurs"""
    print("🚀 TEST COMPLET DU VALIDATEUR CLIENT")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    test_mapping = {
        "france_complet": "FR",
        "usa_complet": "US", 
        "uk_complet": "UK",
        "problematique": "FR",
        "minimal": "FR"
    }
    
    # Tester chaque client
    for test_name, client_data in TEST_CLIENTS.items():
        country = test_mapping[test_name]
        result = await test_validator_single(client_data, country, test_name)
        results[test_name] = {
            "country": country,
            "client_data": client_data,
            "validation_result": result,
            "timestamp": datetime.now().isoformat()
        }
        
        # Pause entre les tests
        await asyncio.sleep(1)
    
    # Résumé global
    print(f"\n{'='*80}")
    print("📈 RÉSUMÉ GLOBAL DES TESTS")
    print(f"{'='*80}")
    
    valid_count = sum(1 for r in results.values() if r["validation_result"].get("valid", False))
    invalid_count = len(results) - valid_count
    
    print(f"Tests réussis (valides): {valid_count}/{len(results)} ✅")
    print(f"Tests échoués (invalides): {invalid_count}/{len(results)} ❌")
    
    # Détail par test
    for test_name, result in results.items():
        status = "✅" if result["validation_result"].get("valid") else "❌"
        errors = len(result["validation_result"].get("errors", []))
        warnings = len(result["validation_result"].get("warnings", []))
        print(f"   {status} {test_name}: {errors} erreurs, {warnings} avertissements")
    
    # Sauvegarder les résultats
    result_file = f"test_validator_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_summary": {
                    "total_tests": len(results),
                    "valid_count": valid_count,
                    "invalid_count": invalid_count,
                    "timestamp": datetime.now().isoformat()
                },
                "test_results": results
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n📁 Résultats sauvegardés: {result_file}")
    except Exception as e:
        print(f"⚠️ Impossible de sauvegarder: {e}")
    
    # Recommandations
    print("\n💡 RECOMMANDATIONS:")
    if valid_count == len(results):
        print("   🎯 Tous les tests de validation fonctionnent correctement")
        print("   → Le validateur est prêt pour l'intégration")
    elif valid_count > 0:
        print("   ⚠️ Certains tests échouent - analyser les erreurs")
        print("   → Vérifier les dépendances et configurations")
    else:
        print("   ❌ Aucun test réussi - problème majeur")
        print("   → Vérifier l'installation des dépendances")

async def test_performance():
    """Test de performance du validateur"""
    print(f"\n{'='*60}")
    print("⚡ TEST DE PERFORMANCE")
    print(f"{'='*60}")
    
    # Test avec le client France complet
    client_data = TEST_CLIENTS["france_complet"]
    validator = ClientValidator()
    
    # Mesure du temps pour plusieurs validations
    times = []
    for i in range(5):
        start_time = datetime.now()
        await validator.validate_complete(client_data, "FR")
        end_time = datetime.now()
        validation_time = (end_time - start_time).total_seconds()
        times.append(validation_time)
        print(f"   Validation {i+1}: {validation_time:.3f}s")
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print("\n📊 STATISTIQUES:")
    print(f"   Temps moyen: {avg_time:.3f}s")
    print(f"   Temps minimum: {min_time:.3f}s")
    print(f"   Temps maximum: {max_time:.3f}s")
    
    if avg_time < 1.0:
        print("   ✅ Performance excellente (< 1s)")
    elif avg_time < 3.0:
        print("   ⚠️ Performance acceptable (< 3s)")
    else:
        print("   ❌ Performance à améliorer (> 3s)")

async def main():
    """Fonction principale"""
    print("🎯 TEST COMPLET DU MODULE DE VALIDATION CLIENT")
    
    # Test de base
    await test_all_validators()
    
    # Test de performance
    await test_performance()
    
    print("\n🏁 TESTS TERMINÉS")
    print("Prochaine étape: Intégrer le validateur dans le workflow de création client")

if __name__ == "__main__":
    asyncio.run(main())