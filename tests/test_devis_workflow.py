# tests/test_devis_workflow.py

import asyncio
import json
from workflow.devis_workflow import DevisWorkflow

async def test_devis_workflow():
    """Test du workflow de devis"""
    test_cases = [
        {
            "name": "Test basique",
            "prompt": "faire un devis sur la fourniture de 500 ref 2021025 pour le client SAFRAN"
        },
        {
            "name": "Test avec quantités multiples",
            "prompt": "devis pour THALES incluant 50 ref SERV2025, 100 cartouches XYZ001 et 10 packs maintenance"
        },
        {
            "name": "Test avec client inconnu",
            "prompt": "devis pour 10 ordinateurs portables pour le client INEXISTANT"
        },
        {
            "name": "Test avec produit indisponible",
            "prompt": "créer un devis pour 2000 unités de la référence XYZ789 pour le client AIRBUS"
        }
    ]
    
    workflow = DevisWorkflow()
    
    for test_case in test_cases:
        print(f"\n=== Test: {test_case['name']} ===")
        print(f"Prompt: {test_case['prompt']}")
        
        result = await workflow.process_prompt(test_case["prompt"])
        
        print(f"Résultat: {json.dumps(result, indent=2)}")
        
        if result.get("status") == "error":
            print(f"Erreur: {result.get('message')}")
        else:
            print(f"Devis {result.get('quote_id')} généré avec succès")
            print(f"Client: {result.get('client', {}).get('name')}")
            print(f"Montant total: {result.get('total_amount')} {result.get('currency')}")
            print(f"Produits: {len(result.get('products', []))}")
            
            if not result.get("all_products_available", True):
                print("Attention: Certains produits sont indisponibles!")
                print(f"Produits indisponibles: {len(result.get('unavailable_products', []))}")
                print(f"Alternatives proposées: {len(result.get('alternatives', {}))}")
        
        print("=== Fin du test ===")

if __name__ == "__main__":
    asyncio.run(test_devis_workflow())