# NOVA MFA - Quickstart

Guide express pour tester le système MFA en 5 minutes.

---

## Installation Express (Windows)

```powershell
# 1. Activer l'environnement virtuel
.\.venv\Scripts\Activate

# 2. Installer les nouvelles dépendances
pip install pyotp==2.9.0 qrcode[pil]==7.4.2 bcrypt==4.1.2 phonenumbers==8.13.26 passlib[bcrypt]==1.7.4 python-jose[cryptography]==3.3.0 ovh==1.1.0 twilio==8.11.0 redis==5.0.1 Pillow==10.1.0

# 3. Ajouter la clé JWT au .env
echo JWT_SECRET_KEY=VOTRE_CLE_SECRETE_TRES_LONGUE_ET_ALEATOIRE_AU_MOINS_256_BITS >> .env

# 4. Appliquer la migration
alembic upgrade head

# 5. Vérifier la migration
alembic current

# 6. Lancer l'API
python main.py
```

---

## Test Rapide (Mock SMS - sans config OVH/Twilio)

### 1. Créer un utilisateur de test (Python)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.user import User
from core.security import get_password_hash
from datetime import datetime, timezone
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://nova_user:NovaUser_31021225@localhost:5432/nova_mcp")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

db = SessionLocal()

user = User(
    email="test@itspirit.com",
    username="testmfa",
    hashed_password=get_password_hash("password123"),
    full_name="Test MFA User",
    is_active=True,
    is_superuser=False,
    mfa_enforced=True
)

db.add(user)
db.commit()
print(f"User created: {user.email} (ID: {user.id})")
db.close()
```

### 2. Générer un token d'accès

```python
from core.security import create_final_access_token

# Utiliser l'ID du user créé ci-dessus
user_id = 1
email = "test@itspirit.com"

token = create_final_access_token(user_id, email, False)
print(f"Access Token: {token}")
```

### 3. Enrôler TOTP

```bash
# Remplacer YOUR_TOKEN par le token généré
curl -X POST "http://localhost:8200/api/mfa/totp/enroll/start" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  | jq
```

Copier le `qr_code` (base64) et l'afficher dans un navigateur :

```html
<html>
<body>
  <h1>Scan avec Google Authenticator</h1>
  <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..." />
</body>
</html>
```

Scanner avec Google Authenticator, puis vérifier :

```bash
# Obtenir code depuis l'app (ex: 123456)
curl -X POST "http://localhost:8200/api/mfa/totp/enroll/verify" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}' \
  | jq
```

**Sauvegarder les recovery codes affichés !**

### 4. Tester login MFA

```python
# Générer un token mfa_pending
from core.security import create_mfa_pending_token

token_pending = create_mfa_pending_token(1, "test@itspirit.com")
print(f"MFA Pending Token: {token_pending}")
```

```bash
# Vérifier TOTP avec code actuel
curl -X POST "http://localhost:8200/api/mfa/verify/totp" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"654321"}' \
  | jq
```

**Succès !** Vous obtenez un token final avec `mfa_ok: true`.

---

## Test SMS (Mock - dev)

Le SMS mock fonctionne automatiquement sans config OVH/Twilio.

### 1. Configurer téléphone

```bash
curl -X POST "http://localhost:8200/api/mfa/phone/set" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+33612345678"}' \
  | jq
```

### 2. Vérifier téléphone

Le mock affiche le code OTP dans les logs serveur. Chercher :

```
[MockSMS] Sent to +33612345678: Votre code... (ID: mock_...)
```

Copier le code (6 chiffres) et vérifier :

```bash
curl -X POST "http://localhost:8200/api/mfa/phone/verify" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}' \
  | jq
```

### 3. Tester fallback SMS (login)

```bash
# Envoyer OTP
curl -X POST "http://localhost:8200/api/mfa/sms/send" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN"

# Récupérer code dans logs, puis vérifier
curl -X POST "http://localhost:8200/api/mfa/verify/sms" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"700112"}' \
  | jq
```

---

## Lancer les tests

```bash
# Tests unitaires services
pytest tests/test_mfa_services.py -v

# Tests intégration API
pytest tests/test_mfa_api.py -v

# Tous les tests avec couverture
pytest tests/test_mfa*.py --cov=services --cov=core --cov=routes.mfa --cov-report=html

# Ouvrir rapport couverture
start htmlcov/index.html
```

---

## Commandes utiles

### Vérifier statut MFA

```bash
curl -X GET "http://localhost:8200/api/mfa/status" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  | jq
```

### Régénérer recovery codes

```bash
curl -X POST "http://localhost:8200/api/mfa/recovery/regenerate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  | jq
```

### Voir documentation interactive

Ouvrir navigateur : `http://localhost:8200/docs`

Tester tous les endpoints MFA avec Swagger UI.

---

## Troubleshooting

### Migration Alembic échoue

```bash
# Vérifier état actuel
alembic current

# Downgrade (DEV ONLY!)
alembic downgrade -1

# Re-upgrade
alembic upgrade head
```

### Tests échouent : "No module named 'pyotp'"

```bash
pip install -r requirements.txt
```

### API ne démarre pas : "Address already in use"

```bash
# Trouver et tuer le processus sur port 8200
netstat -ano | findstr :8200
taskkill /PID <PID> /F
```

### JWT "Could not validate credentials"

Vérifier que `JWT_SECRET_KEY` est défini dans `.env` :

```bash
echo $env:JWT_SECRET_KEY
```

Si vide :

```powershell
$random = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object {[char]$_})
Add-Content .env "JWT_SECRET_KEY=$random"
```

---

## Configuration Production OVH SMS

Si vous voulez tester avec de vrais SMS :

```bash
# Ajouter au .env
OVH_APP_KEY=votre_app_key
OVH_APP_SECRET=votre_app_secret
OVH_CONSUMER_KEY=votre_consumer_key
OVH_SMS_ACCOUNT=sms-ab12345-1
OVH_SMS_SENDER=ITSPIRIT
```

Redémarrer l'API. Le système utilisera automatiquement OVH au lieu du mock.

---

## Documentation complète

- **README_MFA.md** : Documentation technique complète
- **EXAMPLES_MFA.md** : Exemples cURL & Postman
- **Swagger UI** : http://localhost:8200/docs

---

**Durée estimée : 10-15 minutes**

Si problème, consulter `logs/mfa.log` ou `nova.log`.
