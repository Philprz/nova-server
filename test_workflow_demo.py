#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de démonstration du workflow de devis intégré
"""

import requests
import json
import sys

def test_workflow_demo():
    """Test de démonstration du workflow"""
    print("=== DEMO WORKFLOW DE DEVIS NOVA ===")
    print()
    
    base_url = "http://localhost:8000"
    
    # Test 1: Workflow simple
    print("1. Test workflow simple...")
    try:
        response = requests.post(f"{base_url}/api/assistant/workflow/create_quote", 
                               json={"message": "Devis pour Edge Communications: 100 A00025"})
        
        if response.status_code == 200:
            data = response.json()
            print(f"   [OK] Succes: {data.get('success')}")
            print(f"   [MSG] Message: {data.get('message', 'Aucun message')[:100]}...")
            print(f"   [ACT] Actions rapides: {len(data.get('quick_actions', []))}")
            
            # Afficher les actions rapides
            for i, action in enumerate(data.get('quick_actions', [])[:3]):
                print(f"      {i+1}. {action.get('label', 'Action')}")
                
        else:
            print(f"   [ERR] Erreur HTTP: {response.status_code}")
            
    except Exception as e:
        print(f"   [ERR] Erreur: {str(e)}")
    
    print()
    
    # Test 2: Interface accessible
    print("2. Test interface...")
    try:
        response = requests.get(f"{base_url}/api/assistant/interface")
        if response.status_code == 200:
            print(f"   [OK] Interface accessible ({len(response.text)} caracteres)")
        else:
            print(f"   [ERR] Interface inaccessible: {response.status_code}")
    except Exception as e:
        print(f"   [ERR] Erreur interface: {str(e)}")
    
    print()
    print("=== FIN DEMO ===")
    print()
    print("[WEB] Interface disponible sur: http://localhost:8000/api/assistant/interface")
    print("[DOC] Documentation API: http://localhost:8000/docs")

if __name__ == "__main__":
    test_workflow_demo()
