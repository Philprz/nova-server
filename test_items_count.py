"""
Test pour compter le nombre total d'articles dans SAP B1
"""
import asyncio
from services.sap_business_service import get_sap_business_service

async def count_sap_items():
    sap = get_sap_business_service()

    print("=== Comptage des articles SAP B1 ===\n")

    # Méthode 1: Utiliser $count pour obtenir le nombre total
    try:
        result = await sap._call_sap("/Items/$count", params={})
        print(f"[OK] Methode 1 ($count): {result} articles")
    except Exception as e:
        print(f"[ERREUR] Methode 1 echouee: {e}")

    # Méthode 2: Pagination complète pour compter manuellement
    print("\n=== Methode 2: Pagination complete ===")
    all_items = []
    skip = 0
    batch_size = 20

    while True:
        result = await sap._call_sap("/Items", params={
            "$select": "ItemCode,ItemName,ItemsGroupCode",
            "$top": batch_size,
            "$skip": skip,
            "$orderby": "ItemCode"
        })

        batch = result.get('value', [])
        if not batch:
            break

        all_items.extend(batch)
        print(f"  Skip {skip:4d}: {len(batch)} articles recuperes (Total: {len(all_items)})")

        skip += batch_size

        if len(batch) < batch_size:
            break

        # Limite pour éviter un temps d'exécution trop long
        if len(all_items) >= 1000:
            print(f"\n[INFO] Test limite a 1000 articles pour performance")
            break

    print(f"\n[OK] Total compte: {len(all_items)} articles")

    # Vérifier la base SQLite
    from services.sap_cache_db import get_sap_cache_db
    cache_db = get_sap_cache_db()
    stats = cache_db.get_cache_stats()

    print(f"\n=== Comparaison ===")
    print(f"SAP B1:      {len(all_items)} articles (limite test)")
    print(f"Cache local: {stats['total_items']} articles")

    # Vérifier les articles avec ItemName NULL
    null_names = [item for item in all_items if not item.get("ItemName")]
    if null_names:
        print(f"\n[WARN] {len(null_names)} articles avec ItemName NULL:")
        for item in null_names[:5]:
            print(f"  - {item.get('ItemCode')}: ItemName = {item.get('ItemName')}")

if __name__ == "__main__":
    asyncio.run(count_sap_items())
