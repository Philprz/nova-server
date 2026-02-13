"""
Script pour renouveler les webhooks Microsoft Graph
À exécuter quotidiennement (cron/task scheduler)
"""

import asyncio
import sys
import os

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.webhook_service import get_webhook_service


async def renew_webhooks():
    """Renouvelle les webhooks qui expirent bientôt."""
    print("=" * 80)
    print("RENOUVELLEMENT WEBHOOKS MICROSOFT GRAPH")
    print("=" * 80)
    print()

    webhook_service = get_webhook_service()

    # Lister les subscriptions à renouveler (expire < 24h)
    print("[INFO] Checking for subscriptions to renew...")
    subscriptions = webhook_service.get_subscriptions_to_renew()

    if not subscriptions:
        print("[OK] No subscriptions need renewal")
        print()

        # Afficher les subscriptions actives
        active_subs = webhook_service.get_active_subscriptions()
        if active_subs:
            print(f"Active subscriptions: {len(active_subs)}")
            for sub in active_subs:
                print(f"  - {sub['id']} (expires: {sub['expiration_datetime']})")
        print()
        return

    print(f"[INFO] Found {len(subscriptions)} subscription(s) to renew")
    print()

    for sub in subscriptions:
        subscription_id = sub['id']
        expiration = sub['expiration_datetime']

        print(f"Renewing: {subscription_id}")
        print(f"  Current expiration: {expiration}")

        try:
            result = await webhook_service.renew_subscription(subscription_id)

            print(f"  [OK] Renewed successfully")
            print(f"  New expiration: {result['expirationDateTime']}")
            print()

        except Exception as e:
            print(f"  [ERREUR] Failed to renew: {e}")
            print()

    print("=" * 80)
    print("RENEWAL COMPLETE")
    print("=" * 80)
    print()
    print("To setup automatic renewal:")
    print()
    print("Windows Task Scheduler:")
    print("  1. Open Task Scheduler")
    print("  2. Create Basic Task")
    print("  3. Trigger: Daily at 09:00")
    print("  4. Action: Start a program")
    print("  5. Program: python")
    print(f"  6. Arguments: {os.path.abspath(__file__)}")
    print(f"  7. Start in: {os.path.dirname(os.path.abspath(__file__))}")
    print()
    print("Linux/Mac Cron:")
    print("  crontab -e")
    print(f"  0 9 * * * cd {os.path.dirname(os.path.abspath(__file__))} && python renew_webhook.py")
    print()


if __name__ == "__main__":
    asyncio.run(renew_webhooks())
