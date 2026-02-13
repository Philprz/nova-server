"""
Script pour enregistrer un webhook Microsoft Graph
À exécuter une fois pour créer la subscription initiale
"""

import asyncio
import sys
import os

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.webhook_service import get_webhook_service


async def register_webhook():
    """Enregistre un nouveau webhook Microsoft Graph."""
    print("=" * 80)
    print("REGISTRATION WEBHOOK MICROSOFT GRAPH")
    print("=" * 80)
    print()

    webhook_service = get_webhook_service()

    # Configuration
    user_id = os.getenv("GRAPH_USER_ID")
    if not user_id:
        print("[ERREUR] GRAPH_USER_ID not configured in .env")
        print()
        print("Please run first:")
        print("  python get_user_id.py")
        print()
        return

    resource = f"users/{user_id}/mailFolders('Inbox')/messages"
    change_type = "created"
    notification_url = os.getenv("WEBHOOK_NOTIFICATION_URL")
    client_state = os.getenv("WEBHOOK_CLIENT_STATE", "NOVA_WEBHOOK_SECRET_2026")

    print(f"User ID: {user_id}")
    print(f"Resource: {resource}")
    print(f"Change Type: {change_type}")
    print(f"Notification URL: {notification_url}")
    print(f"Client State: {client_state[:10]}...")
    print()

    if not notification_url:
        print("[ERREUR] WEBHOOK_NOTIFICATION_URL not configured in .env")
        print()
        print("Please add to .env:")
        print("WEBHOOK_NOTIFICATION_URL=https://nova-rondot.itspirit.ovh/api/webhooks/notification")
        print()
        return

    try:
        print("[INFO] Creating subscription...")
        result = await webhook_service.create_subscription(
            resource=resource,
            change_type=change_type,
            notification_url=notification_url,
            client_state=client_state
        )

        print()
        print("[OK] Webhook registered successfully!")
        print()
        print(f"Subscription ID: {result['id']}")
        print(f"Resource: {result['resource']}")
        print(f"Change Type: {result['changeType']}")
        print(f"Expiration: {result['expirationDateTime']}")
        print()
        print("=" * 80)
        print("NEXT STEPS")
        print("=" * 80)
        print()
        print("1. The webhook is now active")
        print("2. New emails will be processed automatically")
        print("3. Subscription expires in 3 days")
        print()
        print("To renew before expiration:")
        print("  python renew_webhook.py")
        print()
        print("Or setup automatic renewal (cron/task scheduler):")
        print("  Daily: python renew_webhook.py")
        print()

    except Exception as e:
        print()
        print(f"[ERREUR] Failed to register webhook: {e}")
        print()
        import traceback
        traceback.print_exc()
        print()
        print("Common issues:")
        print("1. WEBHOOK_NOTIFICATION_URL must be HTTPS (not HTTP)")
        print("2. URL must be publicly accessible from internet")
        print("3. Microsoft Graph credentials must be valid")
        print("4. Application must have Mail.Read permission")
        print()


if __name__ == "__main__":
    asyncio.run(register_webhook())
