# Coffre de configuration chiffré + écran d'admin (Lot 2 / étape 2a)

Le coffre `secrets.enc` est la **source unique** de configuration de NOVA. Au
démarrage, `run.py` le déchiffre et peuple `os.environ` **avant** tout import
applicatif ; en l'absence de coffre (ou de clé maître), NOVA retombe sur `.env`.

- Crypto : `services/secure_config.py` (Fernet — AES-128-CBC + HMAC-SHA256).
- Clé maître : variable d'environnement `NOVA_VAULT_KEY` (jamais sur disque, jamais commitée).
- Coffre : `secrets.enc` (gitignoré, `*.enc` gitignoré).
- Écran d'admin : `GET`/`PUT /api/admin/config` (rôle ADMIN) + page `/admin/config`.

> **Ne jamais committer** `secrets.enc` ni une clé maître. `.gitignore` couvre
> déjà `secrets.enc`, `*.enc`, `nova_vault.key`.

## Provisioning en DEV

### 1. Générer une clé maître de test

```bash
.venv/Scripts/python.exe scripts/provision_secrets.py --genkey
```

La commande affiche une ligne `NOVA_VAULT_KEY=...`. La clé n'est **pas** écrite
sur disque. Exposer cette clé dans l'environnement de la session :

```powershell
# PowerShell
$env:NOVA_VAULT_KEY = "la-cle-affichee"
```
```bash
# Git Bash
export NOVA_VAULT_KEY="la-cle-affichee"
```

### 2. Générer `secrets.enc` à partir du `.env`

Avec `NOVA_VAULT_KEY` exposée dans l'environnement :

```bash
.venv/Scripts/python.exe scripts/provision_secrets.py --source .env --out secrets.enc
```

Le coffre est écrit puis relu pour vérification (« Verification de relecture : OK »).

### 3. Démarrer NOVA en mode COFFRE

Avec `secrets.enc` présent **et** `NOVA_VAULT_KEY` dans l'environnement, le
démarrage logue `Mode COFFRE actif : N paire(s) chargee(s)...`. Sinon, NOVA logue
`Mode .env actif` et lit `.env` (repli automatique, aucune exception bloquante).

## Écran d'administration de la configuration

- URL : `/admin/config` (coquille HTML ; toutes les données passent par l'API ADMIN).
- `GET /api/admin/config` : renvoie toutes les variables **groupées par catégorie**.
  Une clé **sensible** (nom contenant `PASSWORD`/`SECRET`/`KEY`/`TOKEN`/
  `CONSUMER_SECRET`/`CLIENT_SECRET`/`API_KEY`, ou `DATABASE_URL`) n'est **jamais**
  renvoyée en clair : `{key, category, is_secret:true, is_set, preview:"********"}`.
  Une clé non sensible renvoie sa valeur.
- `PUT /api/admin/config` : accepte une map **partielle** `{"updates": {clé: valeur}}`,
  **fusionne** dans le coffre courant (les clés non envoyées sont préservées — un
  secret masqué non modifié n'est pas écrasé), re-chiffre `secrets.enc`, journalise
  **uniquement les noms** de clés modifiées, et renvoie `restart_required: true`.

> Les modifications ne sont prises en compte qu'**au redémarrage** (les variables
> sont chargées une seule fois, au démarrage de `run.py`).
