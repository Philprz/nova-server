#!/usr/bin/env python3
"""
Script de test pour l'assistant intelligent NOVA
"""

import requests
import json

def test_chat_api():
    """Test de l'API de chat"""
    url = "http://localhost:8001/api/assistant/chat"
    
    test_messages = [
        "Bonjour NOVA, peux-tu m'aider ?",
        "Je veux créer un devis pour un client",
        "Recherche client Dupont",
        "Merci pour ton aide"
    ]
    
    print("Test de l'API Chat NOVA")
    print("=" * 50)
    
    for i, message in enumerate(test_messages, 1):
        print(f"\nTest {i}: {message}")
        
        try:
            response = requests.post(
                url,
                json={"message": message},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"Succès - Status: {response.status_code}")
                print(f"Réponse NOVA: {data.get('response', {}).get('message', 'Pas de message')}")
                if data.get('intent'):
                    print(f"Intention détectée: {data['intent'].get('intent', 'Inconnue')}")
            else:
                print(f"Erreur - Status: {response.status_code}")
                print(f"Réponse: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"Erreur de connexion: {e}")
        except Exception as e:
            print(f"Erreur: {e}")

def test_suggestions_api():
    """Test de l'API de suggestions"""
    print("\n\n🧪 Test de l'API Suggestions")
    print("=" * 50)
    
    for suggestion_type in ['clients', 'products']:
        url = f"http://localhost:8001/api/assistant/suggestions/{suggestion_type}"
        print(f"\n📤 Test suggestions {suggestion_type}")
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Succès - Status: {response.status_code}")
                suggestions = data.get('suggestions', [])
                print(f"📥 Nombre de suggestions: {len(suggestions)}")
            else:
                print(f"❌ Erreur - Status: {response.status_code}")
                print(f"📥 Réponse: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur de connexion: {e}")
        except Exception as e:
            print(f"❌ Erreur: {e}")

def test_conversation_history():
    """Test de l'historique de conversation"""
    print("\n\n🧪 Test Historique de Conversation")
    print("=" * 50)
    
    url = "http://localhost:8001/api/assistant/conversation/history"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Succès - Status: {response.status_code}")
            history = data.get('history', [])
            print(f"📥 Éléments dans l'historique: {len(history)}")
        else:
            print(f"❌ Erreur - Status: {response.status_code}")
            print(f"📥 Réponse: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion: {e}")
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    print("🚀 Démarrage des tests NOVA Assistant Intelligent")
    print("🌐 Serveur: http://localhost:8001")
    
    # Tests des différentes APIs
    test_chat_api()
    test_suggestions_api()
    test_conversation_history()
    
    print("\n\n🏁 Tests terminés !")
