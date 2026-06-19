# Spécification — Compilation et protection du code NOVA (déploiement RONDOT)

Référence devis : **D-2026-682** (signé « Bon pour accord » le 16/06/2026 par Hervé HUAN)
Base de référence du code : clone local, commit `47d2ad4`
Document complémentaire à `SPEC_LIVRAISON_RONDOT.md` (lots A/B/C fonctionnels).

---

## Objet

Livrer NOVA sur le serveur RONDOT **sans exposer le code source métier**, et permettre la
saisie/modification des paramètres aujourd'hui dans le `.env` via un module d'administration,
sans recompilation.

NOVA reste une application FastAPI lancée sous uvicorn. Le code métier est livré en binaires
`.pyd` (Cython). La configuration et les secrets vivent dans un **fichier chiffré unique**,
ouvert au démarrage par une clé maître embarquée dans le code compilé. Un écran d'admin web
édite ces paramètres ; un outil hors-ligne amorce le coffre au premier déploiement.

### Cadrage honnête (limites)

- Compiler du Python est de la **dissuasion**, pas une protection inviolable : un `.pyd` Cython
  n'est pas décompilable en source mais reste désassemblable avec effort. À coupler avec une
  **clause contractuelle**.
- La clé maître embarquée dans un `.pyd` est du *security by obscurity* : extractible par un
  attaquant déterminé disposant du binaire. Acceptable pour l'objectif (dissuasion admin RONDOT),
  ce n'est pas un secret matériel (HSM).
- Coût logiciel : **nul**. Cython (Apache 2.0) et MS C++ Build Tools sont gratuits. Le coût est
  en temps d'ingénierie.

---

## Récapitulatif des décisions validées

| # | Sujet | Décision |
|---|---|---|
| 1 | Objectif | Dissuasion d'un admin RONDOT + clause contractuelle (pas anti-RE forte) |
| 2 | Technique | Cython : chaque module `.py` → `.pyd` |
| 3 | Périmètre | Tout le métier compilé ; restent en `.py` : mini-lanceur, migrations alembic, `__init__` au besoin |
| 4 | Secrets | UI admin (extension `routes/routes_admin.py`) + coffre chiffré + loader central peuplant `os.environ` au démarrage |
| 5 | Coffre | Fichier chiffré unique `secrets.enc` (inclut `DATABASE_URL`) |
| 6 | Build | Chez IT SPIRIT (Python 3.10.10 x64 + MSVC Build Tools) ; livrer uniquement binaires + non-code |
| 7 | Amorçage | Outil de provisioning hors-ligne génère `secrets.enc` ; l'UI admin n'édite qu'ensuite |
| 8 | Migrations | Le lanceur enchaîne déchiffrement → `alembic upgrade head` → `uvicorn.run(app)` |
| 9 | Maintenance | Git = source non compilée ; tout correctif = rebuild + redéploiement complet |

---

## Contrainte d'ordonnancement critique

Plusieurs modules lisent leur configuration **à l'import** (au chargement du module), pas à la
demande :

- `db/session.py` l.8 : `DATABASE_URL = os.getenv("DATABASE_URL")` puis l.9-10 lève une
  `RuntimeError` si absent.
- `main.py` l.3-4 : `from dotenv import load_dotenv` / `load_dotenv()`.
- `auth/jwt_service.py` : `SECRET_KEY`, TTL lus au niveau module.

**Conséquence :** le loader du coffre doit peupler `os.environ` **avant** tout import de
`db/session` ou des routes. Cela impose un point d'entrée mince qui s'exécute en premier
(voir Lot 3). C'est aussi pourquoi un changement de secret nécessite un **redémarrage** pour
être pris en compte partout.

---

## Lot 1 — Coffre chiffré + loader central + outil de provisioning

À valider **en mode non compilé d'abord** (brique la plus risquée fonctionnellement à cause des
`load_dotenv()` dispersés).

### 1.1 — Coffre `secrets.enc`

- Un seul fichier chiffré contenant l'intégralité des paires clé/valeur du `.env`
  (102 variables aujourd'hui dans `.env.example`), `DATABASE_URL` compris.
- Chiffrement symétrique authentifié (recommandé : `cryptography` / Fernet, déjà dans
  l'écosystème Python ; à confirmer présence dans `requirements.txt`).
- Clé maître : constante définie dans un module qui **sera compilé** en `.pyd` (ne jamais la
  laisser dans un fichier `.py` livré ni dans le coffre lui-même).

### 1.2 — Loader central

- Nouveau module (ex. `services/secure_config.py`, **à créer** — vérifier l'absence d'un
  équivalent avant création) exposant une fonction `load_secrets_into_environ()` :
  déchiffre `secrets.enc` avec la clé maître, puis `os.environ.setdefault(k, v)` pour chaque
  paire. `setdefault` pour ne pas écraser une variable déjà posée par l'OS.
- Appelée par le lanceur (Lot 3) **avant** tout autre import applicatif.
- Conserver `load_dotenv()` existants : ils deviennent inoffensifs (no-op si pas de `.env`),
  on ne les supprime pas pour limiter l'impact.

### 1.3 — Outil de provisioning hors-ligne

- Petit utilitaire (ex. `scripts/provision_secrets.py`) lancé par IT SPIRIT au déploiement :
  lit un template rempli (ou le `.env` réel) → écrit `secrets.enc`.
- Sert aussi à régénérer le coffre hors UI si besoin.

---

## Lot 2 — Écran d'administration des paramètres

Réutiliser l'infrastructure admin existante, ne pas la dupliquer.

- Routeur : `routes/routes_admin.py` — `router = APIRouter(prefix="/api/admin", ...)` (l.28),
  garde de rôle `_admin = Depends(require_role("ADMIN"))` (l.30), import `require_role` depuis
  `auth.dependencies` (l.24). Ajouter les endpoints de lecture/écriture des paramètres sous ce
  préfixe, protégés par `_admin`.
- Écriture = mise à jour du coffre via l'outil/loader du Lot 1 (ré-chiffrement de `secrets.enc`).
- Vue : sur le modèle de `templates/admin_llm.html`. Masquer les valeurs sensibles en lecture.
- **Comportement de prise en compte :** afficher clairement que la modification exige un
  redémarrage de l'app (cf. contrainte d'ordonnancement) ; ne pas promettre un rechargement à chaud.

---

## Lot 3 — Point d'entrée compilable

Aujourd'hui NOVA est lancé par `python main.py` (`restart_server.bat` → `.venv\Scripts\python.exe main.py`),
avec en bas de `main.py` le bloc `if __name__ == "__main__": uvicorn.run(app, ...)`.
Un `.pyd` ne s'exécute pas via `python main.pyd`.

- Créer un lanceur mince **non compilé** (ex. `run.py`) qui, dans l'ordre :
  1. `from services.secure_config import load_secrets_into_environ; load_secrets_into_environ()`
  2. `alembic upgrade head` (par programme) — cf. Lot 4
  3. `import uvicorn` + `from main import app` (`main` devient `main.pyd`)
  4. `uvicorn.run(app, host=..., port=int(os.getenv("APP_PORT", 8001)), ...)`
- Déplacer dans `run.py` la logique du bloc `__main__` de `main.py` (gestion port Windows,
  `PYTHONIOENCODING`, `kill_process_on_port`).
- Mettre à jour `restart_server.bat` : `.venv\Scripts\python.exe run.py`.
- `app = FastAPI(...)` reste défini dans `main.py` (l.243) → compilé en `main.pyd`.

---

## Lot 4 — Migrations alembic après compilation

- Les fichiers de `alembic/versions` restent en `.py` (non sensibles, et alembic les charge par chemin).
- `alembic/env.py` l.10-20 fait son propre `load_dotenv()` + `os.getenv("DATABASE_URL")` :
  reste valable car `os.environ` est déjà peuplé par le loader avant l'appel.
- Le lanceur (Lot 3) déclenche `alembic upgrade head` par programme après le loader, avant uvicorn.

---

## Lot 5 — Pipeline de build Cython

- Environnement de build IT SPIRIT : **Python 3.10.10 x64** + **Microsoft C++ Build Tools**.
  Les `.pyd` sont verrouillés à la version CPython et à l'architecture → doivent correspondre
  au venv RONDOT (3.10.10 x64).
- Script de build compilant l'ensemble du code métier (`services/`, `routes/`, `managers/`,
  `models/`, `db/`, `auth/`, `quote_management/`, `utils/`, `workflow/`, `sap_mcp.py`,
  `salesforce_mcp.py`, `main.py`).
- Option de durcissement : directives Cython pour stripper les docstrings.
- Scripts autonomes exécutés en prod (notamment `register_webhook.py`, `renew_webhook.py` —
  renouvellement de webhook planifié) font `load_dotenv()` : soit les compiler et les passer par
  le loader, soit les conserver mais pointer sur le coffre. **À trancher au build.**

---

## Lot 6 — Hygiène de livraison (ne PAS exposer le code)

À déposer sur le serveur RONDOT : `.pyd` métier, fichiers non-code (`templates/`, `static/`,
`frontend/`, `alembic/`), `run.py`, `requirements.txt`, `secrets.enc`, scripts `.bat`.

À **ne jamais** livrer / présent sur le serveur :

- Aucune source `.py` métier.
- Les fichiers `.c` intermédiaires générés par Cython (contiennent la logique traduite).
- Les `__pycache__/` et `*.pyc` (bytecode décompilable). Déjà ignorés en git (`.gitignore`
  l.2, l.6) — vérifier qu'ils ne sont pas copiés au déploiement.
- La clé maître en clair.

`.gitignore` actuel ignore `.env*` (l.16-19) et `build/` (l.76-77) ; ajouter `secrets.enc`,
`*.c` générés, et le dossier de sortie de build au besoin.

Le front `mail-to-biz` (React) est déjà construit en static → non concerné par la compilation Python.

**Mécanisme de packaging.** Le repo dispose déjà de `scripts/package_deploy.ps1` (livraison
*source*, basé sur `git ls-files`) et de `.deployignore`. Comme les `.pyd` ne sont pas suivis
par git, la livraison compilée passe par un script **dédié** `scripts/package_compiled.ps1` qui
part de la sortie de build Cython et **réutilise les motifs de `.deployignore`** (source de vérité
unique des exclusions). `package_deploy.ps1` est conservé tel quel pour la livraison source/debug.

---

## Ordre de mise en œuvre recommandé

1. Lot 1 (coffre + loader + provisioning), validé **en non compilé**.
2. Lot 2 (écran admin).
3. Lot 3 (point d'entrée `run.py`).
4. Lot 4 (migrations au démarrage).
5. Lot 5 (build Cython des 163 fichiers).
6. Lot 6 (hygiène de livraison) + test de bout en bout sur **VM Windows propre** (venv 3.10.10
   x64, sans aucune source `.py` métier).

Effort réaliste : plusieurs jours (build sur 163 fichiers + coffre + UI + provisioning + tests),
pas une après-midi.

---

## Points à confirmer

- Présence de `cryptography` dans `requirements.txt` (sinon l'ajouter).
- Nom définitif des nouveaux modules (`services/secure_config.py`, `scripts/provision_secrets.py`)
  après vérification d'absence d'équivalent dans `nova-server`.
- Sort des scripts autonomes en prod (compilés vs `.py` + coffre).
- Politique de rotation de la clé maître (rare, mais impose un rebuild).
