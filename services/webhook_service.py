"""
Service de gestion des webhooks Microsoft Graph
Permet de créer, renouveler et supprimer des subscriptions
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from services.graph_service import GraphService

class WebhookService:
    """Service de gestion des webhooks Microsoft Graph."""

    def __init__(self, db_path: str = "webhooks.db"):
        self.db_path = db_path
        self.graph_service = GraphService()
        self._init_database()

    def _init_database(self):
        """Initialise la base de données des subscriptions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id TEXT PRIMARY KEY,
                resource TEXT NOT NULL,
                change_type TEXT NOT NULL,
                notification_url TEXT NOT NULL,
                expiration_datetime TEXT NOT NULL,
                client_state TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                renewed_at TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)

        conn.commit()
        conn.close()

    async def create_subscription(
        self,
        resource: str = None,
        change_type: str = "created",
        notification_url: str = None,
        client_state: str = None
    ) -> Dict[str, Any]:
        """
        Crée une nouvelle subscription webhook.

        Args:
            resource: Ressource à surveiller (None = auto-detect user ID)
            change_type: Type de changement (created, updated, deleted)
            notification_url: URL pour recevoir les notifications
            client_state: Token secret pour valider les notifications

        Returns:
            Dictionnaire avec les détails de la subscription
        """
        # Construire resource avec user ID depuis .env
        if not resource:
            user_id = os.getenv("GRAPH_USER_ID")
            if not user_id:
                raise ValueError("GRAPH_USER_ID not configured in .env. Run: python get_user_id.py")
            resource = f"users/{user_id}/mailFolders('Inbox')/messages"

        if not notification_url:
            notification_url = os.getenv("WEBHOOK_NOTIFICATION_URL")

        if not notification_url:
            raise ValueError("WEBHOOK_NOTIFICATION_URL not configured in .env")

        if not client_state:
            client_state = os.getenv("WEBHOOK_CLIENT_STATE", "NOVA_WEBHOOK_SECRET_2026")

        # Durée d'expiration : 3 jours (maximum pour mailbox)
        expiration = datetime.utcnow() + timedelta(days=3)

        subscription_data = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration.isoformat() + "Z",
            "clientState": client_state
        }

        # Appeler Microsoft Graph API
        access_token = await self.graph_service.get_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://graph.microsoft.com/v1.0/subscriptions",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=subscription_data,
                timeout=30.0
            )

            if response.status_code != 201:
                error_detail = response.json()
                raise Exception(f"Failed to create subscription: {error_detail}")

            result = response.json()

        # Enregistrer en base de données
        self._save_subscription(result, client_state)

        return result

    def _save_subscription(self, subscription: Dict[str, Any], client_state: str):
        """Enregistre une subscription en base de données."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO subscriptions
            (id, resource, change_type, notification_url, expiration_datetime, client_state, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            subscription['id'],
            subscription['resource'],
            subscription['changeType'],
            subscription['notificationUrl'],
            subscription['expirationDateTime'],
            client_state,
            datetime.now().isoformat(),
            'active'
        ))

        conn.commit()
        conn.close()

    async def renew_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """
        Renouvelle une subscription existante.

        Args:
            subscription_id: ID de la subscription à renouveler

        Returns:
            Dictionnaire avec les nouveaux détails
        """
        # Nouvelle expiration : 3 jours
        expiration = datetime.utcnow() + timedelta(days=3)

        update_data = {
            "expirationDateTime": expiration.isoformat() + "Z"
        }

        # Appeler Microsoft Graph API
        access_token = await self.graph_service.get_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=update_data,
                timeout=30.0
            )

            if response.status_code != 200:
                error_detail = response.json()
                raise Exception(f"Failed to renew subscription: {error_detail}")

            result = response.json()

        # Mettre à jour en base de données
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE subscriptions
            SET expiration_datetime = ?,
                renewed_at = ?
            WHERE id = ?
        """, (
            result['expirationDateTime'],
            datetime.now().isoformat(),
            subscription_id
        ))

        conn.commit()
        conn.close()

        return result

    async def delete_subscription(self, subscription_id: str) -> bool:
        """
        Supprime une subscription.

        Args:
            subscription_id: ID de la subscription à supprimer

        Returns:
            True si suppression réussie
        """
        # Appeler Microsoft Graph API
        access_token = await self.graph_service.get_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                timeout=30.0
            )

            if response.status_code not in [204, 404]:  # 404 = déjà supprimée
                raise Exception(f"Failed to delete subscription: {response.status_code}")

        # Marquer comme inactive en base
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE subscriptions
            SET status = 'deleted'
            WHERE id = ?
        """, (subscription_id,))

        conn.commit()
        conn.close()

        return True

    def get_active_subscriptions(self) -> list:
        """Récupère toutes les subscriptions actives."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, resource, change_type, expiration_datetime, client_state
            FROM subscriptions
            WHERE status = 'active'
            ORDER BY created_at DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        subscriptions = []
        for row in rows:
            subscriptions.append({
                'id': row[0],
                'resource': row[1],
                'change_type': row[2],
                'expiration_datetime': row[3],
                'client_state': row[4]
            })

        return subscriptions

    def get_subscriptions_to_renew(self, hours_before_expiration: int = 24) -> list:
        """
        Récupère les subscriptions qui doivent être renouvelées.

        Args:
            hours_before_expiration: Nombre d'heures avant expiration (défaut: 24)

        Returns:
            Liste des subscriptions à renouveler
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Calcul date limite : maintenant + N heures
        threshold = (datetime.utcnow() + timedelta(hours=hours_before_expiration)).isoformat() + "Z"

        cursor.execute("""
            SELECT id, resource, expiration_datetime
            FROM subscriptions
            WHERE status = 'active'
            AND expiration_datetime < ?
            ORDER BY expiration_datetime ASC
        """, (threshold,))

        rows = cursor.fetchall()
        conn.close()

        subscriptions = []
        for row in rows:
            subscriptions.append({
                'id': row[0],
                'resource': row[1],
                'expiration_datetime': row[2]
            })

        return subscriptions

    def validate_notification(self, client_state: str) -> bool:
        """
        Valide qu'une notification provient bien de Microsoft.

        Args:
            client_state: Token reçu dans la notification

        Returns:
            True si valide
        """
        expected_state = os.getenv("WEBHOOK_CLIENT_STATE", "NOVA_WEBHOOK_SECRET_2026")
        return client_state == expected_state


# Singleton
_webhook_service_instance: Optional[WebhookService] = None

def get_webhook_service() -> WebhookService:
    """Retourne l'instance singleton du service webhook."""
    global _webhook_service_instance

    if _webhook_service_instance is None:
        _webhook_service_instance = WebhookService()

    return _webhook_service_instance
