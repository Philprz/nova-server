#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/build_runtime_check.py — Lot 5, ETAPE 2/3 : STAGING DE VALIDATION RUNTIME.

But : assembler, HORS arborescence source, une staging ou CHAQUE module metier est
present UNIQUEMENT sous sa forme COMPILEE (.pyd), sans le .py a cote (sinon CPython
importerait le .py et la validation ne prouverait rien). On y ajoute le non-code et
les fichiers restes legitimement en .py (run.py, shim, alembic/, webhooks, __init__),
plus — POUR LA VALIDATION SEULEMENT, hors livraison — tests/ et les donnees runtime
(copies isolees des .db pour que les tests n'alterent jamais les bases reelles).

Cette staging sert a :
  - prouver que `from main import app` charge bien main.pyd (main.__file__ -> .pyd) ;
  - prouver le shim cython_pydantic_compat a l'echelle (3 modeles a methode-cyfunction) ;
  - faire tourner TestClient (sans bind de port) et pytest CONTRE les .pyd.

NE COMPILE RIEN, NE MODIFIE AUCUNE SOURCE, NE TOUCHE PAS au service live (port 8001).
Le contenu produit (build/runtime_check/) est gitignore (sous build/).

Difference avec scripts/package_compiled.ps1 (etape 3/3) : ce dernier produit la
LIVRAISON (sans tests/, sans donnees, avec garde-fou anti-fuite). Ici on fait
l'inverse cote inclusions : on AJOUTE tests/ et les donnees pour pouvoir valider.

Usage :
    .venv\\Scripts\\python.exe scripts\\build_runtime_check.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPILED = ROOT / "build" / "compiled"
STAGE = ROOT / "build" / "runtime_check"

# Packages metier : leurs __init__.py NE sont PAS compiles (decision pilote) et
# doivent etre copies pour que le package reste importable a cote des .pyd.
PKG_DIRS = [
    "auth", "auth/sap_session", "db", "managers", "models",
    "routes", "services", "services/packing",
    "services/transport", "services/transport/carriers",
    "utils", "workflow",
]

# Dossiers non-code recopies integralement (templates web, assets, migrations).
NONCODE_DIRS = ["templates", "static", "frontend", "alembic"]

# Donnees runtime — COPIES ISOLEES pour la validation (les tests ecrivent dans la
# staging, jamais dans les bases reelles du repo). Hors livraison.
DATA_DIRS = ["data"]
ROOT_DB_GLOBS = ["*.db"]

# Fichiers racine restes legitimement en .py (entrypoint + scheduler webhooks).
ROOT_PY_FILES = ["run.py", "register_webhook.py", "renew_webhook.py"]

# Fichiers racine non-code requis a l'execution / aux tests.
ROOT_OTHER_FILES = ["alembic.ini", ".env"]

# Le shim reste en .py dans scripts/ ; run.py l'expose en top-level via sys.path.
SHIM_REL = "scripts/cython_pydantic_compat.py"


def _ignore_junk(_dir, names):
    return [n for n in names if n in ("__pycache__", ".pytest_cache") or n.endswith((".pyc", ".pyo"))]


def _copytree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=_ignore_junk, dirs_exist_ok=True)


def main() -> int:
    if not COMPILED.is_dir():
        print(f"ERREUR : arbre compile absent : {COMPILED}. Lance d'abord le build Cython.")
        return 2

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    counts = {"pyd": 0, "init": 0, "rootpy": 0, "noncode": 0, "data": 0, "tests": 0, "other": 0}

    # 1. Arbre compile (.pyd) — copie integrale en preservant l'arbo des packages.
    for p in COMPILED.rglob("*.pyd"):
        rel = p.relative_to(COMPILED)
        dst = STAGE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        counts["pyd"] += 1

    # 2. __init__.py des packages (non compiles) — A COTE des .pyd, jamais le module .py.
    for d in PKG_DIRS:
        src = ROOT / d / "__init__.py"
        if src.exists():
            dst = STAGE / d / "__init__.py"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            counts["init"] += 1
        else:
            print(f"AVERTISSEMENT : __init__.py absent pour le package {d}")

    # 3. Modules racine restes en .py (run.py / webhooks).
    for f in ROOT_PY_FILES:
        src = ROOT / f
        if src.exists():
            shutil.copy2(src, STAGE / f)
            counts["rootpy"] += 1
        else:
            print(f"AVERTISSEMENT : fichier racine .py absent : {f}")

    # 3b. Shim (reste en .py dans scripts/).
    shim_src = ROOT / SHIM_REL
    if shim_src.exists():
        (STAGE / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(shim_src, STAGE / SHIM_REL)
        counts["rootpy"] += 1
    else:
        print(f"ERREUR : shim absent : {SHIM_REL}")
        return 2

    # 4. Dossiers non-code (templates/static/frontend/alembic).
    for d in NONCODE_DIRS:
        src = ROOT / d
        if src.is_dir():
            _copytree(src, STAGE / d)
            counts["noncode"] += 1
        else:
            print(f"AVERTISSEMENT : dossier non-code absent : {d}")

    # 5. Fichiers racine non-code (alembic.ini, .env).
    for f in ROOT_OTHER_FILES:
        src = ROOT / f
        if src.exists():
            shutil.copy2(src, STAGE / f)
            counts["other"] += 1
        else:
            print(f"AVERTISSEMENT : fichier racine absent : {f}")

    # 6. Donnees runtime (copies isolees) — VALIDATION SEULEMENT.
    for d in DATA_DIRS:
        src = ROOT / d
        if src.is_dir():
            _copytree(src, STAGE / d)
            counts["data"] += 1
    for g in ROOT_DB_GLOBS:
        for src in ROOT.glob(g):
            shutil.copy2(src, STAGE / src.name)
            counts["data"] += 1

    # 7. tests/ — VALIDATION SEULEMENT (hors livraison).
    tests_src = ROOT / "tests"
    if tests_src.is_dir():
        _copytree(tests_src, STAGE / "tests")
        counts["tests"] += 1

    # 8. Garde-fou : aucun .py metier ne doit ombrer un .pyd dans la staging.
    #    (un services/foo.py a cote de services/foo.*.pyd ferait importer le .py).
    shadows = []
    for pyd in STAGE.rglob("*.pyd"):
        # services/packing/box_catalog.cp310-win_amd64.pyd -> stem module = box_catalog
        stem = pyd.name.split(".")[0]
        sibling_py = pyd.parent / f"{stem}.py"
        if sibling_py.exists():
            shadows.append(str(sibling_py.relative_to(STAGE)))
    if shadows:
        print("ERREUR : des .py ombrent des .pyd dans la staging :")
        for s in shadows:
            print(f"   {s}")
        return 3

    pyd_total = sum(1 for _ in STAGE.rglob("*.pyd"))
    print("== staging de validation runtime ==")
    print(f"Staging : {STAGE}")
    print(f".pyd copies         : {counts['pyd']}  (verif sur disque : {pyd_total})")
    print(f"__init__.py packages: {counts['init']}")
    print(f"modules .py racine  : {counts['rootpy']}  (run.py, webhooks, shim)")
    print(f"dossiers non-code   : {counts['noncode']}  ({', '.join(NONCODE_DIRS)})")
    print(f"fichiers non-code   : {counts['other']}")
    print(f"jeux de donnees     : {counts['data']}  (copies isolees, hors livraison)")
    print(f"tests/              : {'oui' if counts['tests'] else 'NON'}  (hors livraison)")
    print("Garde-fou anti-ombrage .py/.pyd : OK (aucun .py metier a cote d'un .pyd)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
