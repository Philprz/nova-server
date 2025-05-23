# tests/test_stock_fixed.py
import asyncio
import sys
import os

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mcp_connector import MCPConnector

async def test_stock_fixed():
    """Test du stock après correction"""
    print("=== TEST DU STOCK APRÈS CORRECTION ===\n")
    
    try:
        # Test avec sap_get_product_details corrigé
        print("Test avec sap_get_product_details corrigé:")
        print("-" * 50)
        
        result = await MCPConnector.call_sap_mcp("sap_get_product_details", {
            "item_code": "A00002"
        })
        
        if "error" in result:
            print(f"❌ Erreur: {result['error']}")
        else:
            print(f"✅ Produit: {result.get('ItemName', 'N/A')}")
            print(f"✅ Stock total: {result.get('stock', {}).get('total', 'N/A')}")
            print(f"✅ Prix: {result.get('Price', 'N/A')}")
            print(f"✅ Méthode utilisée: {result.get('stock', {}).get('method_used', 'N/A')}")
            
            # Détails par entrepôt
            if result.get('stock', {}).get('warehouses'):
                print("\nDétails par entrepôt:")
                total_check = 0
                for wh in result['stock']['warehouses']:
                    print(f"  - {wh.get('WarehouseCode')}: {wh.get('InStock')} en stock ({wh.get('Available')} disponible)")
                    total_check += wh.get('InStock', 0)
                print(f"  Total calculé: {total_check}")
            
            # Vérification
            expected_stock = 1123
            actual_stock = result.get('stock', {}).get('total', 0)
            
            if actual_stock == expected_stock:
                print(f"\n🎉 SUCCÈS ! Stock correct: {actual_stock} (attendu: {expected_stock})")
                return True
            else:
                print(f"\n❌ ÉCHEC ! Stock incorrect: {actual_stock} (attendu: {expected_stock})")
                return False
        
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_stock_fixed())
    if success:
        print("\n✅ Test réussi - Le stock réel est maintenant correctement récupéré !")
    else:
        print("\n❌ Test échoué - Vérifiez la correction appliquée.")