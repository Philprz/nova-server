#!/usr/bin/env python3
# test_connections.py - Script pour tester les connexions système

import asyncio
import sys
import os

# Ajouter le répertoire parent au path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mcp_connector import MCPConnector
import logging

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_all_connections():
    """Test complet des connexions système"""
    print("🔍 === TEST DES CONNEXIONS SYSTÈME ===")
    
    # Test 1: Connexions générales
    print("\n1️⃣ Test des connexions générales...")
    try:
        connections = await MCPConnector.test_connections()
        print(f"✅ Résultat: {connections}")
        
        sf_connected = connections.get('salesforce', {}).get('connected', False)
        sap_connected = connections.get('sap', {}).get('connected', False)
        
        print(f"📊 Salesforce: {'✅ Connecté' if sf_connected else '❌ Déconnecté'}")
        print(f"🏭 SAP: {'✅ Connecté' if sap_connected else '❌ Déconnecté'}")
        
    except Exception as e:
        print(f"❌ Erreur test connexions: {e}")

    # Test 2: Salesforce spécifique
    print("\n2️⃣ Test Salesforce spécifique...")
    try:
        sf_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
            "query": "SELECT Id, Name FROM Account LIMIT 3"
        })
        
        if "error" in sf_result:
            print(f"❌ Erreur Salesforce: {sf_result['error']}")
        else:
            print(f"✅ Salesforce OK - {sf_result.get('totalSize', 0)} comptes trouvés")
            # Afficher les comptes
            for record in sf_result.get('records', []):
                print(f"   - {record.get('Name')} (ID: {record.get('Id')})")
                
    except Exception as e:
        print(f"❌ Erreur Salesforce: {e}")

    # Test 3: SAP spécifique
    print("\n3️⃣ Test SAP spécifique...")
    try:
        sap_result = await MCPConnector.call_sap_mcp("ping", {})
        
        if "error" in sap_result:
            print(f"❌ Erreur SAP: {sap_result['error']}")
        else:
            print(f"✅ SAP Ping OK: {sap_result}")
            
        # Test requête clients SAP
        print("\n   Test requête clients SAP...")
        sap_clients = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/BusinessPartners?$filter=CardType eq 'cCustomer'&$top=3",
            "method": "GET"
        })
        
        if "error" in sap_clients:
            print(f"❌ Erreur clients SAP: {sap_clients['error']}")
        else:
            print(f"✅ Clients SAP OK - {len(sap_clients.get('value', []))} clients")
            # Afficher les clients
            for client in sap_clients.get('value', [])[:3]:
                print(f"   - {client.get('CardName')} (Code: {client.get('CardCode')})")
                
    except Exception as e:
        print(f"❌ Erreur SAP: {e}")

    # Test 4: Produits SAP (FONCTION CORRIGÉE)
    print("\n4️⃣ Test produits SAP...")
    try:
        sap_products = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$top=3",
            "method": "GET"
        })
        
        if "error" in sap_products:
            print(f"❌ Erreur produits SAP: {sap_products['error']}")
        else:
            print(f"✅ Produits SAP OK - {len(sap_products.get('value', []))} produits")
            # Afficher les produits
            for product in sap_products.get('value', [])[:3]:
                print(f"   - {product.get('ItemName')} (Code: {product.get('ItemCode')})")
                
        # Test 4b: Détails d'un produit spécifique (si on en a trouvé un)
        if sap_products.get('value') and len(sap_products['value']) > 0:
            first_product_code = sap_products['value'][0].get('ItemCode')
            if first_product_code:
                print(f"\n   Test détails produit {first_product_code}...")
                product_details = await MCPConnector.call_sap_mcp("sap_get_product_details", {
                    "item_code": first_product_code
                })
                
                if "error" in product_details:
                    print(f"❌ Erreur détails produit: {product_details['error']}")
                else:
                    print(f"✅ Détails produit OK - Prix: {product_details.get('Price', 'N/A')}")
                    
    except Exception as e:
        print(f"❌ Erreur produits SAP: {e}")

    # Test 5: Recherche SAP (test de sap_search)
    print("\n5️⃣ Test recherche SAP...")
    try:
        search_result = await MCPConnector.call_sap_mcp("sap_search", {
            "query": "test",
            "entity_type": "Items", 
            "limit": 2
        })
        
        if "error" in search_result:
            print(f"❌ Erreur recherche SAP: {search_result['error']}")
        else:
            results = search_result.get('results', [])
            print(f"✅ Recherche SAP OK - {len(results)} résultats")
            for result in results[:2]:
                print(f"   - {result.get('ItemName', 'N/A')} (Code: {result.get('ItemCode', 'N/A')})")
                
    except Exception as e:
        print(f"❌ Erreur recherche SAP: {e}")
                
    except Exception as e:
        print(f"❌ Erreur produits SAP: {e}")
    print("\n🎯 === RÉSUMÉ DES TESTS ===")
    print("Si toutes les connexions sont ✅, vous pouvez activer le mode production.")
    print("Si certaines connexions sont ❌, vérifiez la configuration dans le fichier .env")

if __name__ == "__main__":
    asyncio.run(test_all_connections())