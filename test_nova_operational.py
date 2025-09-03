#!/usr/bin/env python3
"""
Script de test pour vérifier le bon fonctionnement de NOVA
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:8000"
HEADERS = {"Content-Type": "application/json"}

def test_health():
    """Test de l'endpoint health"""
    print("🔍 Test de l'endpoint /health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Serveur: {data.get('status', 'unknown')}")
            print(f"✅ Système: {data.get('system_status', 'unknown')}")
            if 'startup_tests' in data:
                success_rate = data['startup_tests'].get('success_rate', 0)
                print(f"✅ Tests réussis: {success_rate}%")
            return True
        else:
            print(f"❌ Erreur HTTP: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erreur connexion: {e}")
        return False

def test_interface():
    """Test de l'accès à l'interface"""
    print("\n🔍 Test de l'interface web...")
    interfaces = [
        ("/api/assistant/interface", "Interface principale"),
        ("/interface/itspirit", "Interface IT Spirit")
    ]

    success_count = 0
    for url, name in interfaces:
        try:
            response = requests.get(f"{BASE_URL}{url}")
            if response.status_code == 200:
                print(f"✅ {name} accessible ({url})")
                # Vérifier que le HTML contient les corrections
                html = response.text
                if "case \"task_update\":" in html:
                    print("   ✅ Handler task_update présent")
                if "case \"user_interaction_required\":" in html:
                    print("   ✅ Handler user_interaction_required présent")
                if "addClientSelection" in html:
                    print("   ✅ Fonction addClientSelection présente")
                success_count += 1
            else:
                print(f"❌ {name}: Erreur HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ {name}: Erreur {e}")

    return success_count > 0

def test_chat_endpoint():
    """Test de l'endpoint chat avec sélection client"""
    print("\n🔍 Test de l'endpoint /api/assistant/chat...")
    try:
        # Test d'un message simple
        payload = {
            "message": "Bonjour NOVA",
            "task_id": f"test_{int(time.time())}",
            "context": {}
        }
        response = requests.post(
            f"{BASE_URL}/api/assistant/chat",
            json=payload,
            headers=HEADERS
        )
        if response.status_code == 200:
            data = response.json()
            print("✅ Endpoint chat opérationnel")
            print(f"   Réponse: {data.get('message', '')[:100]}...")
            return True
        else:
            print(f"❌ Erreur HTTP: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def main():
    """Exécution des tests"""
    print("=" * 50)
    print("🚀 TEST DE VÉRIFICATION NOVA")
    print("=" * 50)
    
    tests = [
        ("Health Check", test_health),
        ("Interface Web", test_interface),
        ("Chat Endpoint", test_chat_endpoint)
    ]
    
    results = []
    for name, test_func in tests:
        results.append((name, test_func()))
    
    print("\n" + "=" * 50)
    print("📊 RÉSUMÉ DES TESTS")
    print("=" * 50)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    for name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print(f"\nTaux de réussite: {success_count}/{total_count} ({success_count/total_count*100:.0f}%)")
    
    if success_count == total_count:
        print("\n🎉 TOUS LES TESTS SONT RÉUSSIS! NOVA EST OPÉRATIONNEL!")
    else:
        print("\n⚠️ Certains tests ont échoué. Vérifiez les logs.")

if __name__ == "__main__":
    main()