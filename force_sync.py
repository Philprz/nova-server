"""
Force la synchronisation complète des clients SAP
"""
import asyncio
from services.sap_cache_db import get_sap_cache_db
from services.sap_business_service import get_sap_business_service

async def force_full_sync():
    cache_db = get_sap_cache_db()
    sap_service = get_sap_business_service()

    print("=== Synchronisation forcee des clients SAP ===\n")

    # Stats avant
    stats_before = cache_db.get_cache_stats()
    print(f"Avant: {stats_before['total_clients']} clients en cache\n")

    # Forcer la synchronisation
    print("Demarrage de la synchronisation...")
    result = await cache_db.sync_clients_from_sap(sap_service)

    print(f"\nResultat: {result}")

    # Stats après
    stats_after = cache_db.get_cache_stats()
    print(f"\nApres: {stats_after['total_clients']} clients en cache")

    if result["success"]:
        print(f"\n[OK] Synchronisation reussie: {result['total_records']} clients importes")
    else:
        print(f"\n[ERREUR] Synchronisation echouee: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(force_full_sync())
