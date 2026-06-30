#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/build_cython_pilot.py — PILOTE Lot 5 (cf. SPEC_COMPILATION_RONDOT.md)

Objectif : valider la chaine de build Cython sur un ECHANTILLON representatif
(3 modules), PAS sur tout le projet. Ne modifie AUCUNE source .py.

- Compile 3 modules .py -> .pyd via cythonize (language_level=3).
- Les .c intermediaires sont generes hors de l'arborescence source (build/cython_c).
- Les .pyd sont places dans build/compiled/ en preservant l'arbo des packages
  (build/compiled/services/..., build/compiled/routes/...).

Usage (racine du repo, venv actif) :
    .venv\\Scripts\\python.exe scripts\\build_cython_pilot.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
COMPILED = BUILD / "compiled"     # destination des .pyd (arbo packages preservee)
CTMP = BUILD / "cython_c"         # .c generes par Cython (hors arbo source)
TEMP = BUILD / "obj"              # objets intermediaires du compilateur C

# Echantillon representatif des patterns a risque :
#  (a) service de logique pure  : classe + methodes async + petit modele Pydantic
#  (b) modeles Pydantic v2      : Field + field_validator(mode='before') + Enum
#  (c) router FastAPI           : APIRouter + decorateurs + handlers async + import inter-module
MODULES = [
    "services/currency_service.py",
    "services/pricing_models.py",
    "routes/routes_products.py",
]


def module_name(rel_path: str) -> str:
    """services/currency_service.py -> services.currency_service"""
    return rel_path[:-3].replace("/", ".").replace("\\", ".")


def main() -> int:
    import Cython
    from setuptools import Extension
    from setuptools.dist import Distribution
    from Cython.Build import cythonize

    bits = 64 if sys.maxsize > 2**32 else 32
    print(f"== build_cython_pilot ==")
    print(f"Cython {Cython.__version__} | Python {sys.version.split()[0]} ({bits}-bit)")
    print(f"Racine repo : {ROOT}")

    # Verifier l'existence des sources avant toute action.
    sources = []
    for rel in MODULES:
        p = ROOT / rel
        if not p.exists():
            print(f"ERREUR : source introuvable : {rel}")
            return 2
        sources.append((rel, p))
        print(f"  cible : {rel}  ({p.stat().st_size} octets)")

    # Nettoyage des sorties precedentes (sans toucher aux sources).
    for d in (COMPILED, CTMP, TEMP):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # Une Extension par module ; le nom pointe (dote) fixe l'arbo de sortie.
    extensions = [
        Extension(module_name(rel), [str(path)])
        for rel, path in sources
    ]

    # Option de durcissement (Lot 5) : stripper les docstrings du binaire.
    # Ce n'est PAS une compiler-directive par fichier mais un flag global Cython.
    # Laisse a True (defaut) pour le pilote ; passer a False au build de prod.
    #   from Cython.Compiler import Options as _Opt; _Opt.docstrings = False

    # Traduction .py -> .c (les .c vont dans build_dir = CTMP, PAS a cote des sources).
    ext_modules = cythonize(
        extensions,
        build_dir=str(CTMP),
        language_level=3,
        compiler_directives={
            "language_level": "3",
            # CRITIQUE : par defaut Cython interprete les annotations PEP 484
            # (ex. `q: Optional[str]`) comme des declarations de type C et
            # type-check les valeurs par defaut. Cela casse FastAPI
            # (`Query(...)`, `Depends(...)`) et tout code ou la valeur par
            # defaut n'est pas du type annote. On DESACTIVE ce comportement.
            "annotation_typing": False,
        },
        annotate=False,
        quiet=False,
    )

    # Compilation C -> .pyd via la commande build_ext de setuptools (localise MSVC seul).
    dist = Distribution({"name": "nova_cython_pilot", "ext_modules": ext_modules})
    cmd = dist.get_command_obj("build_ext")
    cmd.build_lib = str(COMPILED)
    cmd.build_temp = str(TEMP)
    cmd.inplace = 0
    cmd.ensure_finalized()
    cmd.run()

    print("\n== .pyd produits ==")
    produced = sorted(COMPILED.rglob("*.pyd"))
    for pyd in produced:
        print(f"  {pyd.relative_to(ROOT)}  ({pyd.stat().st_size} octets)")

    if len(produced) != len(MODULES):
        print(f"ERREUR : {len(produced)} .pyd produits, {len(MODULES)} attendus")
        return 1

    print("\nOK : build du pilote termine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
