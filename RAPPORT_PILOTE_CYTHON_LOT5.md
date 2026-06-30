# Rapport — Pilote de compilation Cython (Lot 5)

Référence : `SPEC_COMPILATION_RONDOT.md` (Lot 5). Branche : `prod/lot5-cython-pilot` (depuis `main`).
Objectif : valider la chaîne de build Cython et l'équivalence `.pyd` ↔ source sur un
**échantillon représentatif de 3 modules**, sans modifier aucune source ni le démarrage.

## 1. Toolchain (validée)

| Élément | Constat |
|---|---|
| Python | **3.10.10, 64-bit** (`.venv\Scripts\python.exe`) — conforme cible RONDOT |
| Compilateur C | **MSVC présent** : Visual Studio Build Tools 2022, MSVC **14.44.35207**, `cl.exe` Hostx64/x64 |
| vcvars | `…\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat` présent |
| Cython | installé dans le venv : **3.2.5** |
| setuptools / wheel | 80.9.0 (présents) |

> Le compilateur étant présent, le pilote a pu aller jusqu'au bout. **Aucune installation
> manuelle requise.**

## 2. Modules choisis (3) et justification

Échantillon couvrant les patterns à risque distincts :

| # | Module | Pourquoi représentatif |
|---|---|---|
| (a) | `services/currency_service.py` | Service de logique « classique » : classe + **6 `async def`** + petit modèle Pydantic interne + `os.getenv`. Imports tiers uniquement → compile/charge en autonomie. |
| (b) | `services/pricing_models.py` | **Pydantic v2 authentique** : `Field`, `field_validator(mode='before')`, `Enum`, `class Config`. C'est le vrai candidat « modèles Pydantic ». |
| (c) | `routes/routes_products.py` | **Router FastAPI** : `APIRouter`, décorateurs `@router.get`, **2 handlers async**, paramètres `Query` + path, `HTTPException`, et `from services.mcp_connector import …` → teste l'import **`.pyd` → source non compilée**. |

> ⚠️ **Correction au cadrage du SPEC** : le candidat suggéré `models/data_models.py` n'est
> **pas** du Pydantic — il est en `@dataclass` + `Enum`. Le vrai module Pydantic v2 est
> `services/pricing_models.py`, retenu ici.

## 3. Résultat de compilation

Les 3 modules ont compilé **du premier coup côté Cython** (traduction `.py → .c` sans erreur),
puis en `.pyd` une fois la chaîne de build correctement amorcée (voir §5) :

```
build/compiled/services/currency_service.cp310-win_amd64.pyd   (~119 Ko)
build/compiled/services/pricing_models.cp310-win_amd64.pyd     (~88 Ko)
build/compiled/routes/routes_products.cp310-win_amd64.pyd      (~100 Ko)
```

Arborescence des packages **préservée** (`build/compiled/services/…`, `build/compiled/routes/…`).
Les `.c` sont confinés dans `build/cython_c/` (hors arbo source).

## 4. Smoke-test (`.pyd` chargés par chemin, comparés à la source) — **3/3 OK**

- **(b) pricing_models** : `model_dump()` + `field_validator` → **sortie strictement identique**
  à la source ; `SalesHistoryEntry` (sérialisation `date`→json) OK ; `Enum` (7 valeurs) OK.
- **(a) currency_service** : `async get_exchange_rate('EUR','EUR') → rate 1.0` ; `'EUR','XXX' → None` ;
  `SUPPORTED_CURRENCIES` identique. (Chemins hors réseau, via `asyncio.run`.)
- **(c) routes_products** : le router **expose ses 2 routes** (table identique à la source),
  handlers **async préservés**, import `.pyd → services.mcp_connector` (source) fonctionnel.

## 5. Patterns ayant nécessité un traitement particulier

### 5.1 — 🔴 CRITIQUE : `annotation_typing` (bloquant FastAPI/Pydantic)

Au premier build, l'import du router compilé échouait :

```
TypeError: Expected str, got Query
  q: Optional[str] = Query(None, ...)
```

**Cause** : par défaut Cython interprète les annotations PEP 484 (`q: Optional[str]`) comme des
**déclarations de type C** et type-check les valeurs par défaut. Or en FastAPI la valeur par
défaut est un objet `Query(...)` / `Depends(...)`, pas une `str` → rejet à l'initialisation du module.

**Correctif (obligatoire, généralisable)** : compiler avec la directive
`annotation_typing=False`. Après quoi le router charge et expose ses routes normalement.
→ **À appliquer au build de tous les fichiers** (routers FastAPI, services typés, modèles).

### 5.2 — Chaîne de build MSVC non auto-détectée par setuptools 80.x

`setuptools._distutils` ne localisait pas seul le BuildTools via `vswhere` (`_get_vc_env` renvoyait
vide → *« Unable to find a compatible Visual Studio installation »*), **même** vcvars chargé.

**Correctif** : lancer le build depuis un environnement MSVC initialisé + poser
`DISTUTILS_USE_SDK=1` (et `MSSdk=1`). C'est ce que fait le wrapper `scripts/build_cython_pilot.bat`.
→ À reproduire tel quel sur le poste de build IT SPIRIT.

### 5.3 — `async def`

Aucun traitement spécial. Les coroutines sont préservées (vérifié : `iscoroutinefunction` vrai
sur un handler compilé ; exécution `asyncio.run` OK).

### 5.4 — Pydantic v2

Aucun traitement spécial une fois 5.1 réglé. `field_validator(mode='before')`, `model_dump`,
sérialisation `date`, `Enum`, `class Config` se comportent à l'identique. *Nota* : le validateur
`mode='before'` sur un champ par défaut **ne s'exécute pas** si la valeur n'est pas fournie
(comportement Pydantic, identique source et `.pyd` — non lié à Cython).

### 5.5 — Import `.pyd` → module source

Un module compilé important un module **non compilé** (`services.mcp_connector`) fonctionne via
`sys.path` normal. Pas d'enjeu pour un build partiel/progressif.

### 5.6 — Détail d'outillage (chargement par chemin pour le test)

Une extension C n'exporte que `PyInit_<basename>` : pour charger un `.pyd` par chemin il faut
nommer le spec exactement d'après le basename. Sans incidence sur l'exécution réelle sous uvicorn
(import par nom de package classique).

## 6. Points NON couverts par ce pilote (à lever avant généralisation)

- **`from __future__ import annotations`** : présent dans **16 fichiers** (dont
  `routes/routes_shipping.py`, `routes_packing.py`, `routes_intelligent_assistant.py`,
  `services/transport/*`). Combiné à `annotation_typing=False` le risque est faible, mais
  **à tester explicitement** sur ≥1 router en ayant besoin (les annotations deviennent des
  chaînes → interaction avec FastAPI à confirmer).
- **Forward refs / `model_rebuild()` Pydantic** : aucun des 3 modules n'en utilise.
- **Imports relatifs entre deux modules *tous deux* compilés** : ici on n'a testé que
  compilé → source. À valider (probablement OK si l'arbo `build/compiled` est sur `sys.path`).
- **`__init__.py` de packages** : laissés en `.py` (vides) dans ce pilote ; décider au Lot 5
  s'ils restent `.py` (recommandé) ou sont compilés.
- **Suite de tests complète** : non relancée — **aucune source `.py` n'a été modifiée**
  (anti-régression satisfaite par construction ; `git diff` vide), et on évite de lancer pytest
  pendant que le serveur tourne (risque SAP 305 « User Already Logged In »).

## 7. Hygiène de livraison (vérifiée)

`git status` ne montre que les 3 nouveaux scripts ; **aucun artefact** généré n'est suivi :

- `build/` ignoré (`.gitignore` l.76-77) → couvre `build/compiled/*.pyd` **et** `build/cython_c/*.c` ;
- `*.pyd` (l.4), `__pycache__/` (l.2), `*.pyc` (l.6) ignorés ;
- aucun `.c`/`.pyd` déposé à côté des sources.

Recommandation belt-and-suspenders pour le build complet : ajouter une règle explicite `*.c`
au `.gitignore` (au cas où un futur script écrirait des `.c` hors `build/`).

## 8. Conclusion — **GO** (sous conditions)

La chaîne **Python 3.10.10 x64 + MSVC 14.44 + Cython 3.2.5 compile et produit des `.pyd`
fonctionnellement équivalents aux sources** sur les 3 patterns clés (service async, modèles
Pydantic v2, router FastAPI). Le seul blocage rencontré (annotation_typing) a un correctif
**simple, global et identifié**.

**Conditions à porter dans le build du Lot 5 (les ~163 fichiers) :**

1. `compiler_directives={'language_level':'3', 'annotation_typing': False}` — **non négociable**.
2. Build lancé sous environnement MSVC initialisé + `DISTUTILS_USE_SDK=1` (cf. `.bat`).
3. Garder les `__init__.py` et les migrations alembic en `.py`.
4. Avant généralisation : un test ciblé sur (a) un fichier `from __future__ import annotations`
   et (b) un cas Pydantic à forward-ref / `model_rebuild`.

**Effort estimé pour la généralisation (~160 fichiers)** :

- Script de build complet + intégration `package_compiled.ps1` : **0,5–1 j**.
- Itérations de compilation sur l'ensemble (modules à imports lourds, ordre, cas tordus
  type `email_matcher.py` ~150 Ko, `routes_graph.py` ~128 Ko) : **1–2 j**.
- Test de bout en bout sur VM Windows propre (venv 3.10.10 x64, sans aucune source métier) +
  lancement réel via `run.py` + uvicorn : **1 j**.
- **Total réaliste : 2,5 à 4 jours**, cohérent avec le « plusieurs jours » du SPEC.

---

### Annexes — fichiers produits (non commités)

- `scripts/build_cython_pilot.py` — build des 3 modules → `build/compiled/`.
- `scripts/build_cython_pilot.bat` — wrapper MSVC (`vcvars64` + `DISTUTILS_USE_SDK=1`).
- `scripts/smoke_test_pilot.py` — smoke-test `.pyd` vs source.

Rejouer : `scripts\build_cython_pilot.bat` puis `.venv\Scripts\python.exe scripts\smoke_test_pilot.py`.
