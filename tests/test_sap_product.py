# test_sap_product.py
import asyncio
from services.mcp_connector import MCPConnector

async def test_product_a00002():
    """Test si le produit A00002 existe dans SAP"""
    print("=== TEST PRODUIT A00002 DANS SAP ===")
    
    try:
        # 1. Recherche du produit
        print("1. Recherche du produit A00002...")
        search_result = await MCPConnector.call_sap_mcp("sap_search", {
            "query": "A00002",
            "entity_type": "Items",
            "limit": 5
        })
        
        print(f"Résultat recherche: {search_result}")
        
        # 2. Détails du produit
        print("\n2. Récupération des détails...")
        details_result = await MCPConnector.call_sap_mcp("sap_get_product_details", {
            "item_code": "A00002"
        })
        
        print(f"Détails produit: {details_result}")
        
        # 3. Lecture directe via endpoint
        print("\n3. Lecture directe via endpoint...")
        direct_result = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Items('A00002')",
            "method": "GET"
        })
        
        print(f"Lecture directe: {direct_result}")
        
        # 4. Liste des premiers produits pour comparaison
        print("\n4. Liste des premiers produits...")
        list_result = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Items?$top=5",
            "method": "GET"
        })
        
        if "value" in list_result:
            print("Premiers produits dans SAP:")
            for item in list_result["value"]:
                print(f"  - {item.get('ItemCode', 'N/A')} : {item.get('ItemName', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_product_a00002())