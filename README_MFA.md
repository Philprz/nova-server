# NOVA MFA/2FA - Documentation Complète

## Vue d'ensemble

Implémentation complète d'authentification à deux facteurs (2FA) pour NOVA avec :

- **TOTP** (Time-based One-Time Password) compatible Google Authenticator, Microsoft Authenticator, Authy
- **Fallback SMS** via OVH SMS (priorité) ou Twilio
- **Recovery codes** (codes de secours one-time)
- **Anti-bruteforce** avec rate limiting et verrouillage temporaire
- **Journalisation structurée** JSON pour audit
- **Protection des routes sensibles** via JWT mfa_ok=true

---

## Architecture

### Flux d'authentification complet

```
1. Login (email + password) → JWT mfa_pending (TTL 5 min)
                                      ↓
2. Vérification 2FA:
   - TOTP (défaut)          →  /mfa/verify/totp
   - SMS (fallback)         →  /mfa/sms/send + /mfa/verify/sms
   - Recovery code (secours) →  /mfa/verify/recovery
                                      ↓
3. Si succès → JWT final (mfa_ok=true, TTL 60 min)
                                      ↓
4. Accès routes sensibles (require_mfa_completed)
```

### Structure des fichiers

```
NOVA-SERVER-TEST/
├── core/
│   ├── security.py         # JWT avec stages MFA (pending/completed)
│   ├── rate_limit.py       # Rate limiting (Redis ou in-memory)
│   └── logging.py          # Logs structurés JSON
├── services/
│   ├── mfa_totp.py         # Service TOTP (pyotp)
│   ├── recovery_codes.py   # Génération/vérification recovery codes
│   └── mfa_sms.py          # Service OTP SMS
├── providers/
│   └── sms/
│       ├── base.py         # Interface SMSProvider
│       ├── ovh_sms.py      # Implémentation OVH SMS (priorité)
│       ├── twilio_sms.py   # Implémentation Twilio (fallback)
│       └── __init__.py
├── models/
│   └── user.py             # Modèle User avec champs MFA
├── routes/
│   └── mfa.py              # Endpoints API MFA
├── alembic/versions/
│   └── 20251016_102726_add_mfa_fields.py  # Migration
├── tests/
│   ├── test_mfa_services.py
│   └── test_mfa_api.py
├── README_MFA.md           # Ce fichier
└── EXAMPLES_MFA.md         # Exemples cURL/Postman
```

---

## Installation

### 1. Dépendances

```bash
pip install -r requirements.txt
```

Nouvelles dépendances ajoutées :
- `pyotp==2.9.0` - TOTP (RFC 6238)
- `qrcode[pil]==7.4.2` - Génération QR codes
- `bcrypt==4.1.2` - Hash recovery codes
- `phonenumbers==8.13.26` - Validation numéros téléphone
- `passlib[bcrypt]==1.7.4` - Utilitaires hash
- `python-jose[cryptography]==3.3.0` - JWT
- `ovh==1.1.0` - API OVH SMS
- `twilio==8.11.0` - API Twilio SMS
- `redis==5.0.1` - Stockage OTP/rate limiting
- `Pillow==10.1.0` - Traitement images QR

### 2. Configuration environnement

Ajouter au fichier `.env` :

```bash
# === JWT Configuration ===
JWT_SECRET_KEY=VOTRE_CLE_SECRETE_LONGUE_ET_ALEATOIRE_256_BITS

# === MFA Rate Limiting ===
MFA_RATE_LIMIT_WINDOW=60       # Fenêtre en secondes
MFA_RATE_LIMIT_MAX=10          # Max requêtes par fenêtre

# === OVH SMS (prioritaire) ===
OVH_APP_KEY=votre_app_key
OVH_APP_SECRET=votre_app_secret
OVH_CONSUMER_KEY=votre_consumer_key
OVH_SMS_ACCOUNT=sms-ab12345-1
OVH_SMS_SENDER=ITSPIRIT       # Max 11 caractères

# === Twilio SMS (optionnel, fallback) ===
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM=+15551234567

# === Redis (optionnel mais recommandé pour production) ===
REDIS_URL=redis://localhost:6379/1

# === Database ===
DATABASE_URL=postgresql+psycopg2://nova_user:password@localhost:5432/nova_mcp
```

### 3. Migration base de données

```bash
# Appliquer la migration
alembic upgrade head

# Vérifier
alembic current
```

La migration crée :
- Table `users` avec tous les champs MFA
- Enum `mfa_backup_method_enum` (none, sms)
- Index optimisés pour requêtes MFA

---

## Configuration OVH SMS

### Prérequis

1. **Compte OVH** avec service SMS activé
2. **Application API OVH** : [https://eu.api.ovh.com/createApp/](https://eu.api.ovh.com/createApp/)
   - Obtenir `APP_KEY` et `APP_SECRET`

3. **Consumer Key** avec droits SMS :
   ```bash
   # Utiliser le script Python OVH pour générer le Consumer Key
   # ou via l'API OVH Manager
   ```

4. **Compte SMS** : Identifier le nom du compte (ex: `sms-ab12345-1`)
   ```bash
   GET /sms
   ```

### Test OVH SMS

```python
from providers.sms.ovh_sms import OVHSMSProvider

provider = OVHSMSProvider()
result = await provider.send_sms("+33612345678", "Test NOVA MFA")
print(result.success, result.message_id)
```

---

## Configuration Twilio SMS (optionnel)

### Prérequis

1. Compte Twilio : [https://www.twilio.com/console](https://www.twilio.com/console)
2. Numéro Twilio actif (SMS-capable)

### Test Twilio SMS

```python
from providers.sms.twilio_sms import TwilioSMSProvider

provider = TwilioSMSProvider()
result = await provider.send_sms("+33612345678", "Test NOVA MFA")
print(result.success, result.message_id)
```

---

## Utilisation API

### 1. Enrôlement TOTP (première activation)

#### a) Démarrer l'enrôlement

```bash
POST /api/mfa/totp/enroll/start
Authorization: Bearer <access_token>
```

**Réponse :**
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/IT%20SPIRIT%20NOVA:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=IT%20SPIRIT%20NOVA",
  "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "message": "Scan the QR code with your authenticator app, then verify with a code"
}
```

**Action utilisateur :**
1. Scanner le QR code avec Google Authenticator / Microsoft Authenticator
2. OU saisir manuellement le `secret` dans l'app

#### b) Vérifier le code TOTP

```bash
POST /api/mfa/totp/enroll/verify
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "code": "123456"
}
```

**Réponse (succès) :**
```json
{
  "success": true,
  "recovery_codes": [
    "AB12-CD34",
    "EF56-GH78",
    "..."
  ],
  "message": "TOTP activated! Save your recovery codes in a safe place. They will not be shown again."
}
```

**IMPORTANT:** Les recovery codes sont affichés **UNE SEULE FOIS**. L'utilisateur doit les sauvegarder.

---

### 2. Authentification avec MFA (login)

#### a) Login classique (1er facteur)

```bash
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**Réponse :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "mfa_required": true,
  "mfa_stage": "pending"
}
```

Le token retourné est un **mfa_pending** (TTL 5 min). Il faut maintenant vérifier le 2ème facteur.

#### b) Vérifier TOTP (2ème facteur)

```bash
POST /api/mfa/verify/totp
Authorization: Bearer <mfa_pending_token>
Content-Type: application/json

{
  "code": "654321"
}
```

**Réponse (succès) :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "mfa_ok": true
}
```

Ce token final (mfa_ok=true) permet d'accéder aux routes protégées.

---

### 3. Fallback SMS

#### a) Envoyer OTP SMS

```bash
POST /api/mfa/sms/send
Authorization: Bearer <mfa_pending_token>
```

**Pré-requis:** Numéro de téléphone vérifié (voir section "Vérification téléphone").

**Réponse :**
```json
{
  "success": true,
  "message_id": "123456789",
  "expires_at": "2025-10-16T10:35:00Z",
  "message": "SMS sent to ***5678. Code valid for 5 minutes."
}
```

**Rate limit:** 1/min, 3/heure.

#### b) Vérifier OTP SMS

```bash
POST /api/mfa/verify/sms
Authorization: Bearer <mfa_pending_token>
Content-Type: application/json

{
  "code": "700112"
}
```

**Réponse (succès) :**
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "mfa_ok": true
}
```

---

### 4. Recovery codes (secours)

#### a) Utiliser un recovery code

```bash
POST /api/mfa/verify/recovery
Authorization: Bearer <mfa_pending_token>
Content-Type: application/json

{
  "code": "AB12-CD34"
}
```

**Réponse (succès) :**
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "mfa_ok": true
}
```

**Note:** Le recovery code est **consommé** (one-time). Il ne reste que 9 codes.

#### b) Régénérer les recovery codes

```bash
POST /api/mfa/recovery/regenerate
Authorization: Bearer <access_token>
```

**Réponse :**
```json
{
  "success": true,
  "recovery_codes": ["AB12-CD34", "EF56-GH78", ...],
  "message": "Save these codes in a safe place. They will not be shown again."
}
```

**Rate limit:** 3/jour.

#### c) Lister les recovery codes (nombre)

```bash
GET /api/mfa/recovery/list
Authorization: Bearer <access_token>
```

**Réponse :**
```json
{
  "count": 7,
  "message": "You have 7 recovery codes remaining. Codes cannot be displayed (hashed)."
}
```

---

### 5. Configuration téléphone

#### a) Définir le numéro de téléphone

```bash
POST /api/mfa/phone/set
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "phone": "+33612345678"
}
```

**Réponse :**
```json
{
  "success": true,
  "message": "Verification code sent to +33612345678. Use /mfa/phone/verify to confirm.",
  "expires_at": "2025-10-16T10:35:00Z"
}
```

Un OTP SMS est envoyé au numéro.

#### b) Vérifier le numéro

```bash
POST /api/mfa/phone/verify
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "code": "123456"
}
```

**Réponse (succès) :**
```json
{
  "success": true,
  "message": "Phone number +33612345678 verified successfully"
}
```

#### c) Configurer la méthode de secours

```bash
POST /api/mfa/backup/set
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "method": "sms"
}
```

Valeurs possibles : `"sms"` ou `"none"`.

**Réponse :**
```json
{
  "success": true,
  "backup_method": "sms",
  "message": "Backup method set to: sms"
}
```

---

### 6. Statut MFA

```bash
GET /api/mfa/status
Authorization: Bearer <access_token>
```

**Réponse :**
```json
{
  "user_id": 42,
  "email": "user@example.com",
  "totp_enabled": true,
  "totp_enrolled_at": "2025-10-16T10:00:00Z",
  "phone_number": "+33612345678",
  "phone_verified": true,
  "backup_method": "sms",
  "recovery_codes_count": 7,
  "mfa_enforced": true,
  "is_locked": false
}
```

---

## Sécurité

### Anti-bruteforce

- **Rate limiting** sur tous les endpoints MFA :
  - Vérification TOTP/SMS : 10 requêtes/min par IP
  - Envoi SMS : 1/min, 3/heure
  - Recovery codes : 5/min

- **Verrouillage compte** :
  - 10 échecs MFA → verrouillage 15 minutes
  - Logged avec user_id, IP, timestamp

### Journalisation

Tous les événements MFA sont journalisés au format JSON :

```json
{
  "timestamp": "2025-10-16T10:30:00.000Z",
  "level": "INFO",
  "logger": "nova.mfa",
  "message": "MFA event: totp_verify",
  "user_id": 42,
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0...",
  "mfa_event": "totp_verify",
  "mfa_method": "totp",
  "result": "success"
}
```

Fichier: `logs/mfa.log`

Événements tracés :
- `totp_enroll_start`, `totp_enroll_verify`
- `totp_verify`, `sms_verify`, `recovery_verify`
- `sms_otp_sent`, `phone_set`, `phone_verify`
- `rate_limit_exceeded`, `mfa_account_locked`

### Bonnes pratiques

1. **Secrets TOTP** : Chiffrer en DB (AES-256) en production
2. **JWT_SECRET_KEY** : Utiliser une clé >= 256 bits, aléatoire
3. **Redis** : Utiliser Redis en production pour rate limiting distribué
4. **HTTPS** : Obligatoire pour éviter interception des codes
5. **Rotation secrets** : Permettre à l'utilisateur de régénérer TOTP secret si compromis

---

## Tests

### Lancer les tests

```bash
# Tests services (unitaires)
pytest tests/test_mfa_services.py -v

# Tests API (intégration)
pytest tests/test_mfa_api.py -v

# Tous les tests MFA avec couverture
pytest tests/test_mfa*.py --cov=services --cov=core --cov=routes.mfa --cov-report=term-missing
```

### Couverture attendue

- Services (mfa_totp, recovery_codes, mfa_sms) : >90%
- Core (security, rate_limit, logging) : >85%
- Routes (mfa.py) : >80%

---

## Commandes rapides

### Démarrage complet

```bash
# 1. Installer dépendances
pip install -r requirements.txt

# 2. Appliquer migrations
alembic upgrade head

# 3. Lancer l'API
python main.py

# 4. Tester (autre terminal)
pytest tests/test_mfa*.py -v
```

### Endpoints principaux

```
POST   /api/mfa/totp/enroll/start          # Enrôler TOTP
POST   /api/mfa/totp/enroll/verify         # Vérifier enrôlement
POST   /api/mfa/verify/totp                # Vérifier code TOTP (login)
POST   /api/mfa/verify/sms                 # Vérifier code SMS (login)
POST   /api/mfa/verify/recovery            # Utiliser recovery code
POST   /api/mfa/sms/send                   # Envoyer OTP SMS
POST   /api/mfa/phone/set                  # Configurer téléphone
POST   /api/mfa/phone/verify               # Vérifier téléphone
POST   /api/mfa/recovery/regenerate        # Régénérer recovery codes
GET    /api/mfa/recovery/list              # Lister recovery codes
POST   /api/mfa/backup/set                 # Méthode de secours
GET    /api/mfa/status                     # Statut MFA utilisateur
```

Documentation interactive : `http://localhost:8200/docs`

---

## Troubleshooting

### OVH SMS : "Insufficient credit"

- Vérifier crédit OVH : `GET /sms/{serviceName}` → `creditsLeft`
- Recharger via OVH Manager

### Twilio SMS : "Unverified number"

- En mode trial, Twilio ne peut envoyer qu'à des numéros vérifiés
- Passer en mode production ou vérifier le numéro test

### Redis : "Connection refused"

- Vérifier que Redis tourne : `redis-cli ping` → `PONG`
- Fallback automatique : in-memory si Redis indisponible

### TOTP : "Invalid code" alors que c'est le bon

- **Clock drift** : vérifier l'heure du serveur (NTP)
- Tolérance : `valid_window=1` (±30s par défaut)

### Migration Alembic : "Target database is not up to date"

```bash
# Vérifier état
alembic current

# Réinitialiser (DEV ONLY!)
alembic downgrade base
alembic upgrade head
```

---

## Checklist sécurité (DoD)

- [x] TOTP activable/désactivable avec QR code
- [x] Fallback SMS fonctionnel (OVH prioritaire)
- [x] Recovery codes générés/consommés/régénérables
- [x] JWT mfa_pending (5 min) → mfa_ok=true (60 min)
- [x] Rate limiting sur tous les endpoints critiques
- [x] Verrouillage après 10 échecs (15 min)
- [x] Journalisation structurée JSON sans secrets
- [x] Tests > 90% sur services, > 80% sur API
- [x] Messages d'erreur sobres (pas de leak d'info)
- [x] Statuts HTTP corrects (401, 403, 429, 500)
- [x] Documentation README + exemples cURL
- [x] Migration Alembic testée et réversible

---

## Support & Contribution

- **Issues** : Reporter les bugs via GitHub Issues
- **Questions** : Contact IT SPIRIT support
- **Améliorations** : Pull requests bienvenues

---

## Licence

Propriétaire IT SPIRIT © 2025

---

**Version:** 1.0.0
**Date:** 2025-10-16
**Auteur:** Équipe NOVA
