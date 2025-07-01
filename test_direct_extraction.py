#!/usr/bin/env python3
"""
Test direct de l'extraction d'entités
"""

# Importer la classe ConversationManager directement
import sys
import os
sys.path.append(os.path.dirname(__file__))

from routes.routes_intelligent_assistant import ConversationManager

def test_direct_extraction():
    """Test direct de l'extraction"""
    
    # Créer une instance du manager
    manager = ConversationManager()
    
    test_messages = [
        "faire un devis pour 500 ref A00002 pour le client Edge Communications",
        "Créer un devis pour Edge Communications",
        "Nouveau devis 100 A00025 pour Microsoft",
        "devis client Acme Corp produit B00150 quantité 25"
    ]
    
    print("TEST DIRECT EXTRACTION D'ENTITES")
    print("=" * 50)
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n{i}. Message: '{message}'")
        
        # Analyser l'intention
        intent = manager.analyze_intent(message)
        
        print(f"   Intention: {intent['primary_intent']}")
        print(f"   Entités: {intent['entities']}")
        
        entities = intent['entities']
        print(f"   - Clients: {entities.get('client_names', [])}")
        print(f"   - Produits: {entities.get('product_refs', [])}")
        print(f"   - Quantités: {entities.get('quantities', [])}")

if __name__ == "__main__":
    test_direct_extraction()
