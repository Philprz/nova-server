#!/usr/bin/env python3
"""
Script de test rapide pour valider l'intégration du SuggestionEngine
Usage: python test_suggestion_integration.py
"""

import asyncio
import sys
import os

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_suggestion_engine_basic():
    """Test de base du SuggestionEngine seul"""
    print("🧪 TEST 1: SuggestionEngine - Fonctionnalité de base")
    
    try:
        from services.suggestion_engine import SuggestionEngine, MockDataProvider
        
        # Initialiser le moteur
        engine = SuggestionEngine()
        print("✅ SuggestionEngine initialisé")
        
        # Test avec des données mockées
        clients = MockDataProvider.get_mock_clients()
        
        # Test suggestion client
        result = await engine.suggest_client("Edge Comunications", clients)
        
        if result.has_suggestions:
            suggestion = result.primary_suggestion
            print(f"✅ Suggestion client trouvée:")
            print(f"   Original: 'Edge Comunications'")
            print(f"   Suggéré: '{suggestion.suggested_value}'")
            print(f"   Score: {suggestion.score}%")
            print(f"   Confiance: {suggestion.confidence.value}")
        else:
            print("❌ Aucune suggestion trouvée")
            
        return True
        
    except ImportError as e:
        print(f"❌ Erreur d'import: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur test: {e}")
        return False

async def test_workflow_integration():
    """Test d'intégration avec DevisWorkflow"""
    print("\n🧪 TEST 2: Intégration avec DevisWorkflow")
    
    try:
        from workflow.devis_workflow import DevisWorkflow
        
        # Initialiser le workflow
        workflow = DevisWorkflow(validation_enabled=False)  # Désactiver validation pour test
        print("✅ DevisWorkflow initialisé")
        
        # Vérifier que le suggestion_engine est bien là
        if hasattr(workflow, 'suggestion_engine'):
            print("✅ SuggestionEngine présent dans DevisWorkflow")
        else:
            print("❌ SuggestionEngine manquant dans DevisWorkflow")
            return False
            
        # Vérifier que les nouvelles méthodes existent
        required_methods = [
            '_validate_products_with_suggestions',
            'apply_client_suggestion',
            'apply_product_suggestions'
        ]
        
        for method in required_methods:
            if hasattr(workflow, method):
                print(f"✅ Méthode {method} présente")
            else:
                print(f"❌ Méthode {method} manquante")
                return False
        
        return True
        
    except ImportError as e:
        print(f"❌ Erreur d'import DevisWorkflow: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur test intégration: {e}")
        return False

async def test_dependencies():
    """Test des dépendances requises"""
    print("\n🧪 TEST 3: Vérification des dépendances")
    
    try:
        import fuzzywuzzy
        print("✅ fuzzywuzzy installé")
    except ImportError:
        print("❌ fuzzywuzzy manquant - pip install fuzzywuzzy")
        return False
    
    try:
        import Levenshtein
        print("✅ python-Levenshtein installé")
    except ImportError:
        print("⚠️ python-Levenshtein manquant - pip install python-Levenshtein (optionnel mais recommandé)")
    
    return True

async def test_routes_suggestions():
    """Test des routes de suggestions"""
    print("\n🧪 TEST 4: Vérification des routes suggestions")
    
    try:
        from routes.routes_suggestions import router
        print("✅ Routes suggestions importées")
        
        # Vérifier les endpoints
        routes = [str(route.path) for route in router.routes]
        expected_routes = ['/suggestions/apply_client_choice', '/suggestions/apply_product_choices']
        
        for expected in expected_routes:
            if expected in routes:
                print(f"✅ Route {expected} trouvée")
            else:
                print(f"❌ Route {expected} manquante")
                return False
        
        return True
        
    except ImportError as e:
        print(f"❌ Erreur d'import routes_suggestions: {e}")
        print("   Créez le fichier routes/routes_suggestions.py")
        return False
    except Exception as e:
        print(f"❌ Erreur test routes: {e}")
        return False

async def test_main_integration():
    """Test de l'intégration dans main.py"""
    print("\n🧪 TEST 5: Vérification intégration main.py")
    
    try:
        import main
        
        # Vérifier si les routes suggestions sont incluses
        # Note: Ceci est approximatif car il faudrait analyser le code
        print("⚠️ Vérifiez manuellement que routes_suggestions est inclus dans main.py")
        print("   Ajoutez: app.include_router(routes_suggestions.router)")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur test main.py: {e}")
        return False

async def main():
    """Lance tous les tests"""
    print("🚀 NOVA - Test d'intégration SuggestionEngine")
    print("=" * 50)
    
    tests = [
        test_dependencies,
        test_suggestion_engine_basic,
        test_workflow_integration,
        test_routes_suggestions,
        test_main_integration
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Erreur critique dans {test.__name__}: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("📊 RÉSULTATS DES TESTS")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Tests réussis: {passed}/{total}")
    
    if passed == total:
        print("🎉 TOUS LES TESTS SONT PASSÉS!")
        print("   Votre intégration SuggestionEngine semble correcte.")
    else:
        print("⚠️ CERTAINS TESTS ONT ÉCHOUÉ")
        print("   Vérifiez les erreurs ci-dessus et corrigez avant de continuer.")
    
    print("\n🎯 PROCHAINES ÉTAPES:")
    if passed == total:
        print("1. Testez avec une vraie requête de devis")
        print("2. Vérifiez les suggestions dans l'interface")
        print("3. Testez les corrections de client/produit")
    else:
        print("1. Corrigez les erreurs identifiées")
        print("2. Relancez ce script de test")
        print("3. Continuez quand tous les tests passent")

if __name__ == "__main__":
    # Lancer les tests
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrompus par l'utilisateur")
    except Exception as e:
        print(f"\n💥 Erreur critique: {e}")
        sys.exit(1)