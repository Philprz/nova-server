#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test d'intégration du workflow de devis avec l'assistant intelligent
================================================================

Ce script teste l'intégration entre l'assistant intelligent et le workflow
de devis existant pour s'assurer que tout fonctionne correctement.
"""

import requests
import json
import sys
import time

# Configuration
BASE_URL = "http://localhost:8001"
ASSISTANT_URL = f"{BASE_URL}/api/assistant"

def test_chat_endpoint():
    """Test de l'endpoint de chat principal"""
    print("[TEST] Test de l'endpoint de chat...")
    
    url = f"{ASSISTANT_URL}/chat"
    data = {"message": "Créer un devis pour Edge Communications avec 10 unités de A00025"}
    
    try:
        response = requests.post(url, json=data, timeout=10)
        result = response.json()
        
        print(f"[STATUS] Status: {response.status_code}")
        print(f"[SUCCES] Succès: {result.get('success', False)}")
        
        if result.get('success'):
            print(f"[REPONSE] Réponse: {result['response']['message'][:200]}...")
            print(f"[TYPE] Type: {result['response'].get('type', 'N/A')}")
            
            # Vérifier les actions rapides
            quick_actions = result['response'].get('quick_actions', [])
            if quick_actions:
                print(f"[ACTIONS] Actions rapides disponibles: {len(quick_actions)}")
                for action in quick_actions:
                    print(f"   - {action.get('label', 'N/A')}: {action.get('action', 'N/A')}")
        else:
            print(f"[ERREUR] Erreur: {result.get('error', 'Inconnue')}")
            
    except Exception as e:
        print(f"[ERREUR] Erreur de test: {e}")
    
    print("-" * 50)

def test_workflow_endpoint():
    """Test de l'endpoint du workflow de devis"""
    print("[TEST] Test de l'endpoint workflow...")
    
    url = f"{ASSISTANT_URL}/workflow/create_quote"
    data = {"message": "Créer un devis pour Edge Communications avec 5 unités de A00025"}
    
    try:
        response = requests.post(url, json=data, timeout=15)
        result = response.json()
        
        print(f"[STATUS] Status: {response.status_code}")
        print(f"[SUCCES] Succès: {result.get('success', False)}")
        
        if result.get('success'):
            print(f"[MESSAGE] Message: {result.get('message', 'N/A')}")
            print(f"[STATUS WORKFLOW] Status workflow: {result.get('workflow_status', 'N/A')}")
            print(f"[ACTION SUIVANTE] Action suivante: {result.get('next_action', 'N/A')}")
        else:
            print(f"[ERREUR] Erreur: {result.get('detail', 'Inconnue')}")
            
    except Exception as e:
        print(f"[ERREUR] Erreur de test: {e}")
    
    print("-" * 50)

def test_conversation_flow():
    """Test du flux de conversation complet"""
    print("[TEST] Test du flux de conversation...")
    
    messages = [
        "Bonjour NOVA",
        "Je veux créer un devis",
        "Pour Edge Communications",
        "Avec 10 unités de A00025"
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\n[MSG {i}] Message {i}: {message}")
        
        url = f"{ASSISTANT_URL}/chat"
        data = {"message": message}
        
        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            
            if result.get('success'):
                response_msg = result['response']['message']
                print(f"[REPONSE] Réponse: {response_msg[:150]}...")
                
                # Vérifier l'intention détectée
                intent = result.get('intent', {})
                if intent:
                    print(f"[INTENTION] Intention: {intent.get('primary_intent', 'N/A')}")
            else:
                print(f"[ERREUR] Erreur: {result.get('error', 'Inconnue')}")
                
        except Exception as e:
            print(f"[ERREUR] Erreur: {e}")
        
        time.sleep(1)  # Pause entre les messages
    
    print("-" * 50)

def test_suggestions():
    """Test des suggestions contextuelles"""
    print("[TEST] Test des suggestions...")
    
    for suggestion_type in ['clients', 'products']:
        print(f"\n[SUGGESTIONS] Test suggestions {suggestion_type}...")
        
        url = f"{ASSISTANT_URL}/suggestions/{suggestion_type}"
        
        try:
            response = requests.get(url, timeout=10)
            result = response.json()
            
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Succès: {result.get('success', False)}")
            
            if result.get('success'):
                suggestions = result.get('suggestions', [])
                print(f"[RESULTATS] Suggestions trouvées: {len(suggestions)}")
                
                # Afficher les 3 premières
                for i, suggestion in enumerate(suggestions[:3], 1):
                    name = suggestion.get('Name') or suggestion.get('company_name') or suggestion.get('name', 'N/A')
                    print(f"   {i}. {name}")
            else:
                print(f"❌ Erreur: {result.get('detail', 'Inconnue')}")
                
        except Exception as e:
            print(f"❌ Erreur: {e}")
    
    print("-" * 50)

def main():
    """Fonction principale de test"""
    print("NOVA - Test d'intégration Workflow + Assistant")
    print("=" * 60)
    
    # Vérifier que le serveur est accessible
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"[OK] Serveur accessible (Status: {response.status_code})")
    except:
        print("[ERREUR] Serveur non accessible. Démarrez NOVA avec start_nova.ps1")
        return
    
    print("-" * 50)
    
    # Exécuter les tests
    test_chat_endpoint()
    test_workflow_endpoint()
    test_conversation_flow()
    test_suggestions()
    
    print("[TERMINE] Tests terminés !")
    print("\n[INFO] Pour tester l'interface complète:")
    print(f"   URL: {BASE_URL}/api/assistant/interface")

if __name__ == "__main__":
    main()
