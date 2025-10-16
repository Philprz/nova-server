# NOVA MFA - Exemples cURL & Postman

Ce document contient des exemples pratiques pour tester tous les endpoints MFA de NOVA.

---

## Variables d'environnement (Postman)

Créer ces variables dans votre environnement Postman :

```
BASE_URL = http://localhost:8200
ACCESS_TOKEN = (à remplir après login)
MFA_PENDING_TOKEN = (à remplir après login)
USER_EMAIL = user@example.com
```

---

## 1. Enrôlement TOTP

### 1.1 Démarrer l'enrôlement

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/totp/enroll/start" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/totp/enroll/start
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
```

**Réponse attendue (200) :**
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/IT%20SPIRIT%20NOVA:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=IT%20SPIRIT%20NOVA",
  "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "message": "Scan the QR code with your authenticator app, then verify with a code"
}
```

**Action :**
1. Copier le QR code (base64)
2. L'afficher dans un navigateur : `<img src="data:image/png;base64,..." />`
3. Scanner avec Google Authenticator

### 1.2 Vérifier le code TOTP (finaliser enrôlement)

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/totp/enroll/verify" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "123456"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/totp/enroll/verify
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "code": "123456"
}
```

**Réponse attendue (200) :**
```json
{
  "success": true,
  "recovery_codes": [
    "AB12-CD34",
    "EF56-GH78",
    "IJ90-KL12",
    "MN34-OP56",
    "QR78-ST90",
    "UV12-WX34",
    "YZ56-AB78",
    "CD90-EF12",
    "GH34-IJ56",
    "KL78-MN90"
  ],
  "message": "TOTP activated! Save your recovery codes in a safe place. They will not be shown again."
}
```

**IMPORTANT:** Sauvegarder les recovery codes immédiatement !

---

## 2. Login avec MFA

### 2.1 Login (1er facteur)

**Note:** Cet endpoint doit être créé dans `/api/auth/login` (hors scope MFA, mais nécessaire pour le workflow).

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }'
```

**Réponse attendue (200) :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MiIsImVtYWlsIjoidXNlckBleGFtcGxlLmNvbSIsInR5cGUiOiJtZmFfcGVuZGluZyIsIm1mYV9zdGFnZSI6InBlbmRpbmciLCJtZmFfb2siOmZhbHNlLCJleHAiOjE3MzE3NDk5MDAsImlhdCI6MTczMTc0OTYwMH0...",
  "token_type": "bearer",
  "mfa_required": true,
  "mfa_stage": "pending"
}
```

**Action:** Sauvegarder le `access_token` dans `MFA_PENDING_TOKEN`.

### 2.2 Vérifier TOTP (2ème facteur)

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/verify/totp" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "654321"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/verify/totp
Headers:
  Authorization: Bearer {{MFA_PENDING_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "code": "654321"
}
```

**Réponse attendue (200) :**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MiIsImVtYWlsIjoidXNlckBleGFtcGxlLmNvbSIsImlzX3N1cGVydXNlciI6ZmFsc2UsInR5cGUiOiJhY2Nlc3MiLCJtZmFfc3RhZ2UiOiJjb21wbGV0ZWQiLCJtZmFfb2siOnRydWUsImV4cCI6MTczMTc1MzUwMCwiaWF0IjoxNzMxNzQ5OTAwfQ...",
  "token_type": "bearer",
  "mfa_ok": true
}
```

**Action:** Utiliser ce token pour accéder aux routes protégées.

---

## 3. Fallback SMS

### 3.1 Envoyer OTP SMS

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/sms/send" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json"
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/sms/send
Headers:
  Authorization: Bearer {{MFA_PENDING_TOKEN}}
```

**Réponse attendue (200) :**
```json
{
  "success": true,
  "message_id": "123456789",
  "expires_at": "2025-10-16T10:35:00Z",
  "message": "SMS sent to ***5678. Code valid for 5 minutes."
}
```

**Rate limit:** 1/min, 3/heure.

### 3.2 Vérifier OTP SMS

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/verify/sms" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "700112"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/verify/sms
Headers:
  Authorization: Bearer {{MFA_PENDING_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "code": "700112"
}
```

**Réponse attendue (200) :**
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "mfa_ok": true
}
```

---

## 4. Recovery Codes

### 4.1 Utiliser un recovery code

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/verify/recovery" \
  -H "Authorization: Bearer YOUR_MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "AB12-CD34"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/verify/recovery
Headers:
  Authorization: Bearer {{MFA_PENDING_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "code": "AB12-CD34"
}
```

**Réponse attendue (200) :**
```json
{
  "access_token": "...",
  "token_type": "bearer",
  "mfa_ok": true
}
```

**Note:** Le recovery code est consommé (one-time).

### 4.2 Régénérer recovery codes

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/recovery/regenerate" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/recovery/regenerate
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
```

**Réponse attendue (200) :**
```json
{
  "success": true,
  "recovery_codes": [
    "AB12-CD34",
    "EF56-GH78",
    "..."
  ],
  "message": "Save these codes in a safe place. They will not be shown again."
}
```

### 4.3 Lister recovery codes (compteur)

**cURL :**
```bash
curl -X GET "http://localhost:8200/api/mfa/recovery/list" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Postman :**
```
GET {{BASE_URL}}/api/mfa/recovery/list
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
```

**Réponse attendue (200) :**
```json
{
  "count": 7,
  "message": "You have 7 recovery codes remaining. Codes cannot be displayed (hashed)."
}
```

---

## 5. Configuration Téléphone

### 5.1 Définir le numéro

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/phone/set" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+33612345678"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/phone/set
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "phone": "+33612345678"
}
```

**Réponse attendue (200) :**
```json
{
  "success": true,
  "message": "Verification code sent to +33612345678. Use /mfa/phone/verify to confirm.",
  "expires_at": "2025-10-16T10:35:00Z"
}
```

### 5.2 Vérifier le numéro

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/phone/verify" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "123456"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/phone/verify
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "code": "123456"
}
```

**Réponse attendue (200) :**
```json
{
  "success": true,
  "message": "Phone number +33612345678 verified successfully"
}
```

### 5.3 Configurer méthode de secours

**cURL :**
```bash
curl -X POST "http://localhost:8200/api/mfa/backup/set" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "sms"
  }'
```

**Postman :**
```
POST {{BASE_URL}}/api/mfa/backup/set
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
  Content-Type: application/json
Body (raw JSON):
{
  "method": "sms"
}
```

**Valeurs possibles:** `"sms"` ou `"none"`.

**Réponse attendue (200) :**
```json
{
  "success": true,
  "backup_method": "sms",
  "message": "Backup method set to: sms"
}
```

---

## 6. Statut MFA

**cURL :**
```bash
curl -X GET "http://localhost:8200/api/mfa/status" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Postman :**
```
GET {{BASE_URL}}/api/mfa/status
Headers:
  Authorization: Bearer {{ACCESS_TOKEN}}
```

**Réponse attendue (200) :**
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

## 7. Scénarios complets

### Scénario 1 : Premier enrôlement TOTP

```bash
# 1. Login (obtenir access_token complet, simulé ici)
ACCESS_TOKEN="eyJhbG..."

# 2. Démarrer enrôlement
curl -X POST "http://localhost:8200/api/mfa/totp/enroll/start" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | jq -r '.qr_code' > qr.txt

# 3. Afficher QR dans navigateur
# (copier contenu de qr.txt dans <img src="..." />)

# 4. Scanner avec Google Authenticator

# 5. Obtenir code depuis l'app (ex: 123456)

# 6. Vérifier code
curl -X POST "http://localhost:8200/api/mfa/totp/enroll/verify" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}' \
  | jq '.recovery_codes'

# 7. Sauvegarder les recovery codes affichés!
```

### Scénario 2 : Login complet avec MFA

```bash
# 1. Login 1er facteur (simulé)
MFA_PENDING_TOKEN="eyJhbG..."

# 2. Vérifier TOTP (2ème facteur)
curl -X POST "http://localhost:8200/api/mfa/verify/totp" \
  -H "Authorization: Bearer $MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"654321"}' \
  | jq -r '.access_token'

# 3. Utiliser le token final pour accéder aux routes protégées
FINAL_TOKEN="eyJhbG..."

curl -X GET "http://localhost:8200/api/clients/sensitive-data" \
  -H "Authorization: Bearer $FINAL_TOKEN"
```

### Scénario 3 : Fallback SMS

```bash
# 1. Login 1er facteur
MFA_PENDING_TOKEN="eyJhbG..."

# 2. Envoyer OTP SMS
curl -X POST "http://localhost:8200/api/mfa/sms/send" \
  -H "Authorization: Bearer $MFA_PENDING_TOKEN"

# 3. Récupérer code SMS (ex: 700112)

# 4. Vérifier code SMS
curl -X POST "http://localhost:8200/api/mfa/verify/sms" \
  -H "Authorization: Bearer $MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"700112"}' \
  | jq -r '.access_token'
```

### Scénario 4 : Récupération avec recovery code

```bash
# 1. Login 1er facteur
MFA_PENDING_TOKEN="eyJhbG..."

# 2. Utiliser recovery code (ex: perdu le téléphone)
curl -X POST "http://localhost:8200/api/mfa/verify/recovery" \
  -H "Authorization: Bearer $MFA_PENDING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"AB12-CD34"}' \
  | jq -r '.access_token'

# 3. Régénérer nouveaux recovery codes (avec token final)
FINAL_TOKEN="eyJhbG..."

curl -X POST "http://localhost:8200/api/mfa/recovery/regenerate" \
  -H "Authorization: Bearer $FINAL_TOKEN" \
  | jq '.recovery_codes'
```

---

## 8. Collection Postman

### Importer cette collection

Créer un fichier `NOVA_MFA.postman_collection.json` :

```json
{
  "info": {
    "name": "NOVA MFA",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "1. TOTP Enrollment",
      "item": [
        {
          "name": "1.1 Start Enrollment",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"}
            ],
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/totp/enroll/start",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "totp", "enroll", "start"]
            }
          }
        },
        {
          "name": "1.2 Verify Enrollment",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"},
              {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
              "mode": "raw",
              "raw": "{\"code\": \"123456\"}"
            },
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/totp/enroll/verify",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "totp", "enroll", "verify"]
            }
          }
        }
      ]
    },
    {
      "name": "2. MFA Verification",
      "item": [
        {
          "name": "2.1 Verify TOTP",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{MFA_PENDING_TOKEN}}"},
              {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
              "mode": "raw",
              "raw": "{\"code\": \"654321\"}"
            },
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/verify/totp",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "verify", "totp"]
            }
          }
        },
        {
          "name": "2.2 Verify SMS",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{MFA_PENDING_TOKEN}}"},
              {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
              "mode": "raw",
              "raw": "{\"code\": \"700112\"}"
            },
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/verify/sms",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "verify", "sms"]
            }
          }
        },
        {
          "name": "2.3 Verify Recovery Code",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{MFA_PENDING_TOKEN}}"},
              {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
              "mode": "raw",
              "raw": "{\"code\": \"AB12-CD34\"}"
            },
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/verify/recovery",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "verify", "recovery"]
            }
          }
        }
      ]
    },
    {
      "name": "3. SMS",
      "item": [
        {
          "name": "3.1 Send SMS OTP",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{MFA_PENDING_TOKEN}}"}
            ],
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/sms/send",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "sms", "send"]
            }
          }
        }
      ]
    },
    {
      "name": "4. Phone",
      "item": [
        {
          "name": "4.1 Set Phone",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"},
              {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
              "mode": "raw",
              "raw": "{\"phone\": \"+33612345678\"}"
            },
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/phone/set",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "phone", "set"]
            }
          }
        },
        {
          "name": "4.2 Verify Phone",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"},
              {"key": "Content-Type", "value": "application/json"}
            ],
            "body": {
              "mode": "raw",
              "raw": "{\"code\": \"123456\"}"
            },
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/phone/verify",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "phone", "verify"]
            }
          }
        }
      ]
    },
    {
      "name": "5. Recovery Codes",
      "item": [
        {
          "name": "5.1 Regenerate",
          "request": {
            "method": "POST",
            "header": [
              {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"}
            ],
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/recovery/regenerate",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "recovery", "regenerate"]
            }
          }
        },
        {
          "name": "5.2 List",
          "request": {
            "method": "GET",
            "header": [
              {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"}
            ],
            "url": {
              "raw": "{{BASE_URL}}/api/mfa/recovery/list",
              "host": ["{{BASE_URL}}"],
              "path": ["api", "mfa", "recovery", "list"]
            }
          }
        }
      ]
    },
    {
      "name": "6. Status",
      "request": {
        "method": "GET",
        "header": [
          {"key": "Authorization", "value": "Bearer {{ACCESS_TOKEN}}"}
        ],
        "url": {
          "raw": "{{BASE_URL}}/api/mfa/status",
          "host": ["{{BASE_URL}}"],
          "path": ["api", "mfa", "status"]
        }
      }
    }
  ]
}
```

**Importer dans Postman :**
1. Ouvrir Postman
2. File → Import
3. Coller le JSON ci-dessus
4. Créer un environnement avec `BASE_URL`, `ACCESS_TOKEN`, `MFA_PENDING_TOKEN`

---

## 9. Codes d'erreur courants

| Code | Description | Solution |
|------|-------------|----------|
| 400 | Invalid TOTP code | Vérifier le code depuis l'app authenticator |
| 400 | TOTP not enabled | Appeler `/totp/enroll/start` d'abord |
| 401 | Unauthorized | Token manquant ou invalide |
| 403 | Forbidden (token mismatch) | Utiliser `mfa_pending` pour verify, `access_token` pour manage |
| 404 | User not found | Vérifier user_id dans le token |
| 429 | Rate limit exceeded | Attendre (Retry-After header) |
| 429 | Account locked | Attendre 15 min ou contacter admin |
| 500 | Internal server error | Vérifier logs serveur |

---

**Version:** 1.0.0
**Date:** 2025-10-16
