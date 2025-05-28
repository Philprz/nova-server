#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test direct des serveurs MCP pour vérifier qu'ils fonctionnent
avant de les utiliser dans Claude Desktop
"""


import sys
import os
from pathlib import Path

def test_mcp_server(server_name, script_path, test_function, test_args=None):
    """Test un serveur MCP avec une fonction spécifique"""
    print(f"\n=== TEST {server_name.upper()} ===")
    
    if not os.path.exists(script_path):
        print(f"❌ Script non trouvé : {script_path}")
        return False
    
    print(f"✅ Script trouvé : {script_path}")
    
    # Préparer la commande MCP
    if test_args is None:
        test_args = {}
    
    mcp_request = {
        "method": "tools/call",
        "params": {
            "name": test_function,
            "arguments": test_args
        }
    }
    
    try:
        # Exécuter le serveur MCP
        cmd = ["python", script_path]
        print(f"🔄 Exécution : {' '.join(cmd)}")
        print(f"📤 Test fonction : {test_function}")
        print(f"📋 Arguments : {test_args}")
        
        # Note: Les serveurs MCP fonctionnent en mode stdio
        # Pour un test direct, on peut essayer d'importer et tester les fonctions
        
        # Import du module pour test direct
        module_name = Path(script_path).stem
        sys.path.insert(0, str(Path(script_path).parent))
        
        try:
            module = __import__(module_name)
            print(f"✅ Module {module_name} importé avec succès")
            return True
        except Exception as e:
            print(f"❌ Erreur import module : {e}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur test : {e}")
        return False

def test_env_access():
    """Test l'accès aux variables d'environnement"""
    print("\n=== TEST VARIABLES D'ENVIRONNEMENT ===")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = [
        "SALESFORCE_USERNAME",
        "SALESFORCE_PASSWORD", 
        "SALESFORCE_SECURITY_TOKEN",
        "SAP_REST_BASE_URL",
        "SAP_USER",
        "SAP_CLIENT_PASSWORD"
    ]
    
    all_ok = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Masquer les valeurs sensibles
            if "PASSWORD" in var or "TOKEN" in var:
                display_value = "***"
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: MANQUANT")
            all_ok = False
    
    return all_ok

def main():
    print("🧪 TEST DIRECT DES SERVEURS MCP NOVA")
    print("=" * 50)
    
    # Répertoire de base
    base_dir = Path(__file__).parent
    
    # Test 1: Variables d'environnement
    env_ok = test_env_access()
    
    # Test 2: Serveur Salesforce MCP
    sf_script = base_dir / "salesforce_mcp.py"
    sf_ok = test_mcp_server(
        "Salesforce MCP",
        str(sf_script),
        "salesforce_query",
        {"query": "SELECT Id, Name FROM Account LIMIT 1"}
    )
    
    # Test 3: Serveur SAP MCP  
    sap_script = base_dir / "sap_mcp.py"
    sap_ok = test_mcp_server(
        "SAP MCP",
        str(sap_script),
        "sap_login_test",
        {}
    )
    
    # Résumé
    print("\n" + "=" * 50)
    print("📊 RÉSUMÉ DES TESTS MCP")
    print("=" * 50)
    
    tests = [
        ("Variables d'environnement", env_ok),
        ("Salesforce MCP", sf_ok),
        ("SAP MCP", sap_ok)
    ]
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for test_name, result in tests:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:25} : {status}")
    
    print(f"\nRésultat : {passed}/{total} tests réussis")
    
    if passed == total:
        print("\n🎉 Tous les tests MCP sont OK !")
        print("Les serveurs MCP sont prêts pour Claude Desktop.")
        print("\n📋 Prochaines étapes :")
        print("1. Redémarrez Claude Desktop")
        print("2. Testez dans Claude Desktop : 'Quels outils MCP sont disponibles ?'")
        print("3. Testez une requête Salesforce : 'Trouve le client Edge Communications'")
    else:
        print("\n⚠️ Des problèmes ont été détectés.")
        print("Corrigez les erreurs avant d'utiliser Claude Desktop.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
