#!/usr/bin/env python3
"""
Script de test simple pour l'assistant intelligent NOVA
"""

import requests
import json

def test_chat():
    """Test simple de l'API de chat"""
    url = "http://localhost:8001/api/assistant/chat"
    message = "Bonjour NOVA, peux-tu m'aider ?"
    
    print("Test API Chat NOVA")
    print("Message:", message)
    
    try:
        response = requests.post(
            url,
            json={"message": message},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print("Status Code:", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            print("Succes!")
            print("Reponse:", json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("Erreur!")
            print("Reponse:", response.text)
            
    except Exception as e:
        print("Erreur:", str(e))

def test_history():
    """Test de l'historique"""
    url = "http://localhost:8001/api/assistant/conversation/history"
    
    print("\nTest Historique")
    
    try:
        response = requests.get(url, timeout=10)
        print("Status Code:", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            print("Succes!")
            print("Historique:", json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("Erreur!")
            print("Reponse:", response.text)
            
    except Exception as e:
        print("Erreur:", str(e))

if __name__ == "__main__":
    print("Demarrage des tests NOVA")
    test_chat()
    test_history()
    print("Tests termines!")
