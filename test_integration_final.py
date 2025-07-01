#!/usr/bin/env python3
"""
Test final de l'intégration du workflow de devis dans l'assistant intelligent
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
ASSISTANT_URL = f"{BASE_URL}/api/assistant"

def test_workflow_integration():
    """Test l'intégration complète du workflow"""
    print("[TEST] Integration complete du workflow de devis")
    print("=" * 60)
    
    # Test 1: Chat basique
    print("\n[1] Test du chat basique...")
    try:
        response = requests.post(f"{ASSISTANT_URL}/chat", 
                               json={"message": "Bonjour NOVA"})
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Chat OK: {data.get('response', '')[:100]}...")
        else:
            print(f"[ERREUR] Chat echoue: {response.status_code}")
    except Exception as e:
        print(f"[ERREUR] Erreur chat: {e}")
    
    # Test 2: Workflow de création de devis
    print("\n[2] Test du workflow de creation de devis...")
    try:
        workflow_data = {
            "message": "Je veux créer un devis pour la société TechCorp pour des ordinateurs portables"
        }
        
        response = requests.post(f"{ASSISTANT_URL}/workflow/create_quote", 
                               json=workflow_data)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Workflow OK")
            print(f"   Success: {data.get('success')}")
            print(f"   Message: {data.get('message', '')[:100]}...")
            
            # Afficher les actions rapides
            if data.get('quick_actions'):
                print(f"   Actions rapides: {len(data['quick_actions'])} disponibles")
                for action in data['quick_actions'][:3]:
                    print(f"     - {action.get('label', 'N/A')}")
            
            # Afficher les avertissements
            if data.get('warnings'):
                print(f"   Avertissements: {len(data['warnings'])}")
                for warning in data['warnings'][:2]:
                    print(f"     - {warning}")
            
            # Données du devis
            if data.get('quote_data'):
                quote_data = data['quote_data']
                print(f"   Donnees devis disponibles: {bool(quote_data)}")
                
                # Analyse des doublons
                if quote_data.get('duplicate_analysis'):
                    dup = quote_data['duplicate_analysis']
                    print(f"   Doublons detectes:")
                    print(f"     - Brouillons: {len(dup.get('draft_quotes', []))}")
                    print(f"     - Recents: {len(dup.get('recent_quotes', []))}")
                
                # Aperçu du devis
                if quote_data.get('quote_preview'):
                    preview = quote_data['quote_preview']
                    print(f"   Apercu devis:")
                    if preview.get('client'):
                        print(f"     - Client: {preview['client'].get('name', 'N/A')}")
                    print(f"     - Montant: {preview.get('total_amount', 0)}€")
        else:
            print(f"[ERREUR] Workflow echoue: {response.status_code}")
            print(f"   Reponse: {response.text}")
            
    except Exception as e:
        print(f"[ERREUR] Erreur workflow: {e}")
    
    # Test 3: Interface HTML
    print("\n[3] Test de l'interface...")
    try:
        response = requests.get(f"{ASSISTANT_URL}/interface")
        if response.status_code == 200:
            print(f"[OK] Interface OK: {len(response.text)} caracteres")
        else:
            print(f"[ERREUR] Interface echouee: {response.status_code}")
    except Exception as e:
        print(f"[ERREUR] Erreur interface: {e}")

def test_workflow_scenarios():
    """Test différents scénarios de workflow"""
    print("\n[SCENARIOS] Test des scenarios de workflow")
    print("=" * 40)
    
    scenarios = [
        {
            "name": "Devis simple",
            "message": "Créer un devis pour 10 ordinateurs portables"
        },
        {
            "name": "Devis avec client spécifique",
            "message": "Devis pour la société ABC Corp, 5 imprimantes laser"
        },
        {
            "name": "Devis complexe",
            "message": "Je veux un devis pour TechStart: 20 PC, 5 écrans, installation et formation"
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n[{i}] Scenario: {scenario['name']}")
        try:
            response = requests.post(f"{ASSISTANT_URL}/workflow/create_quote", 
                                   json={"message": scenario['message']})
            
            if response.status_code == 200:
                data = response.json()
                print(f"   [OK] Succes: {data.get('success')}")
                print(f"   Actions: {len(data.get('quick_actions', []))}")
                print(f"   Avertissements: {len(data.get('warnings', []))}")
            else:
                print(f"   [ERREUR] Echec: {response.status_code}")
                
        except Exception as e:
            print(f"   [ERREUR] Erreur: {e}")
        
        time.sleep(1)  # Pause entre les tests

def main():
    """Fonction principale"""
    print("NOVA - Test d'Integration Complete")
    print("=" * 50)
    print(f"Demarre a: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"URL de base: {BASE_URL}")
    
    # Vérifier que le serveur est accessible
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("[OK] Serveur accessible")
        else:
            print(f"[WARN] Serveur repond mais status: {response.status_code}")
    except Exception as e:
        print(f"[ERREUR] Serveur inaccessible: {e}")
        print("[INFO] Assurez-vous que le serveur NOVA est demarre sur le port 8000")
        return
    
    # Exécuter les tests
    test_workflow_integration()
    test_workflow_scenarios()
    
    print(f"\n[FIN] Tests termines a: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 50)

if __name__ == "__main__":
    main()
