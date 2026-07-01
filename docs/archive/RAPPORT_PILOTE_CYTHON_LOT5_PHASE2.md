# Rapport — Pilote Cython Lot 5, PHASE 2 (patterns non couverts + recette finale)

Référence : `SPEC_COMPILATION_RONDOT.md` (Lot 5) ; suite de `RAPPORT_PILOTE_CYTHON_LOT5.md`.
Branche : `prod/lot5-cython-pilot`. Toolchain inchangée et déjà validée :
**Python 3.10.10 x64 + MSVC 14.44.35207 (Build Tools 2022) + Cython 3.2.5**, build sous
`vcvars64.bat` + `DISTUTILS_USE_SDK=1`.

Objectif : lever les **4 patterns laissés ouverts par la phase 1** et produire une **recette
de build sans inconnue**, applicable aux ~160 fichiers. Aucune source du repo n'a été modifiée
(règle stricte) ; tous les artefacts sont sous `build/` (ignoré).

## 1. Échantillon retenu et justification

Un seul package concentre **les 4 patterns à la fois** → échantillon idéal, auto-suffisant
(ne dépend que de `pydantic`/`fastapi`, pas du reste de l'app) : **`services/packing/`**.

| Sous-module | Couvre |
|---|---|
| `box_catalog.py` | `from __future__ import annotations` (P1) ; modèle Pydantic `BoxSpec` (P2) avec **méthode ordinaire** `can_fit_item` |
| `packing_algorithm.py` | future-annotations (P1) ; modèles `FilledBox`/`PackingResult` avec champ **inter-module** `box_spec: BoxSpec` (P2 forward-ref) + méthodes ; **importe** `box_catalog` (P3) |
| `packing_service.py` | future-annotations (P1) ; importe `packing_algorithm` **et** `box_catalog` (P3, chaîne) |
| `__init__.py` | re-exporte les 3 sous-modules → support des **deux options** `__init__` (P4) |

Les 3 sous-modules font partie des **16 fichiers** `from __future__ import annotations` du repo.
Scripts livrés : `scripts/build_cython_phase2.py` (+`.bat`), `scripts/smoke_test_phase2.py`,
`scripts/cython_pydantic_compat.py`, `scripts/probe_fastapi_future.py` (+`.bat`),
`scripts/_scan_pydantic_methods.py`.

## 2. Résultats par pattern

### P1 — `from __future__ import annotations` → **fonctionne TEL QUEL** ✅
Les 3 sous-modules (tous en future-annotations) compilent en `.pyd` et s'importent sans aucun
traitement. Sous `annotation_typing=False`, Cython 3.2.5 n'évalue pas les annotations comme des
types C : que l'annotation soit une chaîne (future) ou un objet est indifférent.
**Aucune retouche source. 0 fichier concerné sur les 16.**

### P2 — Forward-refs / `model_rebuild` Pydantic v2 → **fonctionne TEL QUEL** ✅
- Aucun module du repo n'appelle explicitement `model_rebuild`/`update_forward_refs` (grep = 0).
- Le vrai cas présent est la **référence de type inter-module** `FilledBox.box_spec: BoxSpec` :
  sous future-annotations c'est la **chaîne** `"BoxSpec"` que Pydantic doit résoudre depuis les
  globals du module compilé. Vérifié : validation imbriquée `dict → BoxSpec` OK, et
  `FilledBox.model_rebuild(force=True)` renvoie `True` puis le modèle reste fonctionnel
  → les forward-refs se résolvent **identiquement** en `.pyd`. **Aucune retouche source.**

### P3 — Import croisé entre modules TOUS compilés (`.pyd ↔ .pyd`) → **fonctionne TEL QUEL** ✅
Chaîne `packing_service.pyd → packing_algorithm.pyd → box_catalog.pyd`, imports **relatifs**
(`from .box_catalog import …`) résolus entre binaires. Preuve d'identité d'objet :
`packing_algorithm.BoxSpec is box_catalog.BoxSpec` et idem depuis `packing_service`.
Condition : les `.pyd` doivent être placés dans l'**arborescence de package** correcte (déjà le
cas en prod). **Aucune retouche source.**

### P4 — `__init__.py` : compilé (.pyd) **vs** laissé en .py → **les DEUX marchent**, recommandation .py ✅
Testé en isolation sur les deux variantes, sous-modules en `.pyd` dans les deux cas :

| Variante | Résultat | Subtilité |
|---|---|---|
| (a) `__init__` **compilé** en `.pyd` | OK (import + re-exports accessibles) | Cython compile `__init__.py` sous le nom doté du **package** (`services.packing`) → produit un fichier `packing.<tag>.pyd` (init `PyInit_packing`). **Il faut le RENOMMER `__init__.<tag>.pyd`** et le placer **dans** le dossier du package. Sans ce renommage, Python ne le reconnaît pas comme initialiseur de package. |
| (b) `__init__` **laissé en `.py`** | OK (import + re-exports accessibles) | Aucune manipulation. Un `__init__.py` source qui ré-importe des sous-modules `.pyd` fonctionne sans réserve. |

**Recommandation : laisser les `__init__.py` en `.py`** pour le build complet (généralement
courts — imports/`__all__`, peu de logique « sensible » à protéger), ce qui supprime le piège de
renommage et simplifie le packaging. Compiler le `__init__` reste une option valable si un
`__init__` contient de la logique à masquer (alors : appliquer le renommage ci-dessus).

## 3. 🔴 DÉCOUVERTE phase 2 — méthodes ordinaires sur modèle Pydantic (cyfunction)

C'est **le seul vrai traitement** requis par le projet, non visible en phase 1.

**Symptôme** (à l'import du `.pyd`, avant tout réglage) :
```
PydanticUserError: A non-annotated attribute was detected:
  `can_fit_item = <cyfunction BoxSpec.can_fit_item ...>`. All model fields require a type annotation…
```
**Cause** : une **méthode ordinaire** d'un modèle Pydantic (ni `@property`, ni
`@classmethod/@staticmethod`, ni validateur décoré) devient, une fois compilée, une
`cython_function_or_method` (**cyfunction**). Or la metaclasse Pydantic
(`inspect_namespace`) ignore les fonctions via `default_ignored_types() =
(FunctionType, property, classmethod, staticmethod, …)` — et une cyfunction **n'est pas** un
`types.FunctionType`. Pydantic la prend donc pour un champ sans annotation et lève l'erreur.
> Pourquoi invisible en phase 1 : `pricing_models.py` n'a **que** des champs, des
> `field_validator` décorés et des `@property` — **aucune méthode ordinaire**.

**Ampleur mesurée** (`scripts/_scan_pydantic_methods.py`, AST sur tout le repo) :
- **155 modèles** Pydantic dans 146 fichiers ; **seulement 3 modèles dans 2 fichiers** définissent
  une méthode ordinaire → `BoxSpec` (`can_fit_item`), `FilledBox` (`can_add_item`, `add_item`),
  `PackingResult` (`build_summary`). **Blast radius minuscule.**

**Correctif retenu — shim global, ZÉRO modification des sources** :
`scripts/cython_pydantic_compat.py` ajoute aux `ignored_types` de Pydantic un **marqueur** dont
la metaclasse répond `True` à `isinstance(<cyfunction>, marqueur)` (détection par nom de type,
sans dépendre d'un module compilé préalable). Un appel `apply()` tout en haut de l'entrypoint
suffit ; **idempotent et inerte hors compilation** (un `.py` pur n'a pas de cyfunction).

> Alternative (si on refuse tout shim) : éditer **3 modèles** (sortir la méthode en fonction
> module, ou `model_config = ConfigDict(ignored_types=(...))`). Vu le périmètre (3 modèles), c'est
> faisable — mais le shim est plus sûr et **future-proof** (couvre tout modèle futur).

## 4. Sonde complémentaire — FastAPI + future-annotations + Cython → **OK** ✅

Dernier inconnu pour un build « sans surprise » : 4 routers du repo combinent
`from __future__ import annotations` **et** seraient compilés (`routes_packing`, `routes_shipping`,
`routes_intelligent_assistant`, `routes_sap_session`). La phase 1 n'avait testé un router que
**sans** future-annotations. Sous future-annotations, FastAPI résout les signatures via
`typing.get_type_hints()` sur des handlers devenus cyfunctions.

`scripts/probe_fastapi_future.py` génère un **fixture** router (Query/Depends à défaut, param de
chemin `int`, modèle de corps **avec méthode**), le compile, et compare le comportement HTTP
source vs `.pyd` via `TestClient` :

| Vérification | Résultat `.pyd` |
|---|---|
| `GET /hello` (Query défaut + `Depends`) | 200, valeurs identiques à la source |
| Param de chemin `int` (`/item/{item_id}`) | conversion + calcul OK |
| `POST /echo` corps Pydantic **+ méthode** (cyfunction, via shim) | 200, `shout()` OK |
| Validation `min_length` → **422** | préservée |

→ **FastAPI + future-annotations + Cython fonctionne**, sous réserve des 2 réglages connus
(`annotation_typing=False`, env MSVC) **+ le shim** pour les modèles à méthode.

## 5. Hygiène (vérifiée)

`git status` ne montre que des scripts. `build/` (l.76-77), `*.pyd` (l.4), `*.c` (sous `build/`),
`*.log` (l.29), `__pycache__/` (l.2) sont ignorés. **Aucun artefact** `.pyd`/`.c`/`build` suivi.

---

## 6. RECETTE DE BUILD FINALE (prête pour les ~160 fichiers)

**Directives de compilation (non négociables) :**
```python
cythonize(
    extensions,                       # une Extension par module, nom DOTÉ réel
    build_dir="build/cython_c",       # .c hors arbo source
    language_level=3,
    compiler_directives={
        "language_level": "3",
        "annotation_typing": False,   # CRITIQUE (phase 1) : sinon FastAPI/défauts cassent
    },
)
# Durcissement optionnel : Cython.Compiler.Options.docstrings = False (flag GLOBAL, pas une directive)
```

**Environnement de build (non négociable) :** lancer sous `vcvars64.bat` **+**
`set DISTUTILS_USE_SDK=1` (et `MSSdk=1`). Wrapper de référence : `scripts/build_cython_*.bat`.
> Nota : un avertissement `vswhere.exe non reconnu` peut apparaître ; sans effet dès lors que
> `DISTUTILS_USE_SDK=1` est posé (l'env MSVC est déjà chargé).

**Conventions de packaging :**
1. **Laisser les `__init__.py` en `.py`** (recommandé). Si compilation d'un `__init__` voulue :
   le renommer `__init__.<tag>.pyd` et le placer **dans** le dossier du package.
2. Conserver les `.pyd` dans l'**arborescence de packages** d'origine (imports relatifs `.pyd↔.pyd` OK).
3. Garder en `.py` : les `__init__.py`, `alembic/` et migrations, l'entrypoint `run.py`
   (charge le coffre + migrations **avant** d'importer l'app), et le shim de compat (voir 4.).

**Unique retouche transverse — le shim cyfunction (1 ligne dans 2 fichiers) :**
- déployer `cython_pydantic_compat.py` (ex. à la racine du projet, **laissé en `.py`**) ;
- en **toute première instruction** de `run.py` **et** du repli dev `main.py` :
  ```python
  import cython_pydantic_compat; cython_pydantic_compat.apply()
  ```
- Aucune autre modification de source. (Sinon : éditer les **3** modèles à méthode — au choix.)

**Aucune retouche source requise pour** : future-annotations (16 fichiers), forward-refs Pydantic,
imports croisés, routers FastAPI. Tout passe **tel quel** sous les directives ci-dessus.

## 7. Effort réactualisé

La phase 2 **réduit l'incertitude** : tous les patterns ouverts sont levés et la seule surprise
(cyfunction) a un correctif global d'une ligne et un périmètre de 3 modèles.

| Poste | Estimation |
|---|---|
| Script de build complet (énumération ~160 modules, exclusions `__init__`/alembic/`run.py`, ordre) + intégration packaging | 0,5–1 j |
| Itérations de compilation sur l'ensemble (gros modules à imports lourds : `email_matcher.py`, `routes_graph.py`, etc.) | 1–1,5 j |
| Branchement du shim dans `run.py`/`main.py` + lancement réel `run.py`+uvicorn + suite pytest sur VM Windows propre (venv 3.10.10 x64, sans sources métier) | 1–1,5 j |
| **Total réaliste** | **2,5 à 4 jours** (confirmé, incertitude basse) |

## 8. Conclusion — **GO confirmé, sans inconnue résiduelle**

Les 4 patterns ouverts par la phase 1 fonctionnent **tels quels** sous les 2 réglages déjà connus.
La seule découverte (méthodes ordinaires → cyfunction non reconnue par Pydantic) est **cernée**
(3 modèles), **corrigée globalement** par un shim d'une ligne, et **validée** y compris en contexte
FastAPI. La recette du §6 est prête à appliquer aux ~160 fichiers.

---

### Annexes — fichiers produits (versionnés, hors artefacts de build)

- `scripts/build_cython_phase2.py` / `.bat` — compile `services/packing/` (3 sous-modules + 2
  variantes d'`__init__`) → `build/phase2/`.
- `scripts/smoke_test_phase2.py` — lève P1–P4 en sous-process isolés ; compare `.pyd` ↔ source.
- `scripts/cython_pydantic_compat.py` — **shim** cyfunction ↔ Pydantic (à déployer en prod).
- `scripts/probe_fastapi_future.py` / `.bat` — sonde FastAPI + future-annotations + Cython.
- `scripts/_scan_pydantic_methods.py` — mesure d'ampleur (modèles à méthode ordinaire).

Rejouer : `scripts\build_cython_phase2.bat` puis
`.venv\Scripts\python.exe scripts\smoke_test_phase2.py` ; et `scripts\probe_fastapi_future.bat`.
