# 🚀 Lancer la Démonstration 2FA

## ✅ Étape 1 : Démarrer le serveur

```bash
python main.py
```

**Vérification** : Le serveur devrait démarrer sans erreur et afficher :
```
INFO:     Uvicorn running on http://0.0.0.0:8200 (Press CTRL+C to quit)
```

---

## 🎯 Étape 2 : Choisir votre mode de démo

### Option A : Interface Web (RECOMMANDÉ pour les patrons)

**Ouvrir dans le navigateur :**
```
http://localhost:8200/demo/2fa
```

**Avantages :**
- ✅ Interface visuelle moderne
- ✅ Très impressionnante visuellement
- ✅ Facile à suivre pour les non-techniques
- ✅ Indicateur de progression (1→2→3)
- ✅ Support des 3 méthodes 2FA

**Déroulement :**
1. Entrer email/password
2. Choisir la méthode 2FA (TOTP, SMS, ou Recovery)
3. Valider le code
4. Voir l'écran de succès
5. Afficher le statut MFA

---

### Option B : Script Python visuel

```bash
python demo_2fa_visual.py
```

**Avantages :**
- ✅ Affichage coloré dans le terminal
- ✅ Tableaux récapitulatifs
- ✅ Messages clairs et structurés
- ✅ Test anti-bruteforce disponible

**Déroulement :**
1. Entrer email/password
2. Voir le statut MFA
3. Choisir le scénario :
   - 1 = TOTP
   - 2 = SMS
   - 3 = Recovery code
   - 4 = Test anti-bruteforce
4. Voir le récapitulatif final

---

### Option C : API Swagger (pour les développeurs)

**Ouvrir dans le navigateur :**
```
http://localhost:8200/docs
```

**Avantages :**
- ✅ Tester directement les endpoints
- ✅ Voir la documentation API complète
- ✅ Modifier les paramètres en temps réel

**Endpoints disponibles :**
- `POST /auth/login` - Connexion (1er facteur)
- `GET /api/mfa/status` - Statut 2FA
- `POST /api/mfa/verify/totp` - Vérifier TOTP
- `POST /api/mfa/verify/sms` - Vérifier SMS
- `POST /api/mfa/verify/recovery` - Vérifier code récupération
- `POST /api/mfa/sms/send` - Envoyer SMS
- Et 8 autres endpoints...

---

## 📋 Scénario complet de démo (10 minutes)

### 1. Introduction (1 min)
> "Je vais vous montrer notre système d'authentification à deux facteurs. Il ajoute une couche de sécurité supplémentaire après le mot de passe."

### 2. Démonstration Interface Web (5 min)

**Ouvrir** : `http://localhost:8200/demo/2fa`

1. **Connexion** :
   - Email : `p.perez@it-spirit.com`
   - Password : `31021225`
   - Cliquer "Se connecter"

2. **Montrer le token mfa_pending** :
   - "Après validation du mot de passe, on reçoit un token temporaire de 5 minutes"
   - "Ce token ne donne accès QU'AUX endpoints MFA, pas aux ressources"

3. **Méthode TOTP** (principale) :
   - Cliquer sur "TOTP"
   - "L'utilisateur ouvre Google Authenticator sur son téléphone"
   - Entrer le code à 6 chiffres
   - "Le code change toutes les 30 secondes"
   - Valider

4. **Écran de succès** :
   - "Maintenant l'utilisateur a un token complet valide 60 minutes"
   - "Il peut accéder à toutes les ressources protégées"

5. **Afficher le statut** :
   - Cliquer "Voir le statut MFA"
   - Montrer le tableau récapitulatif

### 3. Test Anti-Bruteforce (2 min)

**Lancer** : `python demo_2fa_visual.py`

1. Choisir option **4** (Test anti-bruteforce)
2. Accepter l'avertissement
3. Le script envoie 10 codes invalides
4. **Montrer le blocage** après 10 tentatives :
   ```
   🛡️ PROTECTION ANTI-BRUTEFORCE ACTIVÉE !
   🔒 Compte verrouillé !
   Durée de verrouillage : 15 minutes
   ```

### 4. Questions & Réponses (2 min)

**Questions anticipées :**

Q : "Que se passe-t-il si l'utilisateur perd son téléphone ?"
R : "Il a 3 options : SMS (si configuré), codes de récupération (10 codes), ou contacter l'admin"

Q : "Combien de temps pour configurer ?"
R : "30 secondes : scanner QR code, entrer un code, noter les codes de récupération"

Q : "Est-ce compatible avec tous les smartphones ?"
R : "Oui, Google/Microsoft Authenticator sur iOS et Android. Même les vieux téléphones peuvent recevoir des SMS"

---

## 🎯 Points clés à souligner

### Sécurité
- ✅ Protection contre phishing et vol de mots de passe
- ✅ Anti-bruteforce (15 min de blocage après 10 échecs)
- ✅ Rate limiting (protection DoS)
- ✅ Audit trail complet (tous événements loggés)

### Facilité d'utilisation
- ✅ Configuration en 30 secondes
- ✅ 3 méthodes de secours (TOTP, SMS, Recovery)
- ✅ Compatible tous clients TOTP standard

### Conformité
- ✅ RFC 6238 (TOTP standard)
- ✅ NIST SP 800-63B (MFA)
- ✅ Logs structurés pour audits RGPD

### Résilience
- ✅ 3 méthodes indépendantes
- ✅ Fallback automatique SMS (OVH → Twilio)
- ✅ Codes de récupération imprimables

---

## 🐛 Dépannage

### Le serveur ne démarre pas
```bash
# Vérifier que le port 8200 est libre
netstat -ano | findstr :8200

# Si occupé, tuer le processus
taskkill /PID <PID> /F
```

### Erreur "Module not found"
```bash
# Installer dans le .venv
.venv/Scripts/python.exe -m pip install email-validator
```

### Erreur "Could not validate credentials"
- Vérifier que le compte utilisateur existe dans la base
- Vérifier que le mot de passe est correct
- Vérifier que `is_active = true`

### 404 sur /auth/login
- Vérifier que le serveur a bien été redémarré après l'ajout de la route
- Vérifier dans Swagger (`/docs`) que la section "Authentification" existe

---

## 📚 Documentation complète

- **Guide complet** : [DEMO_2FA_GUIDE.md](DEMO_2FA_GUIDE.md)
- **Scénario détaillé** : [DEMO_SCENARIO.md](DEMO_SCENARIO.md)
- **API Swagger** : http://localhost:8200/docs
- **Interface web** : http://localhost:8200/demo/2fa

---

## ✨ Message final pour vos patrons

> "Notre système 2FA est **complet et prêt pour la production**. Nous avons :
>
> ✅ Une API REST complète (14 endpoints)
> ✅ 3 méthodes d'authentification (TOTP, SMS, Recovery)
> ✅ Protection anti-bruteforce et rate limiting
> ✅ Audit trail complet
> ✅ Interface web moderne
> ✅ Conforme aux standards (RFC 6238, NIST)
> ✅ Compatible tous clients TOTP (Google, Microsoft, Authy, 1Password)
>
> Le système peut être déployé dès maintenant."

**Bonne démonstration ! 🎉**
