# Scénario de Démonstration 2FA pour les Patrons

## Préparation (5 minutes avant la démo)

### 1. Vérifier l'environnement

```bash
# Terminal 1 : Démarrer le serveur FastAPI
cd c:\Users\PPZ\NOVA-SERVER-TEST
python main.py
```

Le serveur devrait afficher :
```
INFO:     Uvicorn running on http://127.0.0.1:8200 (Press CTRL+C to quit)
```

### 2. Préparer les outils

- **Navigateur 1** : Ouvrir http://localhost:8200/docs (Swagger UI)
- **Navigateur 2** : Prêt pour afficher le QR code
- **Téléphone** : Google Authenticator ou Microsoft Authenticator installé
- **Terminal 2** : Prêt pour lancer le script de test
- **PostgreSQL** : Base de données accessible

### 3. Compte utilisateur de test

Créer un compte si nécessaire :
```sql
INSERT INTO users (
    email,
    username,
    hashed_password,
    full_name,
    is_active,
    mfa_enforced,
    is_totp_enabled
) VALUES (
    'demo@itspirit.fr',
    'demo_boss',
    -- Hash bcrypt de "Demo2024!"
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYpRZLCb1Ma',
    'Compte Démonstration',
    true,
    true,
    false
);
```

---

## PARTIE 1 : VUE D'ENSEMBLE (2 minutes)

### Message d'introduction

> "Bonjour, aujourd'hui je vais vous présenter notre système d'authentification à deux facteurs (2FA) que nous avons implémenté pour sécuriser l'accès à NOVA SERVER.
>
> Le 2FA ajoute une couche de sécurité supplémentaire : même si un mot de passe est compromis, un attaquant ne peut pas se connecter sans le deuxième facteur d'authentification."

### Afficher l'architecture (sur whiteboard ou slide)

```
┌─────────────────────────────────────────────────────────┐
│ FLUX D'AUTHENTIFICATION 2FA                              │
└─────────────────────────────────────────────────────────┘

Étape 1 : Connexion classique
┌──────────┐
│ Email    │  ──→  Validation   ──→  Token "mfa_pending"
│ Password │       (bcrypt)           (5 minutes)
└──────────┘

Étape 2 : Vérification 2FA (3 méthodes possibles)
┌──────────────────┐
│ A. TOTP          │  Google Authenticator (RECOMMANDÉ)
│ B. SMS OTP       │  Code par SMS (secours)
│ C. Recovery Code │  Codes imprimés (urgence)
└──────────────────┘
         │
         ▼
   Token "completed"
   (60 minutes)
         │
         ▼
   Accès aux ressources
```

**Points clés à mentionner** :
- 3 méthodes indépendantes (redondance)
- Conforme aux standards (RFC 6238, NIST)
- Protection anti-bruteforce
- Audit trail complet

---

## PARTIE 2 : DÉMONSTRATION PRATIQUE (15 minutes)

### Démo 1 : Configuration TOTP avec Google Authenticator (5 minutes)

#### A. Démarrer l'enrollment

**Navigateur** : Ouvrir http://localhost:8200/docs

1. Trouver l'endpoint `POST /api/mfa/totp/enroll/start`
2. Cliquer sur "Try it out"
3. Cliquer sur "Execute"

**Points à souligner pendant l'attente** :
- "L'endpoint génère un secret unique pour cet utilisateur"
- "Le secret est encodé en base32 selon le standard RFC 6238"

#### B. Afficher le QR Code

**Résultat affiché** :
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/...",
  "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "message": "Scannez le QR code..."
}
```

**Action** : Copier le `qr_code` (toute la chaîne base64)

**Navigateur 2** : Créer un fichier HTML temporaire
```html
<!DOCTYPE html>
<html>
<head><title>QR Code TOTP</title></head>
<body style="text-align:center; padding:50px;">
    <h1>Scannez avec Google Authenticator</h1>
    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
         alt="QR Code"
         style="width:300px;height:300px;"/>
    <p style="font-size:20px; color:#666;">
        Code généré toutes les 30 secondes
    </p>
</body>
</html>
```

Ouvrir le fichier dans le navigateur.

#### C. Scanner avec le téléphone

**Action** :
1. Ouvrir **Google Authenticator** sur le téléphone
2. Appuyer sur "+" → "Scanner un code QR"
3. Scanner le QR code affiché à l'écran

**Résultat** : L'application affiche maintenant "IT SPIRIT NOVA - demo@itspirit.fr" avec un code à 6 chiffres qui change toutes les 30 secondes.

**Points à souligner** :
- "Le code change toutes les 30 secondes"
- "Même si notre serveur est hors ligne, l'application génère le code"
- "Compatible avec tous les clients TOTP standard (Google, Microsoft, Authy, 1Password)"

#### D. Vérifier le code TOTP

**Action** :
1. Lire le code actuel sur le téléphone (ex: "123456")
2. Retourner sur Swagger UI
3. Trouver l'endpoint `POST /api/mfa/totp/enroll/verify`
4. Cliquer sur "Try it out"
5. Entrer le code dans le body :
   ```json
   {
     "code": "123456"
   }
   ```
6. Cliquer sur "Execute"

**Résultat attendu** :
```json
{
  "success": true,
  "recovery_codes": [
    "ABCD-1234",
    "EFGH-5678",
    "IJKL-9012",
    "MNOP-3456",
    "QRST-7890",
    "UVWX-1234",
    "YZAB-5678",
    "CDEF-9012",
    "GHIJ-3456",
    "KLMN-7890"
  ],
  "message": "TOTP activé avec succès..."
}
```

**Points à souligner** :
- "10 codes de récupération générés automatiquement"
- "Chaque code est à usage unique"
- "L'utilisateur doit les conserver en lieu sûr (gestionnaire de mots de passe, coffre)"
- "En cas de perte du téléphone, ces codes permettent de se connecter"

---

### Démo 2 : Connexion avec 2FA (3 minutes)

#### A. Simuler une connexion

**Terminal** : Lancer le script de test
```bash
python demo_2fa_test.py
```

**Entrées** :
```
Email de test: demo@itspirit.fr
Mot de passe: Demo2024!

Choix (1-6): 2  # Vérification TOTP
```

**Points à souligner** :
- "Après la validation du mot de passe, le serveur retourne un token temporaire (5 minutes)"
- "Ce token ne donne accès qu'aux endpoints MFA, pas aux ressources"

#### B. Vérifier le code TOTP

**Action** : Lire le code actuel sur Google Authenticator

**Script** : Entrer le code à 6 chiffres

**Résultat** :
```
✓ Authentification 2FA réussie!
✓ Token completed reçu: eyJhbGciOiJIUzI1NiIs...
```

**Points à souligner** :
- "Maintenant l'utilisateur a un token valide pour 60 minutes"
- "Il peut accéder à toutes les ressources protégées"
- "L'événement est enregistré dans les logs (IP, User-Agent, timestamp)"

---

### Démo 3 : SMS de secours (2 minutes)

#### A. Configurer un numéro de téléphone

**Swagger UI** : `POST /api/mfa/phone/set`

**Body** :
```json
{
  "phone": "+33612345678"
}
```

**Résultat** :
```json
{
  "success": true,
  "message": "Code de vérification envoyé par SMS",
  "message_id": "SM1234567890"
}
```

**Points à souligner** :
- "Le numéro doit être au format international E.164 (+33...)"
- "Le système envoie un code de vérification pour s'assurer que le numéro est valide"
- "Support OVH SMS et Twilio (basculement automatique)"

#### B. Simuler l'utilisation du SMS comme secours

**Scénario** : "L'utilisateur a perdu son téléphone avec Google Authenticator"

**Swagger UI** : `POST /api/mfa/sms/send`

**Résultat** :
```json
{
  "success": true,
  "message_id": "SM9876543210",
  "expires_at": "2025-10-17T14:35:00Z",
  "message": "Code envoyé par SMS, valide pendant 5 minutes"
}
```

**Points à souligner** :
- "Le code SMS est valide 5 minutes"
- "Rate limiting strict : 1 SMS par minute, 3 par heure (anti-spam)"
- "Le code est stocké dans Redis (distribué) ou en mémoire (développement)"

---

### Démo 4 : Code de récupération (2 minutes)

**Scénario** : "L'utilisateur a perdu son téléphone ET n'a pas accès aux SMS"

**Swagger UI** : `POST /api/mfa/verify/recovery`

**Body** :
```json
{
  "code": "ABCD-1234"
}
```

**Résultat** :
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "mfa_ok": true,
  "remaining_codes": 9
}
```

**Points à souligner** :
- "Le code est consommé après utilisation (impossible de le réutiliser)"
- "Il reste 9 codes après cette utilisation"
- "L'utilisateur peut régénérer 10 nouveaux codes via l'API (limite : 3/jour)"

---

### Démo 5 : Protection anti-bruteforce (2 minutes)

**Terminal** : Script de test
```bash
python demo_2fa_test.py
```

**Choix** : 5 (Test anti-bruteforce)

**Action** : Le script envoie 10 codes TOTP invalides automatiquement

**Résultat attendu** :
```
Tentative 1/10... 401
Tentative 2/10... 401
...
Tentative 10/10... 423 BLOQUÉ!

{
  "detail": "Compte verrouillé en raison de tentatives échouées multiples.
             Réessayez dans 15 minutes."
}

✓ Protection anti-bruteforce activée!
```

**Points à souligner** :
- "Blocage automatique après 10 échecs"
- "Durée de verrouillage : 15 minutes"
- "Le compteur est par utilisateur + IP (évite le blocage accidentel)"
- "L'événement est enregistré dans les logs pour analyse"

---

### Démo 6 : Rate limiting (1 minute)

**Swagger UI** : Tester rapidement `POST /api/mfa/verify/totp` plusieurs fois

**Action** : Cliquer sur "Execute" 15 fois de suite (rapidement)

**Résultat attendu (HTTP 429)** :
```json
{
  "detail": "Trop de requêtes. Limite : 10 requêtes par minute."
}
```

**Points à souligner** :
- "Protection contre les attaques par déni de service (DoS)"
- "Limites configurables par endpoint"
- "Support Redis pour distribution multi-serveurs"

---

## PARTIE 3 : LOGS ET AUDIT TRAIL (3 minutes)

### Afficher les logs structurés

**Terminal** : Afficher les derniers logs
```bash
# Si logs dans un fichier
tail -f logs/mfa.log | grep mfa_event

# Ou afficher les logs du serveur
```

**Exemple de log JSON** :
```json
{
  "timestamp": "2025-10-17T14:23:45.123Z",
  "level": "INFO",
  "logger": "mfa.totp",
  "user_id": 1,
  "email": "demo@itspirit.fr",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
  "mfa_event": "totp_verify",
  "mfa_method": "totp",
  "result": "success",
  "extra_data": {
    "attempt_count": 1
  }
}
```

**Points à souligner** :
- "Tous les événements MFA sont enregistrés"
- "Format JSON structuré pour analyse automatisée (ELK, Datadog)"
- "Tracking IP et User-Agent pour détecter les anomalies"
- "Permet de générer des rapports de sécurité"

### Afficher le statut dans la base de données

**PostgreSQL** :
```sql
SELECT
    email,
    is_totp_enabled,
    is_phone_verified,
    mfa_backup_method,
    mfa_failed_attempts,
    mfa_last_success,
    mfa_last_ip
FROM users
WHERE email = 'demo@itspirit.fr';
```

**Résultat** :
```
| email              | is_totp_enabled | is_phone_verified | mfa_backup_method | mfa_failed_attempts | mfa_last_success       | mfa_last_ip   |
|--------------------|-----------------|-------------------|-------------------|---------------------|------------------------|---------------|
| demo@itspirit.fr   | true            | true              | sms               | 0                   | 2025-10-17 14:23:45+00 | 192.168.1.100 |
```

**Points à souligner** :
- "Toutes les informations MFA sont stockées dans la base"
- "Permet de voir rapidement si un utilisateur a configuré le 2FA"
- "Tracking des dernières connexions pour analyse de sécurité"

---

## PARTIE 4 : QUESTIONS & RÉPONSES (3 minutes)

### Questions anticipées

#### Q1 : "Combien de temps prend la configuration pour un utilisateur ?"
**R** : "Environ 30 secondes : scanner le QR code, entrer un code, noter les codes de récupération."

#### Q2 : "Que se passe-t-il si un utilisateur perd son téléphone ?"
**R** : "Il a 3 options : SMS (si configuré), codes de récupération (10 codes), ou contact administrateur."

#### Q3 : "Est-ce compatible avec tous les smartphones ?"
**R** : "Oui, Google Authenticator et Microsoft Authenticator sont disponibles sur iOS et Android. Même les anciens téléphones peuvent recevoir des SMS."

#### Q4 : "Quel est l'impact sur la performance ?"
**R** : "Négligeable. La vérification TOTP prend moins de 10ms. Le système peut traiter des milliers de vérifications par seconde."

#### Q5 : "Comment gérer les utilisateurs qui refusent d'activer le 2FA ?"
**R** : "Le champ `mfa_enforced` permet de rendre le 2FA obligatoire par utilisateur ou pour toute l'organisation."

#### Q6 : "Est-ce conforme aux réglementations (RGPD, etc.) ?"
**R** : "Oui, le système suit les recommandations du NIST et génère un audit trail complet pour la conformité."

#### Q7 : "Quel est le coût des SMS ?"
**R** : "Dépend du provider (OVH : ~0.05€/SMS, Twilio : ~0.07€/SMS). Mais le SMS est une méthode de secours, pas la méthode principale."

---

## PARTIE 5 : CONCLUSION (2 minutes)

### Récapitulatif des avantages

**Sécurité** :
- Protection contre le phishing et le vol de mots de passe
- Anti-bruteforce et rate limiting
- Audit trail complet

**Facilité d'utilisation** :
- Configuration en 30 secondes
- 3 méthodes de secours
- Compatible avec tous les clients TOTP standard

**Conformité** :
- RFC 6238 (TOTP)
- NIST SP 800-63B (MFA)
- Logs structurés pour audits

**Résilience** :
- 3 méthodes indépendantes
- Fallback automatique SMS (OVH → Twilio)
- Codes de récupération imprimables

### Prochaines étapes recommandées

1. **Court terme** :
   - Déployer en production avec utilisateurs pilotes
   - Former le support IT
   - Créer documentation utilisateur

2. **Moyen terme** :
   - Ajouter support WebAuthn (clés de sécurité FIDO2)
   - Dashboard admin pour gestion MFA
   - Notifications push (Firebase)

3. **Long terme** :
   - Analyse comportementale (IP suspectes)
   - Support passkeys (passwordless)
   - Machine learning pour détection fraude

---

## CHECK-LIST AVANT LA DÉMO

- [ ] Serveur FastAPI démarré (http://localhost:8200)
- [ ] Swagger UI accessible (http://localhost:8200/docs)
- [ ] Base de données PostgreSQL opérationnelle
- [ ] Compte utilisateur de test créé
- [ ] Google Authenticator installé sur téléphone
- [ ] Script de test prêt (`demo_2fa_test.py`)
- [ ] Fichier HTML pour QR code préparé
- [ ] Terminal avec logs visible
- [ ] Présentation / whiteboard prêt

---

## TIMING TOTAL : 25 minutes

- Partie 1 (Vue d'ensemble) : 2 minutes
- Partie 2 (Démo pratique) : 15 minutes
- Partie 3 (Logs/Audit) : 3 minutes
- Partie 4 (Q&R) : 3 minutes
- Partie 5 (Conclusion) : 2 minutes

---

## POINTS CLÉS À RETENIR

**Message final** :
> "Notre système 2FA est prêt pour la production. Il répond aux standards de sécurité modernes, est facile à utiliser, et offre plusieurs méthodes de secours. Nous recommandons un déploiement progressif avec des utilisateurs pilotes avant un rollout complet."

**Bonne démonstration !**
