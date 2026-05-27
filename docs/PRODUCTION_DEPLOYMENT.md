# NOVA-SERVER — Déploiement production

Document opérationnel pour le déploiement, l'exploitation et le rollback de NOVA-SERVER en production.

## Pré-requis machine

- Windows Server 2019+ (testé sur `Windows Server 2019 Standard 10.0.17763`)
- Python 3.10 installé (`C:\Python\python.exe`)
- Virtualenv local : `.venv\` dans la racine du repo
- PostgreSQL 14+ accessible (URL dans `DATABASE_URL`)
- SAP B1 Service Layer accessible sur `SAP_REST_BASE_URL`
- Microsoft Graph credentials valides (Azure AD)
- Caddy (reverse proxy TLS) — binaire à la racine du repo : `caddy.exe`
- NSSM (gestionnaire de services Windows) — `winget install NSSM` ou téléchargement direct

## Configuration `.env`

Toujours copier depuis `.env.example` et compléter. Variables critiques à valider :

| Variable | Valeur prod attendue | Source |
|---|---|---|
| `NOVA_MODE` | `production` | manuel — active `Secure` cookies, log INFO |
| `DISABLE_DOCS` | `true` | masque `/docs`, `/redoc`, `/openapi.json` |
| `APP_PORT` | `8001` | exposé en interne, Caddy proxy 443 → 8001 |
| `DATABASE_URL` | `postgresql://...` | fail-fast au démarrage si absente (L3) |
| `WEBHOOK_CLIENT_STATE` | secret aléatoire ≥ 32 chars | utilisé par HMAC `compare_digest` (L3) |
| `NOVA_JWT_SECRET` | `secrets.token_hex(32)` | signature JWT cookies HttpOnly |
| `SAP_CA_BUNDLE_PATH` | chemin vers bundle CA SAP | sinon `verify=False` + WARNING au boot (L5d) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | clés roteables | rotation tous les 6 mois |
| `SALESFORCE_CONSUMER_KEY`, `SALESFORCE_CONSUMER_SECRET` | renommés en L2 (anciennement franco-anglais) | clés Connected App |

## Démarrage initial

```powershell
# 1. Cloner et configurer
git clone <repo-url> C:\Users\PPZ\NOVA-SERVER
cd C:\Users\PPZ\NOVA-SERVER
copy .env.example .env
# Compléter les valeurs sensibles dans .env

# 2. Python venv + dépendances
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt

# 3. Initialisation base auth (créée automatiquement au premier démarrage)
.venv\Scripts\python.exe main.py
# Ctrl+C après "DEMARRAGE NOMINAL NOVA" pour s'assurer que nova_auth.db est créée
```

## Services Windows (NSSM)

Installation des 2 services autostart :

```powershell
# Service backend NOVA
nssm install NOVA-Backend "C:\Users\PPZ\NOVA-SERVER\.venv\Scripts\python.exe" "main.py"
nssm set NOVA-Backend AppDirectory "C:\Users\PPZ\NOVA-SERVER"
nssm set NOVA-Backend AppStdout "C:\Users\PPZ\NOVA-SERVER\logs\service.log"
nssm set NOVA-Backend AppStderr "C:\Users\PPZ\NOVA-SERVER\logs\service-error.log"
nssm set NOVA-Backend Start SERVICE_AUTO_START

# Service Caddy (reverse proxy HTTPS)
nssm install NOVA-Caddy "C:\Users\PPZ\NOVA-SERVER\caddy.exe" "run"
nssm set NOVA-Caddy AppDirectory "C:\Users\PPZ\NOVA-SERVER"
nssm set NOVA-Caddy Start SERVICE_AUTO_START

# Démarrage
nssm start NOVA-Backend
nssm start NOVA-Caddy

# Vérification
nssm status NOVA-Backend  # doit retourner SERVICE_RUNNING
nssm status NOVA-Caddy    # doit retourner SERVICE_RUNNING
```

Test de redémarrage automatique : `shutdown /r /t 0`. Après reboot, les 2 services doivent revenir SERVICE_RUNNING sans intervention.

## Backup SQLite quotidien

Plusieurs bases SQLite à sauvegarder : `data/nova_auth.db`, `email_analysis.db`, `sap_cache.db`, `supplier_tariffs.db`, `webhooks.db`.

Tâche Windows planifiée (3h du matin, locale machine) :

```powershell
$action = New-ScheduledTaskAction -Execute "robocopy" -Argument "C:\Users\PPZ\NOVA-SERVER\data C:\Backups\NOVA\$(Get-Date -Format 'yyyy-MM-dd') /E"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "NOVA-SQLite-Backup" -Action $action -Trigger $trigger -RunLevel Highest
```

Rétention : prévoir un purge mensuelle des backups > 30 jours.

**Limite connue** : SQLite n'a PAS le mode WAL activé sur `nova_auth.db` et les autres `.db`. Conséquence : `uvicorn --workers > 1` reste interdit tant que WAL n'est pas appliqué (voir backlog post-prod).

## Monitoring

Endpoints à surveiller (typiquement via Uptime Kuma ou équivalent) :

| Endpoint | Auth | Fréquence | Alerte si |
|---|---|---|---|
| `GET /health` | publique | 1 min | code != 200 ou `summary.success_rate < 50` |
| `GET /api/auth/me` | cookie nova_session | 5 min (synthetic login) | code != 200 |
| `GET /api/sap-rondot/...` | cookie + cookie test admin | 15 min | code != 200 |

`/health` retourne `degraded` si Salesforce subprocess échoue — c'est attendu tant que l'issue subprocess salesforce_mcp préexistante n'est pas résolue (voir backlog).

## Procédure de mise à jour

```powershell
# 1. Arrêter les services
nssm stop NOVA-Backend
nssm stop NOVA-Caddy

# 2. Pull
cd C:\Users\PPZ\NOVA-SERVER
git fetch
git status   # vérifier qu'il n'y a pas de modifs locales non commitées
git pull --ff-only

# 3. Mettre à jour dépendances si requirements.txt a changé
.venv\Scripts\pip.exe install -r requirements.txt

# 4. Supprimer les .pyc périmés (cf. Leçon Critique 23/02/2026)
Get-ChildItem -Path . -Filter "*.pyc" -Recurse | Remove-Item -Force
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force

# 5. Redémarrer
nssm start NOVA-Backend
nssm start NOVA-Caddy

# 6. Validation post-déploiement
curl -s http://localhost:8001/health | python -m json.tool
.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"
# Doit retourner 217 (ou la baseline en vigueur)
```

## Procédure de rollback

En cas de régression critique après mise à jour :

```powershell
# 1. Arrêter les services
nssm stop NOVA-Backend
nssm stop NOVA-Caddy

# 2. Revenir au commit précédent stable
cd C:\Users\PPZ\NOVA-SERVER
git log --oneline -10
git reset --hard <hash-commit-stable>

# 3. Suppression .pyc + redémarrage
Get-ChildItem -Path . -Filter "*.pyc" -Recurse | Remove-Item -Force
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force
nssm start NOVA-Backend
nssm start NOVA-Caddy
```

Le rollback ne touche pas les données : les bases SQLite et PostgreSQL restent dans l'état laissé par la version précédente. Si une migration de schéma a été appliquée, la rollback peut être incomplet — préférer une vraie procédure de migration aller-retour Alembic.

## Rappels périodiques

| Action | Fréquence | Pourquoi |
|---|---|---|
| Rotation `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | 6 mois | bonne pratique |
| Rotation `NOVA_JWT_SECRET` | 12 mois ou incident | invalide toutes les sessions actives |
| Vérification `SAP_CA_BUNDLE_PATH` | à chaque renouvellement cert SAP | sinon WARNING au boot |
| Vérification backups SQLite | 1 mois | tester un restore complet |
| Purge logs `nova.log.5` (RotatingFileHandler garde 5 backups) | automatique | rien à faire |

## Procédures d'urgence

**Connexion SAP impossible** — vérifier session SAP côté serveur : si erreur 305 "User Already Logged In", se référer à la mémoire `auto memory` qui rappelle de ne jamais lancer de script Python séparé connecté à SAP pendant que le serveur tourne. Solution : redémarrer NOVA-Backend pour relancer la session.

**Cookie `nova_session` non stocké en navigateur** — vérifier `NOVA_MODE=production` (qui active `Secure`). Sur HTTPS, navigateur l'accepte ; sur HTTP localhost, il rejette. Si test local nécessaire, basculer `NOVA_MODE=development` localement.

**Webhook Microsoft Graph reçu mais ignoré** — vérifier `WEBHOOK_CLIENT_STATE` côté serveur identique à celui passé à Graph lors de la création de la subscription. Si rotaté, recréer toutes les subscriptions (`POST /api/webhooks/subscriptions/renew/{id}`).

## Référence — Architecture auth post-L7

- Cookie `nova_session` : JWT signé HS256, 60 min TTL, `HttpOnly Secure SameSite=Strict Path=/`
- Cookie `nova_refresh` : opaque token, 7 j TTL, `HttpOnly Secure SameSite=Strict Path=/api/auth/refresh` (scoped au refresh)
- WebSocket : cookie envoyé sur le handshake, validé par `_authenticate_ws()` (close 4401 si invalide)
- 201 API routes protégées sur 211 total (22 admin-only via `require_role("ADMIN")`)
- 10 routes publiques restantes : login/refresh/health/HTML interface/webhook callback HMAC

Détail dans [`docs/AUTH_ARCHITECTURE.md`](AUTH_ARCHITECTURE.md).
