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

## Clé maître embarquée (Lot 2 / étape 2b)

En livraison compilée, la clé maître n'est plus fournie via la variable
d'environnement `NOVA_VAULT_KEY` : elle est **embarquée** dans un module compilé
dédié, `_vault_key.pyd`, et **reconstruite à l'exécution** par `get_key()`.

### Résolution de la clé (`secure_config.get_master_key`)

1. **Clé embarquée d'abord** : tentative d'`import _vault_key` (livré uniquement
   sous forme `_vault_key.pyd`) puis appel de `_vault_key.get_key()`.
2. **Fallback DEV** : si `_vault_key` est absent (`ImportError` — module non
   généré/compilé, cas du poste de dev), repli sur `NOVA_VAULT_KEY` (comportement
   du Lot 1).
3. Si **aucune** des deux sources n'est disponible → `RuntimeError` explicite.

### Schéma d'obfuscation

`scripts/generate_vault_key_module.py` lit la clé maître depuis une source
**fournie au build et jamais commitée** (`--key-file <chemin>` ou
`NOVA_VAULT_KEY`) et génère `_vault_key.py` où la clé est :

- découpée en **segments**, chaque octet stocké sous la forme
  `octet_stocké = clé XOR masque_aléatoire XOR flux` ;
- `flux[i] = (SEED * (i+1) + 131) & 0xFF`, `SEED` étant une graine aléatoire 16
  bits propre à chaque génération.

La reconstruction exige **simultanément** les segments XOR, les masques *et* le
flux dérivé de `SEED` : aucun tableau stocké ne révèle la clé à lui seul, et le
**base64 complet de la clé n'apparaît jamais** dans le fichier (vérifié avant
écriture par le générateur ; `strings`/`grep` sur le `.pyd` ne le révèle pas).

### Chaîne de build et d'hygiène

- `_vault_key.py` est **gitignoré** : jamais commité, jamais livré en source.
- `build_cython_full` compile `_vault_key.py` → `_vault_key.pyd` **s'il est
  présent** (module racine optionnel). Avec lui, le total passe de 111 à **112
  modules** ; absent (dev), il est simplement ignoré.
- `package_compiled.ps1` ne laisse passer **que** `_vault_key.pyd` ; le garde-fou
  refuse tout `.py` hors allowlist — `_vault_key.py` n'y figure pas, donc une
  fuite de la source ferait **échouer** le packaging.

### Procédure de livraison

```bash
# 1. Générer le module à partir de la clé RONDOT (fichier NON commité)
.venv/Scripts/python.exe scripts/generate_vault_key_module.py --key-file C:\secure\rondot.key
# 2. Build Cython (compile aussi _vault_key.py -> _vault_key.pyd ; total 112)
scripts\build_cython_full.bat
# 3. Packaging (seul _vault_key.pyd ship ; garde-fou vérifie l'absence de .py)
powershell -ExecutionPolicy Bypass -File scripts\package_compiled.ps1
```

> **Limite assumée.** Un module compilé reste **réversible par désassemblage**.
> L'embarquement obfusqué est une mesure de **dissuasion** contre une extraction
> triviale (`strings`/`grep`), **pas** un coffre inviolable. C'est un choix
> assumé : la clé n'est jamais en clair sur disque ni dans le `.env` de
> production, ce qui élève significativement le coût d'une extraction.
