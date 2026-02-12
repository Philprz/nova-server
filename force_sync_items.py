"""
Force la synchronisation des articles ACTIFS SAP
ATTENTION: Peut prendre 20-30 minutes pour 23571 articles
"""
import asyncio
import time
from services.sap_cache_db import get_sap_cache_db
from services.sap_business_service import get_sap_business_service

async def force_items_sync():
    cache_db = get_sap_cache_db()
    sap_service = get_sap_business_service()

    print("=== Synchronisation forcee des ARTICLES ACTIFS SAP ===\n")

    # Stats avant
    stats_before = cache_db.get_cache_stats()
    print(f"Avant: {stats_before['total_items']} articles en cache\n")

    # Forcer la synchronisation
    print("Demarrage de la synchronisation...")
    print("ATTENTION: Cela peut prendre 20-30 minutes pour ~23500 articles\n")

    start_time = time.time()
    result = await cache_db.sync_items_from_sap(sap_service)
    elapsed = time.time() - start_time

    print(f"\nResultat: {result}")
    print(f"Temps ecoule: {elapsed:.1f} secondes ({elapsed/60:.1f} minutes)")

    # Stats après
    stats_after = cache_db.get_cache_stats()
    print(f"\nApres: {stats_after['total_items']} articles en cache")

    if result["success"]:
        print(f"\n[OK] Synchronisation reussie: {result['total_records']} articles importes")
        print(f"Vitesse: {result['total_records']/(elapsed/60):.0f} articles/minute")
    else:
        print(f"\n[ERREUR] Synchronisation echouee: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(force_items_sync())
