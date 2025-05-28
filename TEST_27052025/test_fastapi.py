#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test de démarrage FastAPI avec diagnostic détaillé
"""

import sys
import traceback
import os
from dotenv import load_dotenv

def test_imports():
    """Test tous les imports nécessaires"""
    print("=== TEST DES IMPORTS ===")
    
    imports_to_test = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("sqlalchemy", "SQLAlchemy"),
        ("pydantic", "Pydantic"),
        ("simple_salesforce", "Simple Salesforce"),
        ("httpx", "HTTPX"),
        ("dotenv", "Python-dotenv")
    ]
    
    all_ok = True
    for module, name in imports_to_test:
        try:
            __import__(module)
            print(f"✅ {name} : OK")
        except ImportError as e:
            print(f"❌ {name} : ERREUR - {e}")
            all_ok = False
    
    return all_ok

def test_env_vars():
    """Test des variables d'environnement"""
    print("\n=== TEST VARIABLES D'ENVIRONNEMENT ===")
    
    load_dotenv()
    
    required_vars = [
        "ANTHROPIC_API_KEY",
        "SALESFORCE_USERNAME", 
        "SALESFORCE_PASSWORD",
        "SALESFORCE_SECURITY_TOKEN",
        "SAP_REST_BASE_URL",
        "SAP_USER",
        "SAP_CLIENT_PASSWORD",
        "API_KEY"
    ]
    
    all_ok = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Masquer les valeurs sensibles
            if "KEY" in var or "PASSWORD" in var or "TOKEN" in var:
                display_value = value[:10] + "..." if len(value) > 10 else "***"
            else:
                display_value = value
            print(f"✅ {var} : {display_value}")
        else:
            print(f"❌ {var} : MANQUANT")
            all_ok = False
    
    return all_ok

def test_routes_import():
    """Test de l'import des routes"""
    print("\n=== TEST IMPORT DES ROUTES ===")
    
    routes_to_test = [
        ("routes.routes_claude", "Claude"),
        ("routes.routes_salesforce", "Salesforce"),
        ("routes.routes_sap", "SAP"),
        ("routes.routes_devis", "Devis"),
        ("db.models", "Modèles DB"),
        ("workflow.devis_workflow", "Workflow Devis")
    ]
    
    all_ok = True
    for module, name in routes_to_test:
        try:
            __import__(module)
            print(f"✅ {name} : OK")
        except Exception as e:
            print(f"❌ {name} : ERREUR - {e}")
            all_ok = False
    
    return all_ok

def test_main_app():
    """Test de l'application principale"""
    print("\n=== TEST APPLICATION PRINCIPALE ===")
    
    try:
        # Importer main.py
        import main
        print("✅ Import main.py : OK")
        
        # Vérifier que l'app FastAPI existe
        if hasattr(main, 'app'):
            print("✅ Instance FastAPI : OK")
            
            # Lister les routes
            routes = []
            for route in main.app.routes:
                if hasattr(route, 'path'):
                    routes.append(route.path)
            
            print(f"✅ Routes disponibles ({len(routes)}) :")
            for route in routes[:10]:  # Afficher les 10 premières
                print(f"   - {route}")
            if len(routes) > 10:
                print(f"   ... et {len(routes) - 10} autres")
            
            return True
        else:
            print("❌ Instance FastAPI non trouvée")
            return False
            
    except Exception as e:
        print(f"❌ Erreur application principale : {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

def test_port_availability():
    """Test de la disponibilité du port 8000"""
    print("\n=== TEST DISPONIBILITÉ PORT 8000 ===")
    
    import socket
    
    try:
        # Tenter de se connecter au port 8000
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 8000))
        sock.close()
        
        if result == 0:
            print("⚠️ Port 8000 : OCCUPÉ par un autre processus")
            return False
        else:
            print("✅ Port 8000 : DISPONIBLE")
            return True
            
    except Exception as e:
        print(f"❌ Erreur test port : {e}")
        return False

def main():
    """Fonction principale de diagnostic"""
    print("🚀 DIAGNOSTIC FASTAPI NOVA")
    print("=" * 50)
    
    # Tests séquentiels
    tests = [
        ("Imports", test_imports),
        ("Variables d'environnement", test_env_vars),
        ("Import routes", test_routes_import),
        ("Application principale", test_main_app),
        ("Disponibilité port", test_port_availability)
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n--- {test_name.upper()} ---")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ ERREUR CRITIQUE dans {test_name} : {e}")
            results[test_name] = False
    
    # Résumé
    print("\n" + "=" * 50)
    print("📊 RÉSUMÉ DU DIAGNOSTIC")
    print("=" * 50)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:25} : {status}")
    
    print(f"\nRésultat global : {passed_tests}/{total_tests} tests réussis")
    
    if passed_tests == total_tests:
        print("🎉 Tous les tests sont OK ! FastAPI devrait démarrer.")
        print("\nPour démarrer FastAPI :")
        print("uvicorn main:app --reload --host 0.0.0.0 --port 8000")
    else:
        print("⚠️ Des problèmes ont été détectés. Corrigez-les avant de démarrer FastAPI.")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)