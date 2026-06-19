#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/build_cython_phase2.py — PILOTE Lot 5, PHASE 2 (cf. SPEC_COMPILATION_RONDOT.md)

Objectif : lever les 4 patterns NON couverts par la phase 1, sur UN echantillon
cible et auto-suffisant : le package `services/packing/` (3 sous-modules + __init__).
Ce package est ideal car il combine, en un seul endroit :
  - Pattern 1 : `from __future__ import annotations` dans les 3 sous-modules
                (box_catalog, packing_algorithm, packing_service font partie des
                16 fichiers du repo concernes).
  - Pattern 2 : modeles Pydantic v2 avec references de type INTER-MODULES
                (`FilledBox.box_spec: BoxSpec`, champs `BoxType`) -> sous
                `from __future__ import annotations`, ces annotations sont des
                CHAINES que Pydantic doit resoudre (mecanisme des forward-refs /
                `model_rebuild`).
  - Pattern 3 : chaine d'imports packing_service -> packing_algorithm ->
                box_catalog (tous compiles) -> import croise .pyd <-> .pyd.
  - Pattern 4 : un `__init__.py` qui re-exporte les sous-modules -> on teste les
                DEUX options (compile en .pyd / laisse en .py source).

Ne modifie AUCUNE source .py du repo. Tous les artefacts vont sous build/.

Sorties :
  build/phase2/cython_c/      .c intermediaires (hors arbo source)
  build/phase2/obj/           objets C intermediaires
  build/phase2/pyd/services/packing/*.pyd   les .pyd bruts (incl. __init__.pyd)
  build/phase2/variant_init_pyd/   arbre package avec __init__.pyd compile
  build/phase2/variant_init_src/   arbre package avec __init__.py source (copie)

Usage (racine du repo, sous environnement MSVC + DISTUTILS_USE_SDK=1) :
    scripts\\build_cython_phase2.bat
ou directement (si MSVC deja charge) :
    .venv\\Scripts\\python.exe scripts\\build_cython_phase2.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "services" / "packing"
BUILD = ROOT / "build" / "phase2"
CTMP = BUILD / "cython_c"
TEMP = BUILD / "obj"
PYD = BUILD / "pyd"                       # arbo brute des .pyd produits
VAR_INIT_PYD = BUILD / "variant_init_pyd"  # variante (a) : __init__ compile
VAR_INIT_SRC = BUILD / "variant_init_src"  # variante (b) : __init__ en .py

# Sous-modules a compiler (nom dote REEL = emplacement dans l'arbo de staging).
SUBMODULES = [
    "services.packing.box_catalog",
    "services.packing.packing_algorithm",
    "services.packing.packing_service",
]
# Le package init, compile a part : source = __init__.py, nom dote = le PACKAGE
# lui-meme (services.packing) -> Cython genere PyInit_packing et un .pyd nomme
# __init__ a placer dans le dossier du package.
INIT_DOTTED = "services.packing"


def _src_for(dotted: str) -> Path:
    """services.packing.box_catalog -> <root>/services/packing/box_catalog.py"""
    return ROOT / (dotted.replace(".", "/") + ".py")


def main() -> int:
    import Cython
    from setuptools import Extension
    from setuptools.dist import Distribution
    from Cython.Build import cythonize

    bits = 64 if sys.maxsize > 2**32 else 32
    print("== build_cython_phase2 ==")
    print(f"Cython {Cython.__version__} | Python {sys.version.split()[0]} ({bits}-bit)")
    print(f"Package cible : {PKG_DIR.relative_to(ROOT)}")

    # Verifier les sources.
    targets = []  # (dotted, src_path, is_init)
    for d in SUBMODULES:
        p = _src_for(d)
        if not p.exists():
            print(f"ERREUR : source introuvable : {p}")
            return 2
        targets.append((d, p, False))
    init_src = PKG_DIR / "__init__.py"
    if not init_src.exists():
        print(f"ERREUR : __init__.py introuvable : {init_src}")
        return 2
    targets.append((INIT_DOTTED, init_src, True))
    for d, p, is_init in targets:
        tag = "  (__init__)" if is_init else ""
        print(f"  cible : {d}{tag}  ({p.stat().st_size} octets)")

    # Nettoyage.
    for x in (CTMP, TEMP, PYD, VAR_INIT_PYD, VAR_INIT_SRC):
        if x.exists():
            shutil.rmtree(x)
        x.mkdir(parents=True, exist_ok=True)

    # Une Extension par cible. Le nom DOTE pilote l'arbo de sortie et l'init.
    extensions = [Extension(d, [str(p)]) for d, p, _ in targets]

    ext_modules = cythonize(
        extensions,
        build_dir=str(CTMP),
        language_level=3,
        compiler_directives={
            "language_level": "3",
            # CRITIQUE (valide phase 1) : sinon Cython type-check les annotations
            # PEP 484 et casse FastAPI / les defauts non conformes au type annote.
            "annotation_typing": False,
        },
        annotate=False,
        quiet=False,
    )

    dist = Distribution({"name": "nova_cython_phase2", "ext_modules": ext_modules})
    cmd = dist.get_command_obj("build_ext")
    cmd.build_lib = str(PYD)
    cmd.build_temp = str(TEMP)
    cmd.inplace = 0
    cmd.ensure_finalized()
    cmd.run()

    produced = sorted(PYD.rglob("*.pyd"))
    print("\n== .pyd produits ==")
    for pyd in produced:
        print(f"  {pyd.relative_to(BUILD)}  ({pyd.stat().st_size} octets)")
    if len(produced) != len(targets):
        print(f"ERREUR : {len(produced)} .pyd produits, {len(targets)} attendus")
        return 1

    # ── Staging des deux variantes ────────────────────────────────────────────
    # Les .pyd des 3 sous-modules sont communs aux deux variantes ; seule la
    # gestion du __init__ change.
    #
    # SUBTILITE Cython/CPython sur le __init__ : compile avec le nom dote
    # `services.packing`, Cython produit un fichier `packing.<tag>.pyd` (place a
    # PYD/services/, init = PyInit_packing) — c.-a-d. la forme d'un MODULE
    # `services.packing`, pas d'un package. Pour qu'il serve d'initialiseur de
    # PACKAGE, il faut le RENOMMER `__init__.<tag>.pyd` et le placer DANS le
    # dossier `services/packing/`. CPython, important `services.packing`, attend
    # justement `PyInit_packing` (dernier composant du nom dote) pour un
    # `__init__.*.pyd` situe dans le repertoire `packing/` -> correspondance OK.
    pkg_built = PYD / "services" / "packing"
    sub_pyds = sorted(pkg_built.glob("*.pyd"))  # box_catalog / packing_algorithm / packing_service
    init_built = sorted((PYD / "services").glob("packing.*.pyd"))  # le __init__ compile
    if len(sub_pyds) != 3 or len(init_built) != 1:
        print(f"ERREUR : staging inattendu (sub={len(sub_pyds)}, init={len(init_built)})")
        return 1
    init_pyd = init_built[0]
    # packing.cp310-win_amd64.pyd -> __init__.cp310-win_amd64.pyd
    init_target_name = "__init__." + init_pyd.name.split(".", 1)[1]

    def _stage(dest_root: Path, with_init_pyd: bool) -> None:
        pkg = dest_root / "services" / "packing"
        pkg.mkdir(parents=True, exist_ok=True)
        # `services` : package namespace minimal (init vide) pour l'isolation.
        (dest_root / "services" / "__init__.py").write_text(
            "# staging package (test phase 2) — volontairement vide\n", encoding="utf-8"
        )
        for p in sub_pyds:
            shutil.copy2(p, pkg / p.name)
        if with_init_pyd:
            shutil.copy2(init_pyd, pkg / init_target_name)
        else:
            # Variante (b) : __init__.py SOURCE (re-exporte les sous-modules .pyd).
            shutil.copy2(init_src, pkg / "__init__.py")

    _stage(VAR_INIT_PYD, with_init_pyd=True)
    _stage(VAR_INIT_SRC, with_init_pyd=False)

    print("\n== variantes de staging ==")
    print(f"  (a) __init__ compile  : {VAR_INIT_PYD.relative_to(BUILD)}/services/packing/")
    for p in sorted((VAR_INIT_PYD / 'services' / 'packing').iterdir()):
        print(f"        {p.name}")
    print(f"  (b) __init__ en .py   : {VAR_INIT_SRC.relative_to(BUILD)}/services/packing/")
    for p in sorted((VAR_INIT_SRC / 'services' / 'packing').iterdir()):
        print(f"        {p.name}")

    print("\nOK : build phase 2 termine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
