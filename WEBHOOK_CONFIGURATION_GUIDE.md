# Configuration Webhook Microsoft Graph - Guide Complet

**Date** : 2026-02-13
**Objectif** : Traitement 100% automatique des emails dès leur arrivée

---

## 📋 Vue d'Ensemble

Le webhook Microsoft Graph permet de recevoir des notifications en temps réel quand un nouvel email arrive dans la boîte de réception.

**Workflow avec webhook** :
```
1. Email arrive dans boîte mail Microsoft 365
   ↓
2. Microsoft envoie notification webhook → NOVA
   ↓
3. NOVA traite automatiquement en arrière-plan
   ├─ Détection devis
   ├─ Identification client SAP
   ├─ Matching produits SAP
   ├─ Calcul pricing automatique
   └─ Sauvegarde en DB
   ↓
4. Utilisateur se connecte (30 min plus tard)
   └─ Tous les devis déjà traités, bouton "Synthèse" affiché
```

---

## 🔧 Prérequis

### 1. URL Publique HTTPS

**Le webhook DOIT être accessible depuis internet en HTTPS**

Votre configuration actuelle :
```
https://nova-rondot.itspirit.ovh
```

✅ **OK** : Domaine public avec HTTPS

---

### 2. Permissions Microsoft Graph

L'application Azure AD doit avoir ces permissions :

- ✅ **Mail.Read** - Lire les emails
- ✅ **Mail.ReadWrite** - Modifier emails (marquer lu, etc.)
- ⚠️ **Mail.ReadBasic.All** (optionnel) - Lire métadonnées

**Vérifier permissions** :
1. Portail Azure → Azure Active Directory
2. App registrations → Votre app NOVA
3. API permissions → Vérifier Mail.Read

---

### 3. Variables .env

Ajouter ces variables dans `.env` :

```env
# ============================================
# WEBHOOK MICROSOFT GRAPH
# ============================================

# URL publique pour recevoir les notifications
WEBHOOK_NOTIFICATION_URL=https://nova-rondot.itspirit.ovh/api/webhooks/notification

# Token secret pour valider les notifications (générer un token aléatoire)
WEBHOOK_CLIENT_STATE=NOVA_WEBHOOK_SECRET_2026_aB3xY9zK

# Note: Changez le CLIENT_STATE pour un token unique et complexe
```

**Générer un client_state sécurisé** :
```python
import secrets
print(secrets.token_urlsafe(32))
# Exemple: NOVA_WEBHOOK_SECRET_2026_aB3xY9zK7mN4qP2wR5sT8uV
```

---

## 📦 Fichiers Créés

| Fichier | Description |
|---------|-------------|
| `services/webhook_service.py` | Service gestion webhooks (créer/renouveler/supprimer) |
| `routes/routes_webhooks.py` | Endpoint pour recevoir notifications |
| `register_webhook.py` | Script enregistrement initial |
| `renew_webhook.py` | Script renouvellement (cron) |
| `webhooks.db` | Base SQLite subscriptions |

---

## 🚀 Installation

### Étape 1 : Configuration .env

Ajouter les variables ci-dessus dans `.env`

```bash
# Vérifier que les variables sont présentes
cat .env | grep WEBHOOK
```

---

### Étape 2 : Démarrer le Serveur

Le serveur DOIT être démarré pour recevoir la validation initiale du webhook.

```bash
cd C:\Users\PPZ\NOVA-SERVER
python main.py
```

**Vérifier logs** :
```
[INFO] Webhooks routes registered at /api/webhooks
[INFO] EmailAnalysisDB initialized
[INFO] Application startup complete
```

---

### Étape 3 : Enregistrer le Webhook

**Dans un NOUVEAU terminal** (serveur doit rester actif) :

```bash
cd C:\Users\PPZ\NOVA-SERVER
python register_webhook.py
```

**Ce qui se passe** :
```
1. Script appelle Microsoft Graph API
   POST /subscriptions

2. Microsoft VALIDE immédiatement
   GET https://nova-rondot.itspirit.ovh/api/webhooks/notification?validationToken=...

3. Endpoint /webhooks/notification répond avec le token
   Response: validationToken (text/plain)

4. Microsoft confirme subscription
   Retourne subscription ID + expiration

5. Script sauvegarde dans webhooks.db
```

**Logs attendus dans le serveur principal** :
```
[INFO] 📞 Webhook validation request received
[INFO] Webhook subscription created: 12345678-abcd-...
```

**Output du script** :
```
================================================================================
REGISTRATION WEBHOOK MICROSOFT GRAPH
================================================================================

Resource: me/mailFolders('Inbox')/messages
Change Type: created
Notification URL: https://nova-rondot.itspirit.ovh/api/webhooks/notification
Client State: NOVA_WEBHO...

[INFO] Creating subscription...

[OK] Webhook registered successfully!

Subscription ID: 12345678-abcd-1234-5678-123456789abc
Resource: me/mailFolders('Inbox')/messages
Change Type: created
Expiration: 2026-02-16T13:00:00.0000000Z

================================================================================
NEXT STEPS
================================================================================

1. The webhook is now active
2. New emails will be processed automatically
3. Subscription expires in 3 days

To renew before expiration:
  python renew_webhook.py
```

---

### Étape 4 : Tester le Webhook

**Envoyer un email test** à la boîte mail configurée.

**Logs serveur attendus** :
```
[INFO] 📬 Webhook notification received
[INFO] 🔄 Processing notification: created on Users/.../Messages/AAMk...
[INFO] 📧 New email detected: AAMk...abc123
[INFO] 🤖 Auto-processing email: AAMk...abc123
[INFO] 📧 Email: Test devis from client@example.com
[INFO] ✅ Quote request detected, starting full analysis...
[INFO] 💰 Calcul pricing pour 3 produits...
[INFO] ⚡ Phase 5 - Pricing: 450ms
[INFO] 💾 Analysis persisted to DB for AAMk...abc123
[INFO] ✅ Auto-processing completed for AAMk...abc123
```

**Vérifier dans l'interface** :
1. Accéder http://localhost:8001/ (ou https://nova-rondot.itspirit.ovh/)
2. Charger boîte de réception
3. L'email test doit avoir le bouton **"Synthèse"** (déjà traité)
4. Clic "Synthèse" → Affichage instantané

---

## 🔄 Renouvellement Automatique

Le webhook **expire après 3 jours**. Il faut le renouveler avant expiration.

### Option A : Renouvellement Manuel

```bash
cd C:\Users\PPZ\NOVA-SERVER
python renew_webhook.py
```

**Output** :
```
================================================================================
RENOUVELLEMENT WEBHOOKS MICROSOFT GRAPH
================================================================================

[INFO] Checking for subscriptions to renew...
[INFO] Found 1 subscription(s) to renew

Renewing: 12345678-abcd-1234-5678-123456789abc
  Current expiration: 2026-02-16T13:00:00Z
  [OK] Renewed successfully
  New expiration: 2026-02-19T13:00:00Z
```

---

### Option B : Renouvellement Automatique (Recommandé)

**Windows Task Scheduler** :

1. Ouvrir "Task Scheduler" (Planificateur de tâches)
2. Actions → Create Basic Task
3. Nom : "NOVA Webhook Renewal"
4. Description : "Renouvelle webhook Microsoft Graph tous les jours"
5. Trigger : **Daily** at **09:00**
6. Action : **Start a program**
   - Program : `python`
   - Arguments : `renew_webhook.py`
   - Start in : `C:\Users\PPZ\NOVA-SERVER`
7. Finish → Propriétés → Cocher "Run whether user is logged on or not"

---

**Linux/Mac Cron** :

```bash
crontab -e

# Ajouter cette ligne (exécute tous les jours à 09:00)
0 9 * * * cd /path/to/NOVA-SERVER && python renew_webhook.py
```

---

## 📊 Monitoring & Debug

### Lister les Webhooks Actifs

**Via API** :
```bash
curl http://localhost:8001/api/webhooks/subscriptions
```

**Réponse** :
```json
{
  "count": 1,
  "subscriptions": [
    {
      "id": "12345678-abcd-1234-5678-123456789abc",
      "resource": "me/mailFolders('Inbox')/messages",
      "change_type": "created",
      "expiration_datetime": "2026-02-16T13:00:00Z",
      "client_state": "NOVA_WEBHOOK_SECRET_2026..."
    }
  ]
}
```

---

### Vérifier Subscriptions à Renouveler

**Via API** :
```bash
curl http://localhost:8001/api/webhooks/subscriptions/to-renew
```

**Réponse** :
```json
{
  "count": 0,  // Si 0, aucun renouvellement nécessaire
  "subscriptions": []
}
```

---

### Renouveler via API

```bash
curl -X POST http://localhost:8001/api/webhooks/subscriptions/renew/12345678-abcd-...
```

---

### Supprimer un Webhook

```bash
curl -X DELETE http://localhost:8001/api/webhooks/subscriptions/12345678-abcd-...
```

---

## ⚠️ Troubleshooting

### Erreur : "Failed to create subscription"

**Causes possibles** :

1. **URL pas HTTPS** :
   ```
   Error: notificationUrl must use HTTPS
   ```
   → Vérifier WEBHOOK_NOTIFICATION_URL commence par `https://`

2. **URL non accessible** :
   ```
   Error: Failed to validate notificationUrl
   ```
   → Microsoft ne peut pas joindre votre serveur
   → Vérifier firewall/reverse proxy

3. **Permissions manquantes** :
   ```
   Error: Insufficient privileges
   ```
   → Ajouter Mail.Read dans Azure AD permissions
   → Admin consent requis

4. **Token expiré** :
   ```
   Error: Access token has expired
   ```
   → Vérifier GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID dans .env

---

### Webhook ne Reçoit Pas de Notifications

**1. Vérifier webhook actif** :
```bash
curl http://localhost:8001/api/webhooks/subscriptions
```

**2. Vérifier logs serveur** :
```bash
tail -f nova.log | grep webhook
```

**3. Envoyer email test** :
- Envoyer depuis un compte externe
- Pas depuis le compte configuré (auto-envoi peut être filtré)

**4. Vérifier endpoint accessible** :
```bash
curl https://nova-rondot.itspirit.ovh/api/webhooks/notification
```
→ Doit retourner 405 Method Not Allowed (normal, GET pas supporté)

---

### Webhook Expire Trop Vite

**Normal** : Microsoft limite les webhooks mailbox à 3 jours maximum.

**Solution** : Renouvellement automatique quotidien (Task Scheduler/Cron)

---

## 📈 Métriques & Logs

### Logs Importants

**Validation initiale** :
```
[INFO] 📞 Webhook validation request received
```

**Notification reçue** :
```
[INFO] 📬 Webhook notification received: {...}
[INFO] 🔄 Processing notification: created on Users/.../Messages/...
```

**Traitement automatique** :
```
[INFO] 📧 New email detected: AAMk...abc123
[INFO] 🤖 Auto-processing email: AAMk...abc123
[INFO] ✅ Quote request detected
[INFO] 💰 Calcul pricing pour X produits...
[INFO] ✅ Auto-processing completed
[INFO] 💾 Analysis persisted to DB
```

**Renouvellement** :
```
[INFO] Renewing subscription: 12345678-abcd-...
[INFO] [OK] Renewed successfully
```

---

### Base de Données

**Fichiers SQLite** :
- `webhooks.db` - Subscriptions actives
- `email_analysis.db` - Analyses emails

**Consulter subscriptions** :
```bash
sqlite3 webhooks.db "SELECT id, expiration_datetime, status FROM subscriptions"
```

**Consulter analyses automatiques** :
```bash
sqlite3 email_analysis.db "SELECT email_id, subject, analyzed_at FROM email_analysis ORDER BY analyzed_at DESC LIMIT 10"
```

---

## ✅ Checklist Configuration

- [ ] Variables .env configurées (WEBHOOK_NOTIFICATION_URL, WEBHOOK_CLIENT_STATE)
- [ ] Serveur démarré (`python main.py`)
- [ ] Webhook enregistré (`python register_webhook.py`)
- [ ] Logs montrent "Webhook validation request received"
- [ ] Subscription ID retournée
- [ ] Email test envoyé
- [ ] Logs montrent "Auto-processing email"
- [ ] Interface affiche bouton "Synthèse"
- [ ] Renouvellement automatique configuré (Task Scheduler/Cron)

---

## 🎯 Résumé

**Avant Webhook** :
- ❌ Traitement au moment du clic "Traiter"
- ❌ Attente 2-5s à chaque fois
- ❌ Emails pas traités avant connexion

**Avec Webhook** :
- ✅ Traitement automatique dès arrivée email
- ✅ Affichage instantané (< 50ms)
- ✅ Emails déjà traités avant connexion

**Gain** : **100% automatique** - Aucun clic nécessaire

---

**Une fois configuré, les nouveaux emails seront traités automatiquement en arrière-plan !**
