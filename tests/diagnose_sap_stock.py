# tests/diagnose_sap_stock.py
import asyncio
import json
import sys
import os

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mcp_connector import MCPConnector

async def diagnose_sap_stock_api():
    """Diagnostic complet des endpoints SAP pour trouver le stock réel"""
    print("=== DIAGNOSTIC DES ENDPOINTS SAP POUR LE STOCK ===\n")
    
    try:
        # 1. Tester différentes requêtes sur Items pour voir quels champs sont disponibles
        print("1. Structure complète de l'objet Item A00002:")
        print("-" * 60)
        
        full_item = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Items('A00002')",
            "method": "GET"
        })
        
        if "error" not in full_item:
            print("Champs disponibles dans l'objet Item:")
            for key, value in full_item.items():
                if not key.startswith('_'):
                    print(f"  - {key}: {value}")
            print()
        
        # 2. Tester avec $select pour demander explicitement les champs de stock
        print("2. Requête avec $select explicite pour les champs de stock:")
        print("-" * 60)
        
        stock_fields_item = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Items('A00002')?$select=ItemCode,ItemName,OnHand,IsCommitted,Ordered,QuantityOnStock,InStock",
            "method": "GET"
        })
        
        if "error" not in stock_fields_item:
            print("Résultat avec $select stock:")
            print(json.dumps(stock_fields_item, indent=2))
        else:
            print(f"Erreur avec $select: {stock_fields_item['error']}")
        print()
        
        # 3. Essayer d'autres endpoints liés aux stocks
        print("3. Test d'endpoints alternatifs pour le stock:")
        print("-" * 60)
        
        # Essayer WarehouseStockInfo ou StockTransfer
        endpoints_to_test = [
            "/Items('A00002')/ItemWarehouseInfoCollection",
            "/WarehouseStockInfo?$filter=ItemCode eq 'A00002'",
            "/StockTransfers?$filter=StockTransferLines/any(line: line/ItemCode eq 'A00002')&$top=1",
            "/InventoryGenEntries?$filter=DocumentLines/any(line: line/ItemCode eq 'A00002')&$top=1",
            "/Items('A00002')?$expand=ItemWarehouseInfoCollection"
        ]
        
        for endpoint in endpoints_to_test:
            print(f"Test: {endpoint}")
            result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": endpoint,
                "method": "GET"
            })
            
            if "error" not in result:
                if "value" in result and result["value"]:
                    print(f"  ✅ Données trouvées: {len(result['value'])} éléments")
                    if len(result["value"]) > 0:
                        print(f"  Premier élément: {json.dumps(result['value'][0], indent=4)}")
                elif result:
                    print(f"  ✅ Données trouvées (objet direct)")
                    print(f"  Contenu: {json.dumps(result, indent=4)}")
                else:
                    print(f"  ⚠️ Réponse vide")
            else:
                print(f"  ❌ Erreur: {result['error']}")
            print()
        
        # 4. Essayer de lister les entrepôts pour comprendre la structure
        print("4. Liste des entrepôts disponibles:")
        print("-" * 60)
        
        warehouses = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Warehouses",
            "method": "GET"
        })
        
        if "error" not in warehouses and "value" in warehouses:
            print("Entrepôts disponibles:")
            for wh in warehouses["value"]:
                print(f"  - Code: {wh.get('WarehouseCode', 'N/A')}, Nom: {wh.get('WarehouseName', 'N/A')}")
            print()
            
            # 5. Essayer de récupérer le stock pour chaque entrepôt
            print("5. Stock par entrepôt pour A00002:")
            print("-" * 60)
            
            for wh in warehouses["value"][:3]:  # Limiter aux 3 premiers
                wh_code = wh.get('WarehouseCode', '')
                print(f"Entrepôt {wh_code}:")
                
                # Essayer différentes approches pour cet entrepôt
                wh_endpoints = [
                    f"/Items('A00002')/ItemWarehouseInfoCollection?$filter=WarehouseCode eq '{wh_code}'",
                    f"/Items('A00002')/ItemWarehouseInfoCollection('{wh_code}')",
                    f"/ItemWarehouseInfo?$filter=ItemCode eq 'A00002' and WarehouseCode eq '{wh_code}'"
                ]
                
                for wh_endpoint in wh_endpoints:
                    result = await MCPConnector.call_sap_mcp("sap_read", {
                        "endpoint": wh_endpoint,
                        "method": "GET"
                    })
                    
                    if "error" not in result:
                        print(f"  ✅ {wh_endpoint}")
                        if "value" in result and result["value"]:
                            for item in result["value"]:
                                print(f"     InStock: {item.get('InStock', 'N/A')}")
                                print(f"     Committed: {item.get('Committed', 'N/A')}")
                                print(f"     Ordered: {item.get('Ordered', 'N/A')}")
                        elif result:
                            print(f"     InStock: {result.get('InStock', 'N/A')}")
                            print(f"     Committed: {result.get('Committed', 'N/A')}")
                            print(f"     Ordered: {result.get('Ordered', 'N/A')}")
                        break
                    else:
                        print(f"  ❌ {wh_endpoint}: {result['error']}")
                print()
        
        # 6. Tester des requêtes OData plus complexes
        print("6. Tests de requêtes OData avancées:")
        print("-" * 60)
        
        advanced_queries = [
            "/Items?$filter=ItemCode eq 'A00002'&$expand=ItemWarehouseInfoCollection",
            "/$metadata",  # Pour voir la structure complète
            "/Items('A00002')?$expand=*"  # Expand all
        ]
        
        for query in advanced_queries:
            print(f"Test: {query}")
            result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": query,
                "method": "GET"
            })
            
            if "error" not in result:
                if query == "/$metadata":
                    print(f"  ✅ Métadonnées disponibles ({len(str(result))} caractères)")
                    # Chercher les informations sur Items dans les métadonnées
                    metadata_str = str(result)
                    if "OnHand" in metadata_str:
                        print("  📊 OnHand trouvé dans les métadonnées")
                    if "InStock" in metadata_str:
                        print("  📊 InStock trouvé dans les métadonnées")
                    if "ItemWarehouseInfo" in metadata_str:
                        print("  📊 ItemWarehouseInfo trouvé dans les métadonnées")
                else:
                    print(f"  ✅ Données récupérées")
                    if isinstance(result, dict) and "value" in result:
                        print(f"  Nombre d'éléments: {len(result['value'])}")
                    print(f"  Taille de la réponse: {len(str(result))} caractères")
            else:
                print(f"  ❌ Erreur: {result['error']}")
            print()
        
        print("=== FIN DU DIAGNOSTIC ===")
        print("Analysez les résultats ci-dessus pour identifier la bonne méthode d'accès au stock.")
        
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(diagnose_sap_stock_api())
    