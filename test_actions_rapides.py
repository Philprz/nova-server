#!/usr/bin/env python3
"""
Test des nouvelles actions rapides de l'assistant intelligent NOVA
"""

import requests
import json

def test_clients_api():
    """Test de l'API de recherche de clients"""
    url = "http://localhost:8001/clients/search_clients_advanced"
    params = {"q": "", "limit": 20}
    
    print("Test API Clients")
    print("URL:", url)
    print("Params:", params)
    
    try:
        response = requests.get(url, params=params, timeout=15)
        print("Status Code:", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            print("Succes!")
            print("Clients trouves:", len(data.get('clients', [])))
            print("Total:", data.get('total_found', 0))
            
            # Afficher quelques clients
            clients = data.get('clients', [])[:3]
            for i, client in enumerate(clients, 1):
                print(f"  {i}. {client.get('Name', 'Sans nom')}")
                if client.get('Industry'):
                    print(f"     Secteur: {client['Industry']}")
        else:
            print("Erreur!")
            print("Reponse:", response.text[:200])
            
    except Exception as e:
        print("Erreur:", str(e))

def test_products_api():
    """Test de l'API de recherche de produits"""
    url = "http://localhost:8001/products/search_products_advanced"
    params = {"limit": 20}
    
    print("\nTest API Produits")
    print("URL:", url)
    print("Params:", params)
    
    try:
        response = requests.get(url, params=params, timeout=15)
        print("Status Code:", response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            print("Succes!")
            print("Produits trouves:", len(data.get('products', [])))
            print("Total:", data.get('total_found', 0))
            
            # Afficher quelques produits
            products = data.get('products', [])[:3]
            for i, product in enumerate(products, 1):
                print(f"  {i}. {product.get('ItemName', 'Sans nom')}")
                if product.get('ItemCode'):
                    print(f"     Ref: {product['ItemCode']}")
        else:
            print("Erreur!")
            print("Reponse:", response.text[:200])
            
    except Exception as e:
        print("Erreur:", str(e))

if __name__ == "__main__":
    print("Test des Actions Rapides NOVA")
    print("=" * 40)
    
    test_clients_api()
    test_products_api()
    
    print("\nTests termines!")
