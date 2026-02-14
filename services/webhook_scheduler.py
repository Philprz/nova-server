"""
Webhook Scheduler Service
Renouvellement automatique des webhooks Microsoft Graph

Fonctionnalités:
- Vérification quotidienne des webhooks expirant
- Renouvellement automatique avant expiration
- Logs détaillés des actions
- Intégration FastAPI lifecycle
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

logger = logging.getLogger(__name__)

class WebhookScheduler:
    """Gestionnaire de renouvellement automatique des webhooks"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._is_running = False

    def start(self):
        """Démarre le scheduler de renouvellement automatique"""
        if self._is_running:
            logger.warning("⚠️ Webhook scheduler already running")
            return

        try:
            # Créer scheduler asyncio
            self.scheduler = AsyncIOScheduler()

            # Tâche quotidienne à 09:00 (UTC+1 = 08:00 UTC)
            self.scheduler.add_job(
                self._renew_expiring_webhooks,
                trigger=CronTrigger(hour=8, minute=0),  # 09:00 Paris time
                id='webhook_renewal_daily',
                name='Webhook Renewal Daily',
                replace_existing=True
            )

            # Tâche de vérification au démarrage (1 minute après démarrage)
            self.scheduler.add_job(
                self._renew_expiring_webhooks,
                trigger='date',
                run_date=datetime.now() + timedelta(minutes=1),
                id='webhook_renewal_startup',
                name='Webhook Renewal Startup Check'
            )

            self.scheduler.start()
            self._is_running = True

            logger.info("✅ Webhook scheduler started successfully")
            logger.info("📅 Daily renewal scheduled at 09:00 (Paris time)")
            logger.info("🔍 Startup check scheduled in 1 minute")

        except Exception as e:
            logger.error(f"❌ Failed to start webhook scheduler: {e}")
            raise

    def stop(self):
        """Arrête le scheduler"""
        if not self._is_running or not self.scheduler:
            return

        try:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("🛑 Webhook scheduler stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping webhook scheduler: {e}")

    async def _renew_expiring_webhooks(self):
        """Vérifie et renouvelle les webhooks expirant dans les 24h"""
        try:
            from services.webhook_service import get_webhook_service

            logger.info("🔍 Checking for expiring webhooks...")

            webhook_service = get_webhook_service()

            # Récupérer subscriptions à renouveler (expire dans < 24h)
            subscriptions_to_renew = webhook_service.get_subscriptions_to_renew(
                hours_before_expiration=24
            )

            if not subscriptions_to_renew:
                logger.info("✅ No webhooks need renewal (all valid > 24h)")
                return

            logger.info(f"🔄 Found {len(subscriptions_to_renew)} webhook(s) to renew")

            # Renouveler chaque subscription
            renewed_count = 0
            failed_count = 0

            for subscription in subscriptions_to_renew:
                subscription_id = subscription['id']
                expiration = subscription['expiration_datetime']

                try:
                    logger.info(f"🔄 Renewing webhook {subscription_id} (expires: {expiration})")

                    result = await webhook_service.renew_subscription(subscription_id)

                    if result and 'error' not in result:
                        new_expiration = result.get('expirationDateTime', 'unknown')
                        logger.info(f"✅ Webhook renewed successfully. New expiration: {new_expiration}")
                        renewed_count += 1
                    else:
                        error_msg = result.get('error', {}).get('message', 'Unknown error') if result else 'No response'
                        logger.error(f"❌ Failed to renew webhook: {error_msg}")
                        failed_count += 1

                except Exception as e:
                    logger.error(f"❌ Exception renewing webhook {subscription_id}: {e}")
                    failed_count += 1

                # Petit délai entre renouvellements
                await asyncio.sleep(1)

            # Résumé
            logger.info(f"📊 Renewal summary: {renewed_count} renewed, {failed_count} failed")

            if failed_count > 0:
                logger.warning(f"⚠️ Some webhooks failed to renew. Manual intervention may be required.")

        except Exception as e:
            logger.error(f"❌ Error in webhook renewal task: {e}", exc_info=True)

    def get_next_run_time(self) -> Optional[str]:
        """Retourne la prochaine exécution planifiée"""
        if not self.scheduler or not self._is_running:
            return None

        job = self.scheduler.get_job('webhook_renewal_daily')
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return None

    def is_running(self) -> bool:
        """Vérifie si le scheduler est actif"""
        return self._is_running


# Singleton instance
_webhook_scheduler: Optional[WebhookScheduler] = None

def get_webhook_scheduler() -> WebhookScheduler:
    """Retourne l'instance singleton du scheduler"""
    global _webhook_scheduler
    if _webhook_scheduler is None:
        _webhook_scheduler = WebhookScheduler()
    return _webhook_scheduler


# Fonction pour FastAPI startup
async def start_webhook_scheduler():
    """Démarre le scheduler au démarrage de l'application"""
    scheduler = get_webhook_scheduler()
    scheduler.start()
    logger.info("🚀 Webhook auto-renewal system initialized")


# Fonction pour FastAPI shutdown
async def stop_webhook_scheduler():
    """Arrête le scheduler à l'arrêt de l'application"""
    scheduler = get_webhook_scheduler()
    scheduler.stop()
    logger.info("👋 Webhook auto-renewal system stopped")
