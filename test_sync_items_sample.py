"""
Test de synchronisation avec un ÉCHANTILLON d'articles (100 premiers)
"""
import asyncio
from services.sap_cache_db import SAPCacheDB
from services.sap_business_service import get_sap_business_service
import sqlite3
from datetime import datetime

async def test_sample_sync():
    sap_service = get_sap_business_service()

    print("=== Test synchronisation 100 premiers articles actifs ===\n")

    # Récupérer 100 articles actifs
    all_items = []
    skip = 0
    batch_size = 20

    for i in range(5):  # 5 batches = 100 articles max
        result = await sap_service._call_sap("/Items", params={
            "$select": "ItemCode,ItemName,ItemsGroupCode",
            "$filter": "Valid eq 'Y' and Frozen eq 'N'",
            "$top": batch_size,
            "$skip": skip,
            "$orderby": "ItemCode"
        })

        batch = result.get('value', [])
        if not batch:
            break

        all_items.extend(batch)
        print(f"Batch {i+1}: {len(batch)} articles recuperes (Total: {len(all_items)})")
        skip += batch_size

        if len(batch) < batch_size:
            break

    # Test insertion dans SQLite
    print(f"\nTest insertion de {len(all_items)} articles dans SQLite...")

    db_path = "C:/Users/PPZ/NOVA-SERVER/supplier_tariffs.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    inserted = 0
    errors = 0

    for item in all_items:
        try:
            # Gérer les ItemName NULL
            item_name = item.get("ItemName") or item.get("ItemCode") or "Unknown"

            cursor.execute("""
                INSERT OR REPLACE INTO sap_items
                (ItemCode, ItemName, ItemGroup, last_updated)
                VALUES (?, ?, ?, ?)
            """, (
                item.get("ItemCode"),
                item_name,
                item.get("ItemsGroupCode"),
                datetime.now().isoformat()
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            print(f"  [ERREUR] {item.get('ItemCode')}: {e}")

    conn.commit()
    conn.close()

    print(f"\n[OK] {inserted} articles inseres, {errors} erreurs")

    # Vérifier dans le cache
    from services.sap_cache_db import get_sap_cache_db
    cache_db = get_sap_cache_db()
    stats = cache_db.get_cache_stats()
    print(f"Cache: {stats['total_items']} articles")

if __name__ == "__main__":
    asyncio.run(test_sample_sync())
