#!/usr/bin/env python3
"""
Debug des regex d'extraction
"""

import re

def test_regex_patterns():
    """Test des patterns regex"""
    
    test_message = "faire un devis pour 500 ref A00002 pour le client Edge Communications"
    print(f"Message test: '{test_message}'")
    print("=" * 60)
    
    # Test extraction produits
    print("\n1. EXTRACTION PRODUITS:")
    product_refs = re.findall(r'\b[A-Z]\d{5}\b', test_message)
    print(f"   Produits trouvés: {product_refs}")
    
    # Test extraction quantités
    print("\n2. EXTRACTION QUANTITES:")
    
    # Pattern 1: avec unités
    qty_with_units = re.findall(r'\b(\d+)\s*(?:pièces?|unités?|pc|u)\b', test_message, re.IGNORECASE)
    print(f"   Avec unités: {qty_with_units}")
    
    # Pattern 2: patterns spécifiques
    qty_patterns = [
        (r'\b(\d+)\s+ref\b', "500 ref"),
        (r'\bquantité\s+(\d+)\b', "quantité 25"),
        (r'\b(\d+)\s+[A-Z]\d{5}\b', "100 A00025"),
    ]
    
    for pattern, desc in qty_patterns:
        matches = re.findall(pattern, test_message, re.IGNORECASE)
        print(f"   {desc}: {matches}")
    
    # Pattern 3: nombres isolés
    isolated_numbers = re.findall(r'\b(\d{1,4})\b', test_message)
    print(f"   Nombres isolés: {isolated_numbers}")
    
    # Test extraction clients
    print("\n3. EXTRACTION CLIENTS:")
    
    # Pattern 1: explicites
    explicit_patterns = [
        (r'(?:client|pour le client|société|entreprise)\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\.|\n)', "client X"),
        (r'\bpour\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', "pour X"),
    ]
    
    for pattern, desc in explicit_patterns:
        matches = re.findall(pattern, test_message)
        print(f"   {desc}: {matches}")
    
    # Pattern 2: noms composés
    compound_names = re.findall(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b', test_message)
    print(f"   Noms composés: {compound_names}")

def test_all_messages():
    """Test sur tous les messages"""
    
    messages = [
        "faire un devis pour 500 ref A00002 pour le client Edge Communications",
        "Créer un devis pour Edge Communications", 
        "Nouveau devis 100 A00025 pour Microsoft",
        "devis client Acme Corp produit B00150 quantité 25"
    ]
    
    print("\n" + "=" * 60)
    print("TEST SUR TOUS LES MESSAGES")
    print("=" * 60)
    
    for i, msg in enumerate(messages, 1):
        print(f"\n{i}. '{msg}'")
        
        # Produits
        products = re.findall(r'\b[A-Z]\d{5}\b', msg)
        print(f"   Produits: {products}")
        
        # Quantités - pattern "500 ref"
        qty_ref = re.findall(r'\b(\d+)\s+ref\b', msg, re.IGNORECASE)
        print(f"   Quantité (ref): {qty_ref}")
        
        # Quantités - pattern "100 A00025"
        qty_prod = re.findall(r'\b(\d+)\s+[A-Z]\d{5}\b', msg)
        print(f"   Quantité (prod): {qty_prod}")
        
        # Quantités - pattern "quantité 25"
        qty_explicit = re.findall(r'\bquantité\s+(\d+)\b', msg, re.IGNORECASE)
        print(f"   Quantité (explicit): {qty_explicit}")
        
        # Clients - pattern "pour Edge Communications"
        client_pour = re.findall(r'\bpour\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', msg)
        print(f"   Client (pour): {client_pour}")
        
        # Clients - pattern "client X"
        client_explicit = re.findall(r'(?:client|pour le client)\s+([A-Z][a-zA-Z\s]+?)(?:\s|$|,|\.)', msg)
        print(f"   Client (explicit): {client_explicit}")

if __name__ == "__main__":
    test_regex_patterns()
    test_all_messages()
