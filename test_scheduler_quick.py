"""
Test rapide du scheduler webhook
"""

import asyncio
import logging
from services.webhook_scheduler import get_webhook_scheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def quick_test():
    print("\n[TEST] WEBHOOK SCHEDULER - Test rapide\n")

    scheduler = get_webhook_scheduler()

    # Test 1: Démarrage
    print("1. Démarrage scheduler...")
    try:
        scheduler.start()
        print("   [OK] Scheduler démarre")
    except Exception as e:
        print(f"   [ERREUR] {e}")
        return

    await asyncio.sleep(1)

    # Test 2: Statut
    print("\n2. Vérification statut...")
    is_running = scheduler.is_running()
    print(f"   [{'OK' if is_running else 'ERREUR'}] Running: {is_running}")

    # Test 3: Prochaine exécution
    print("\n3. Prochaine exécution planifiée...")
    next_run = scheduler.get_next_run_time()
    print(f"   [INFO] {next_run if next_run else 'Non planifiée'}")

    # Test 4: Arrêt
    print("\n4. Arrêt scheduler...")
    scheduler.stop()
    await asyncio.sleep(1)
    print(f"   [{'OK' if not scheduler.is_running() else 'ERREUR'}] Arrêt complet")

    print("\n[OK] TEST TERMINÉ AVEC SUCCÈS\n")

if __name__ == "__main__":
    asyncio.run(quick_test())
