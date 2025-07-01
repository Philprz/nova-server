#!/usr/bin/env python3
"""
Test de l'extraction d'entités améliorée
"""

import requests
import json

def test_entity_extraction():
    """Test des différents types de messages"""
    print("TEST EXTRACTION D'ENTITES")
    print("=" * 40)
    
    test_messages = [
        "faire un devis pour 500 ref A00002 pour le client Edge Communications",
        "Créer un devis pour Edge Communications",
        "edge communication imprimante 40",
        "Nouveau devis 100 A00025 pour Microsoft",
        "devis client Acme Corp produit B00150 quantité 25"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n{i}. Test: '{message}'")
        
        try:
            response = requests.post(
                "http://localhost:8001/api/assistant/chat",
                json={"message": message},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Status: {response.status_code} - OK")
                
                # Afficher les entités extraites si disponibles
                if 'extracted_info' in data.get('response', {}):
                    info = data['response']['extracted_info']
                    print(f"   Clients: {info.get('clients', [])}")
                    print(f"   Produits: {info.get('products', [])}")
                    print(f"   Quantités: {info.get('quantities', [])}")
                else:
                    print("   Pas d'informations extraites")
                    
            else:
                print(f"   Status: {response.status_code} - ERREUR")
                
        except Exception as e:
            print(f"   Erreur: {str(e)}")

if __name__ == "__main__":
    test_entity_extraction()
