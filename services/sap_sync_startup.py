"""
Script de synchronisation automatique des données SAP au démarrage.
Lance une sync quotidienne si les données sont obsolètes (> 24h).
"""

import logging
import asyncio
from services.sap_cache_db import get_sap_cache_db
from services.sap_business_service import get_sap_business_service

logger = logging.getLogger(__name__)


async def sync_sap_data_if_needed():
    """
    Synchronise les données SAP si nécessaire (données > 24h).
    Appelé automatiquement au démarrage du backend.
    """
    cache_db = get_sap_cache_db()
    sap_service = get_sap_business_service()

    logger.info("=== Vérification cache SAP ===")

    # Vérifier les statistiques actuelles
    stats = cache_db.get_cache_stats()
    logger.info(f"Cache actuel : {stats['total_clients']} clients, {stats['total_items']} articles")

    # Synchroniser clients si nécessaire
    if cache_db.needs_sync("clients", max_age_hours=24):
        logger.info("🔄 Synchronisation clients SAP...")
        result = await cache_db.sync_clients_from_sap(sap_service)

        if result["success"]:
            logger.info(f"✅ Clients synchronisés : {result['total_records']} clients importés")
        else:
            logger.error(f"❌ Échec sync clients : {result.get('error')}")
    else:
        logger.info("✓ Cache clients à jour")

    # Synchroniser articles si nécessaire (articles actifs uniquement)
    if cache_db.needs_sync("items", max_age_hours=24):
        logger.info("🔄 Synchronisation articles SAP (actifs uniquement)...")
        result = await cache_db.sync_items_from_sap(sap_service)

        if result["success"]:
            logger.info(f"✅ Articles synchronisés : {result['total_records']} articles actifs importés")
        else:
            logger.error(f"❌ Échec sync articles : {result.get('error')}")
    else:
        logger.info("✓ Cache articles à jour")

    # Afficher les stats finales
    final_stats = cache_db.get_cache_stats()
    logger.info(f"✓ Cache SAP prêt : {final_stats['total_clients']} clients, {final_stats['total_items']} articles")
    logger.info("=" * 30)


def sync_sap_data_blocking():
    """Version bloquante pour appel depuis main.py (sans async/await)."""
    asyncio.run(sync_sap_data_if_needed())
