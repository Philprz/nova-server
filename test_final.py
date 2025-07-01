#!/usr/bin/env python3
"""
Test final de l'assistant intelligent NOVA
"""

import requests
import json

def test_all_apis():
    """Test de toutes les APIs"""
    print("TEST COMPLET ASSISTANT INTELLIGENT NOVA")
    print("Serveur: http://localhost:8001")
    print("=" * 50)
    
    tests = [
        {
            "name": "Interface HTML",
            "url": "http://localhost:8001/api/assistant/interface",
            "method": "GET"
        },
        {
            "name": "Chat API",
            "url": "http://localhost:8001/api/assistant/chat",
            "method": "POST",
            "data": {"message": "Bonjour NOVA"}
        },
        {
            "name": "Historique",
            "url": "http://localhost:8001/api/assistant/conversation/history",
            "method": "GET"
        },
        {
            "name": "API Clients",
            "url": "http://localhost:8001/clients/search_clients_advanced?limit=5",
            "method": "GET"
        },
        {
            "name": "API Produits",
            "url": "http://localhost:8001/products/search_products_advanced?limit=5",
            "method": "GET"
        }
    ]
    
    results = []
    
    for test in tests:
        print(f"\nTest: {test['name']}")
        try:
            if test['method'] == 'POST':
                response = requests.post(
                    test['url'], 
                    json=test.get('data', {}),
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
            else:
                response = requests.get(test['url'], timeout=10)
            
            if response.status_code == 200:
                print(f"  Status: {response.status_code} - OK")
                results.append(f"✓ {test['name']}")
            else:
                print(f"  Status: {response.status_code} - ERREUR")
                results.append(f"✗ {test['name']}")
                
        except Exception as e:
            print(f"  Erreur: {str(e)}")
            results.append(f"✗ {test['name']}")
    
    print("\n" + "=" * 50)
    print("RESULTATS FINAUX:")
    for result in results:
        print(f"  {result}")
    
    print(f"\nSUCCES: {len([r for r in results if r.startswith('✓')])}/{len(results)}")
    
    print("\nPour tester l'interface complete:")
    print("  1. Ouvrez: http://localhost:8001/api/assistant/interface")
    print("  2. Cliquez sur 'Rechercher Client' ou 'Produits'")
    print("  3. Testez le chat avec des messages")

if __name__ == "__main__":
    test_all_apis()
