"""
Test du système de renouvellement automatique des webhooks
"""

import asyncio
import logging
from services.webhook_scheduler import get_webhook_scheduler

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_scheduler():
    """Test du scheduler"""
    print("=" * 60)
    print("TEST WEBHOOK SCHEDULER")
    print("=" * 60)

    # Récupérer scheduler
    scheduler = get_webhook_scheduler()

    # Démarrer
    print("\n1. Démarrage du scheduler...")
    scheduler.start()
    await asyncio.sleep(2)

    # Vérifier statut
    print(f"\n2. Statut: {'✅ Running' if scheduler.is_running() else '❌ Stopped'}")

    # Prochaine exécution
    next_run = scheduler.get_next_run_time()
    print(f"3. Prochaine exécution: {next_run}")

    print("\n4. Attente 70 secondes pour voir si la vérification startup se lance...")
    print("   (La vérification startup est programmée 1 minute après le démarrage)")

    # Attendre 70 secondes pour voir les logs
    for i in range(7):
        await asyncio.sleep(10)
        print(f"   ... {(i+1)*10} secondes écoulées")

    # Arrêter
    print("\n5. Arrêt du scheduler...")
    scheduler.stop()
    await asyncio.sleep(1)

    print(f"\n6. Statut final: {'❌ Stopped' if not scheduler.is_running() else '✅ Still running'}")

    print("\n" + "=" * 60)
    print("TEST TERMINÉ")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_scheduler())
