"""
Synchronise le cache SAP local avec les données SAP en temps réel.
À exécuter régulièrement (1x par jour) ou après ajout de nouveaux articles dans SAP.
"""

import asyncio
import logging
from services.sap_cache_db import get_sap_cache_db
from services.sap_business_service import get_sap_business_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def sync_sap_cache():
    """
    Synchronise le cache local avec SAP.
    - Articles (Items)
    - Clients (BusinessPartners)
    """
    print("=" * 60)
    print("SYNCHRONISATION CACHE SAP")
    print("=" * 60)

    try:
        cache = get_sap_cache_db()
        sap = get_sap_business_service()

        # 1. Synchroniser les articles
        print("\n[1/2] Synchronisation articles SAP...")
        print("  (Peut prendre 2-5 minutes selon le nombre d'articles)")

        try:
            items_result = await cache.sync_items_from_sap(sap)

            if items_result.get("success"):
                print(f"  [OK] Articles synchronises")
                print(f"    Total: {items_result.get('total_synced', 0)}")
                print(f"    Nouveaux: {items_result.get('new', 0)}")
                print(f"    Mis a jour: {items_result.get('updated', 0)}")
                print(f"    Duree: {items_result.get('duration_seconds', 0):.1f}s")
            else:
                print(f"  [ERREUR] {items_result.get('error', 'Erreur inconnue')}")
                return False

        except Exception as e:
            print(f"  [ERREUR] Erreur sync articles: {e}")
            return False

        # 2. Synchroniser les clients
        print("\n[2/2] Synchronisation clients SAP...")

        try:
            clients_result = await cache.sync_clients_from_sap(sap)

            if clients_result.get("success"):
                print(f"  [OK] Clients synchronises")
                print(f"    Total: {clients_result.get('total_synced', 0)}")
                print(f"    Nouveaux: {clients_result.get('new', 0)}")
                print(f"    Mis a jour: {clients_result.get('updated', 0)}")
                print(f"    Duree: {clients_result.get('duration_seconds', 0):.1f}s")
            else:
                print(f"  [ERREUR] {clients_result.get('error', 'Erreur inconnue')}")

        except Exception as e:
            print(f"  [ERREUR] Erreur sync clients: {e}")

        # 3. Statistiques finales
        print("\n" + "=" * 60)
        print("STATISTIQUES CACHE")
        print("=" * 60)

        stats = cache.get_statistics()
        print(f"  Articles en cache: {stats.get('items', 0)}")
        print(f"  Clients en cache: {stats.get('clients', 0)}")
        print(f"  Derniere MAJ: {stats.get('last_sync', 'Jamais')}")

        print("\n[OK] Synchronisation terminee avec succes !")
        return True

    except Exception as e:
        print(f"\n[ERREUR CRITIQUE] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(sync_sap_cache())
    exit(0 if success else 1)
