#!/usr/bin/env python3
"""
Script pour identifier et corriger l'erreur du workflow
"""

import asyncio
import requests
import json

async def test_workflow_endpoint():
    """Tester directement l'endpoint du workflow"""
    print("🔍 Test direct de l'endpoint workflow")
    print("=" * 50)
    
    # Test 1: Endpoint workflow direct
    try:
        response = requests.post(
            "http://localhost:8000/api/assistant/workflow/create_quote",
            json={"message": "Créer un devis pour Edge Communications avec 5 A00001"},
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Workflow réponse:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Erreur: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {str(e)}")
    
    # Test 2: Vérifier les logs
    print("\n📋 Vérification des logs récents:")
    try:
        with open("logs/workflow_devis.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            errors = [line for line in lines[-50:] if "ERROR" in line]
            if errors:
                print("Dernières erreurs trouvées:")
                for error in errors[-5:]:
                    print(f"  {error.strip()}")
            else:
                print("✅ Aucune erreur récente dans les logs")
    except FileNotFoundError:
        print("⚠️ Fichier de log non trouvé")

if __name__ == "__main__":
    asyncio.run(test_workflow_endpoint())