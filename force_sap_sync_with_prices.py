"""
Script pour forcer la resynchronisation du cache SAP avec les prix

Ce script :
1. Supprime les anciennes données du cache
2. Force une nouvelle synchronisation complète depuis SAP
3. Récupère les prix des produits (Price, Currency)
"""

import asyncio
import logging
from services.sap_cache_db import get_sap_cache_db
from services.sap_business_service import get_sap_business_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def main():
    print("\n" + "="*60)
    print("FORCE RESYNC SAP CACHE AVEC PRIX")
    print("="*60 + "\n")

    cache_db = get_sap_cache_db()
    sap_service = get_sap_business_service()

    # 1. Synchroniser les articles (avec prix)
    logger.info("🔄 Synchronisation articles SAP (avec prix)...")
    result_items = await cache_db.sync_items_from_sap(sap_service)

    if result_items['success']:
        logger.info(f"✅ Articles synchronisés: {result_items['total_records']}")
    else:
        logger.error(f"❌ Erreur sync articles")

    # 2. Synchroniser les clients
    logger.info("\n🔄 Synchronisation clients SAP...")
    result_clients = await cache_db.sync_clients_from_sap(sap_service)

    if result_clients['success']:
        logger.info(f"✅ Clients synchronisés: {result_clients['total_records']}")
    else:
        logger.error(f"❌ Erreur sync clients")

    # 3. Vérifier que les prix sont bien là
    logger.info("\n🔍 Vérification des prix récupérés...")
    items = cache_db.get_all_items()

    items_with_price = sum(1 for item in items if item.get('Price') is not None)
    items_total = len(items)

    logger.info(f"   Total articles: {items_total}")
    logger.info(f"   Articles avec prix: {items_with_price}")
    logger.info(f"   Taux couverture: {items_with_price/items_total*100:.1f}%")

    # Afficher quelques exemples
    logger.info("\n📊 Exemples d'articles avec prix:")
    count = 0
    for item in items:
        if item.get('Price') is not None and count < 5:
            logger.info(f"   - {item['ItemCode']}: {item['Price']} {item.get('Currency', 'EUR')} ({item['ItemName'][:50]})")
            count += 1

    print("\n" + "="*60)
    print("SYNCHRONISATION TERMINÉE")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
