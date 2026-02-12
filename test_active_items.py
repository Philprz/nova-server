"""
Test pour compter les articles ACTIFS dans SAP B1
"""
import asyncio
from services.sap_business_service import get_sap_business_service

async def count_active_items():
    sap = get_sap_business_service()

    print("=== Comptage des articles ACTIFS SAP B1 ===\n")

    # Test 1: Articles actifs (Valid = Y)
    try:
        result = await sap._call_sap("/Items/$count", params={
            "$filter": "Valid eq 'Y'"
        })
        print(f"[OK] Articles actifs (Valid=Y): {result}")
    except Exception as e:
        print(f"[ERREUR] Filter Valid: {e}")

    # Test 2: Articles non gelés (Frozen = N)
    try:
        result = await sap._call_sap("/Items/$count", params={
            "$filter": "Frozen eq 'N'"
        })
        print(f"[OK] Articles non geles (Frozen=N): {result}")
    except Exception as e:
        print(f"[ERREUR] Filter Frozen: {e}")

    # Test 3: Articles actifs ET non gelés
    try:
        result = await sap._call_sap("/Items/$count", params={
            "$filter": "Valid eq 'Y' and Frozen eq 'N'"
        })
        print(f"[OK] Articles actifs ET non geles: {result}")
    except Exception as e:
        print(f"[ERREUR] Filter combine: {e}")

    # Test 4: Échantillon d'articles actifs
    print("\n=== Echantillon d'articles actifs ===")
    try:
        result = await sap._call_sap("/Items", params={
            "$select": "ItemCode,ItemName,Valid,Frozen,ItemsGroupCode",
            "$filter": "Valid eq 'Y' and Frozen eq 'N'",
            "$top": 10
        })

        items = result.get('value', [])
        print(f"\nPremiers 10 articles actifs:")
        for item in items:
            print(f"  - {item.get('ItemCode')}: {item.get('ItemName')} (Valid={item.get('Valid')}, Frozen={item.get('Frozen')})")
    except Exception as e:
        print(f"[ERREUR] Sample: {e}")

if __name__ == "__main__":
    asyncio.run(count_active_items())
