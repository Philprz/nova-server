#!/usr/bin/env python3
"""
Test complet de l'interface assistant intelligent NOVA
"""

import requests
import json
import time

def test_chat_workflow():
    """Test du workflow de chat complet"""
    print("=== TEST WORKFLOW CHAT COMPLET ===")
    
    # 1. Test du chat principal
    print("\n1. Test Chat Principal")
    chat_url = "http://localhost:8001/api/assistant/chat"
    
    messages = [
        "Bonjour NOVA",
        "Je veux créer un devis",
        "Recherche client Dupont",
        "Montre-moi les produits disponibles"
    ]
    
    for msg in messages:
        print(f"\nEnvoi: {msg}")
        try:
            response = requests.post(
                chat_url,
                json={"message": msg},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Réponse reçue (Status: {response.status_code})")
                # Éviter l'affichage des emojis qui causent des erreurs d'encodage
                print("✅ Chat fonctionnel")
            else:
                print(f"❌ Erreur chat: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Erreur: {str(e)}")
        
        time.sleep(1)  # Pause entre les messages

def test_actions_rapides():
    """Test des APIs des actions rapides"""
    print("\n\n=== TEST ACTIONS RAPIDES ===")
    
    # Test clients
    print("\n2. Test API Clients")
    try:
        response = requests.get("http://localhost:8001/clients/search_clients_advanced?limit=5", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Clients OK - {len(data.get('clients', []))} clients trouvés")
        else:
            print(f"❌ API Clients erreur: {response.status_code}")
    except Exception as e:
        print(f"❌ Erreur clients: {str(e)}")
    
    # Test produits
    print("\n3. Test API Produits")
    try:
        response = requests.get("http://localhost:8001/products/search_products_advanced?limit=5", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Produits OK - {len(data.get('products', []))} produits trouvés")
        else:
            print(f"❌ API Produits erreur: {response.status_code}")
    except Exception as e:
        print(f"❌ Erreur produits: {str(e)}")

def test_historique():
    """Test de l'historique"""
    print("\n\n=== TEST HISTORIQUE ===")
    
    try:
        response = requests.get("http://localhost:8001/api/assistant/conversation/history", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Historique OK - {len(data.get('history', []))} éléments")
        else:
            print(f"❌ API Historique erreur: {response.status_code}")
    except Exception as e:
        print(f"❌ Erreur historique: {str(e)}")

def test_interface_html():
    """Test de l'interface HTML"""
    print("\n\n=== TEST INTERFACE HTML ===")
    
    try:
        response = requests.get("http://localhost:8001/api/assistant/interface", timeout=10)
        if response.status_code == 200:
            print("✅ Interface HTML accessible")
            print(f"   Taille: {len(response.text)} caractères")
        else:
            print(f"❌ Interface HTML erreur: {response.status_code}")
    except Exception as e:
        print(f"❌ Erreur interface: {str(e)}")

if __name__ == "__main__":
    print("🚀 TEST COMPLET ASSISTANT INTELLIGENT NOVA")
    print("🌐 Serveur: http://localhost:8001")
    print("=" * 60)
    
    # Tests séquentiels
    test_interface_html()
    test_actions_rapides()
    test_historique()
    test_chat_workflow()
    
    print("\n" + "=" * 60)
    print("🏁 TESTS TERMINÉS")
    print("\n💡 Pour tester l'interface complète:")
    print("   👉 Ouvrez: http://localhost:8001/api/assistant/interface")
    print("   👉 Cliquez sur les boutons 'Actions Rapides'")
    print("   👉 Testez le chat interactif")
