# Système de Renouvellement Automatique des Webhooks

## 🎯 Objectif

Renouveler automatiquement les webhooks Microsoft Graph **directement depuis NOVA** sans dépendre du Planificateur de tâches Windows.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   NOVA Server (FastAPI)                     │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Webhook Scheduler (APScheduler)             │   │
│  │                                                        │   │
│  │  • Tâche quotidienne : 09:00 (Paris time)            │   │
│  │  • Vérification startup : 1 minute après démarrage   │   │
│  │  • Renouvellement automatique si expire < 24h        │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Webhook Service (webhook_service.py)         │   │
│  │                                                        │   │
│  │  • get_subscriptions_to_renew(hours=24)             │   │
│  │  • renew_subscription(subscription_id)               │   │
│  │  • Base SQLite : webhooks.db                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                           ▼                                  │
│           Microsoft Graph API (PATCH /subscriptions)         │
└─────────────────────────────────────────────────────────────┘
```

## 📋 Fonctionnalités

### 1. Vérification Quotidienne

- **Heure** : 09:00 heure de Paris (08:00 UTC)
- **Fréquence** : Quotidienne
- **Action** : Vérifie tous les webhooks expirant dans les 24 heures

### 2. Vérification au Démarrage

- **Déclencheur** : 1 minute après le démarrage de NOVA
- **Action** : Vérification immédiate de l'état des webhooks
- **Objectif** : S'assurer que rien n'a expiré pendant l'arrêt du serveur

### 3. Renouvellement Automatique

- **Critère** : Webhook expire dans moins de 24 heures
- **Action** : Appel Microsoft Graph PATCH /subscriptions/{id}
- **Nouvelle durée** : +3 jours à partir du moment du renouvellement
- **Logs** : Traçabilité complète dans nova.log

## 🚀 Activation

Le système est **automatique** et démarre avec NOVA :

```python
# Dans main.py (déjà intégré)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage
    await start_webhook_scheduler()

    yield

    # Arrêt
    await stop_webhook_scheduler()
```

**Aucune configuration supplémentaire requise !**

## 📊 Monitoring

### API de Statut

Vérifier le statut du scheduler :

```bash
GET /api/webhooks/scheduler/status
```

**Réponse** :

```json
{
  "success": true,
  "scheduler": {
    "is_running": true,
    "next_run_time": "2026-02-15 08:00:00",
    "timezone": "Europe/Paris (UTC+1)"
  }
}
```

### Logs

Tous les événements sont loggés dans `nova.log` :

```
2026-02-14 08:28:07 - INFO - ✅ Webhook scheduler started successfully
2026-02-14 08:28:07 - INFO - 📅 Daily renewal scheduled at 09:00 (Paris time)
2026-02-14 08:28:07 - INFO - 🔍 Startup check scheduled in 1 minute
...
2026-02-15 09:00:00 - INFO - 🔍 Checking for expiring webhooks...
2026-02-15 09:00:01 - INFO - 🔄 Found 1 webhook(s) to renew
2026-02-15 09:00:02 - INFO - ✅ Webhook renewed successfully. New expiration: 2026-02-18T09:00:00Z
```

## 🧪 Test Manuel

### Test Rapide

```bash
python test_scheduler_quick.py
```

**Sortie attendue** :

```
[TEST] WEBHOOK SCHEDULER - Test rapide

1. Démarrage scheduler...
   [OK] Scheduler démarre

2. Vérification statut...
   [OK] Running: True

3. Prochaine exécution planifiée...
   [INFO] 2026-02-15 08:00:00

4. Arrêt scheduler...
   [OK] Arrêt complet

[OK] TEST TERMINÉ AVEC SUCCÈS
```

### Test Complet (70 secondes)

```bash
python test_webhook_scheduler.py
```

Ce test attend 70 secondes pour voir la vérification startup se déclencher.

## 📁 Fichiers Créés

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `services/webhook_scheduler.py` | 175 | Service APScheduler principal |
| `test_scheduler_quick.py` | 46 | Test rapide (5 secondes) |
| `test_webhook_scheduler.py` | 52 | Test complet (70 secondes) |

## 🔧 Configuration

### Variables d'Environnement

Aucune nouvelle variable requise. Le scheduler utilise les mêmes variables que le webhook service :

```env
WEBHOOK_NOTIFICATION_URL=https://nova-rondot.itspirit.ovh/api/webhooks/notification
WEBHOOK_CLIENT_STATE=NOVA_WEBHOOK_SECRET_2026_aB3xY9zK7mN4qP2w
GRAPH_USER_ID=229aa9a1-2581-4ac1-ae1f-68273832e2e5
```

### Dépendances

Ajouté dans `requirements.txt` :

```txt
apscheduler>=3.11.0
```

## 🔄 Workflow Complet

```
Jour 1 (14/02/2026)
└─ 15:00 : Webhook créé (expire 17/02/2026 15:00)

Jour 2 (15/02/2026)
└─ 09:00 : Vérification quotidienne
           → Expire dans 2.25 jours
           → Pas de renouvellement (> 24h)

Jour 3 (16/02/2026)
└─ 09:00 : Vérification quotidienne
           → Expire dans 1.25 jours (30 heures)
           → Pas de renouvellement (> 24h)

Jour 4 (17/02/2026)
└─ 09:00 : Vérification quotidienne
           → Expire dans 6 heures (< 24h)
           → ✅ RENOUVELLEMENT AUTOMATIQUE
           → Nouvelle expiration : 20/02/2026 09:00

Jour 5 (18/02/2026)
└─ 09:00 : Vérification quotidienne
           → Expire dans 2 jours
           → Pas de renouvellement

...et ainsi de suite (boucle infinie)
```

## ⚠️ Points d'Attention

### 1. Serveur NOVA doit tourner en permanence

Le scheduler fonctionne **uniquement si NOVA est démarré**. Si le serveur est arrêté pendant plusieurs jours, le webhook peut expirer.

**Solutions** :

- ✅ **Recommandé** : Service Windows (NSSM) avec redémarrage automatique
- ✅ Monitoring externe (UptimeRobot, Pingdom)
- ✅ Alertes email si NOVA down

### 2. Fuseau horaire

Le scheduler utilise **UTC pour la planification** mais affiche **Paris time** dans les logs :

- Tâche planifiée : `08:00 UTC` = `09:00 Paris`
- Adaptation automatique heure d'été/hiver

### 3. Logs verbeux

Chaque vérification quotidienne log même si aucun renouvellement :

```
2026-02-15 09:00:00 - INFO - 🔍 Checking for expiring webhooks...
2026-02-15 09:00:01 - INFO - ✅ No webhooks need renewal (all valid > 24h)
```

**C'est normal** - confirmation que le système fonctionne.

## 🆚 Comparaison avec Planificateur de Tâches Windows

| Critère | APScheduler (intégré) | Task Scheduler Windows |
|---------|------------------------|------------------------|
| **Installation** | ✅ Aucune (auto avec NOVA) | ⚠️ Configuration manuelle |
| **Dépendance** | ✅ NOVA seulement | ⚠️ Windows + Python + NOVA |
| **Logs** | ✅ Dans nova.log | ⚠️ Logs séparés |
| **Monitoring** | ✅ API /scheduler/status | ⚠️ Interface Windows |
| **Multiplateforme** | ✅ Linux/Windows | ❌ Windows uniquement |
| **Redémarrage** | ✅ Auto avec NOVA | ⚠️ Peut échouer |

**Conclusion** : APScheduler intégré est **supérieur** dans tous les cas d'usage.

## 🎉 Avantages

1. ✅ **Zéro configuration manuelle** - Démarre automatiquement avec NOVA
2. ✅ **Multiplateforme** - Fonctionne sur Windows et Linux
3. ✅ **Logs centralisés** - Tout dans nova.log
4. ✅ **Monitoring API** - Statut via endpoint REST
5. ✅ **Double vérification** - Startup + quotidienne
6. ✅ **Logs détaillés** - Traçabilité complète
7. ✅ **Pas de point de défaillance externe** - Tout dans NOVA

## 📚 Documentation Complémentaire

- [WEBHOOK_CONFIGURATION_GUIDE.md](WEBHOOK_CONFIGURATION_GUIDE.md) - Configuration initiale webhook
- [INSTRUCTIONS_WEBHOOK.txt](INSTRUCTIONS_WEBHOOK.txt) - Instructions pas à pas
- [APScheduler Documentation](https://apscheduler.readthedocs.io/) - Documentation officielle

## 🆘 Dépannage

### Le scheduler ne démarre pas

**Symptôme** : Pas de logs "Webhook scheduler started"

**Solution** :

```bash
# Vérifier que APScheduler est installé
pip install apscheduler

# Redémarrer NOVA
python main.py
```

### Pas de renouvellement alors que webhook expire < 24h

**Symptôme** : Logs montrent "No webhooks need renewal" alors que webhook expire bientôt

**Solution** :

1. Vérifier base SQLite `webhooks.db` :

```python
from services.webhook_service import get_webhook_service
webhook_service = get_webhook_service()
subs = webhook_service.get_subscriptions_to_renew(hours_before_expiration=48)
print(subs)
```

2. Forcer renouvellement manuel :

```bash
python renew_webhook.py
```

### Erreur "Task was destroyed but it is pending"

**Symptôme** : Erreur asyncio au shutdown

**Cause** : Tâche scheduler non attendue proprement

**Solution** : Déjà géré dans `stop_webhook_scheduler()` avec `wait=False`

---

**Version** : 2.6.0
**Date** : 13/02/2026
**Auteur** : Philippe PEREZ (ITSpirit)
