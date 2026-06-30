#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/build_cython_full.py — Lot 5, ETAPE 1/3 : BUILD CYTHON COMPLET.

Compile TOUT le code metier en .pyd selon la recette validee (phases 1+2 du
pilote, cf. SPEC_COMPILATION_RONDOT.md). Cette etape NE fait QUE compiler et
RAPPORTER : elle ne supprime aucune source, ne modifie aucun .py d'origine et
ne touche pas au demarrage runtime.

RECETTE (non negociable) :
  - compiler_directives = {'language_level': '3', 'annotation_typing': False}
    annotation_typing=False est CRITIQUE : sinon Cython type-check les
    annotations PEP 484 et casse FastAPI (Query/Depends/...) et les defauts
    non conformes au type annote.
  - .c generes dans un build_dir HORS arborescence source (build/cython_c).
  - .pyd ecrits dans build/compiled/ en PRESERVANT l'arborescence des packages.
  - Durcissement : Options.docstrings = False (flag GLOBAL Cython, pas une
    directive par fichier) -> strip des docstrings du binaire.
  - Build sous vcvars64 + DISTUTILS_USE_SDK=1 (assure par le wrapper .bat).

PERIMETRE A COMPILER :
  - Repertoires metier : services/, routes/, managers/, models/, db/, auth/,
    utils/, workflow/  (recursif, sous-packages inclus).
  - Modules racine : main.py, sap_mcp.py, salesforce_mcp.py.

NE SONT PAS COMPILES (restent en .py, hors perimetre de ce script) :
  - __init__.py de tous les packages (decision pilote : laisses en source).
  - run.py + scripts/cython_pydantic_compat.py (entrypoint + shim).
  - alembic/, register_webhook.py, renew_webhook.py, tests/, scripts/, one-shots.

STRATEGIE DE BUILD : chaque module est compile INDIVIDUELLEMENT (cythonize +
build_ext isole, dans un try/except). Un echec sur un module n'interrompt pas
les autres : tous les echecs sont collectes et remontes en fin de rapport avec
le module concerne et l'erreur. AUCUN contournement silencieux.

Usage (racine du repo, sous environnement MSVC x64 + DISTUTILS_USE_SDK=1) :
    scripts\\build_cython_full.bat
ou directement (si MSVC deja charge dans le shell) :
    .venv\\Scripts\\python.exe scripts\\build_cython_full.py
"""
import io
import shutil
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
COMPILED = BUILD / "compiled"     # destination des .pyd (arbo packages preservee)
CTMP = BUILD / "cython_c"         # .c generes par Cython (hors arbo source)
TEMP = BUILD / "obj"              # objets intermediaires du compilateur C

# Repertoires metier a compiler recursivement.
PKG_DIRS = [
    "services", "routes", "managers", "models",
    "db", "auth", "utils", "workflow",
]
# Modules racine a compiler.
ROOT_MODULES = ["main.py", "sap_mcp.py", "salesforce_mcp.py"]

# Modules racine OPTIONNELS : compiles seulement s'ils existent, sans
# avertissement bruyant en leur absence (cas legitime). _vault_key.py (Lot 2/2b)
# porte la cle maitre embarquee ; il est genere AU BUILD de livraison par
# scripts/generate_vault_key_module.py et gitignore. Present -> compile en
# _vault_key.pyd et le total de modules passe a 112 ; absent (dev) -> ignore.
OPTIONAL_ROOT_MODULES = ["_vault_key.py"]


def module_name(rel_path: Path) -> str:
    """services/packing/box_catalog.py -> services.packing.box_catalog"""
    return rel_path.with_suffix("").as_posix().replace("/", ".")


def collect_sources() -> list[Path]:
    """Liste des sources (chemins relatifs a ROOT) du perimetre, __init__.py exclus."""
    found: list[Path] = []
    for d in PKG_DIRS:
        base = ROOT / d
        if not base.is_dir():
            print(f"AVERTISSEMENT : repertoire de perimetre absent : {d}")
            continue
        for p in sorted(base.rglob("*.py")):
            if p.name == "__init__.py":
                continue          # decision pilote : __init__ laisses en .py
            found.append(p.relative_to(ROOT))
    for m in ROOT_MODULES:
        p = ROOT / m
        if p.exists():
            found.append(p.relative_to(ROOT))
        else:
            print(f"AVERTISSEMENT : module racine absent : {m}")
    for m in OPTIONAL_ROOT_MODULES:
        p = ROOT / m
        if p.exists():
            found.append(p.relative_to(ROOT))
            print(f"INFO : module optionnel present, sera compile : {m}")
        else:
            print(f"INFO : module optionnel absent (ignore, normal en dev) : {m}")
    return found


def main() -> int:
    import Cython
    from Cython.Build import cythonize
    from Cython.Compiler import Options
    from setuptools import Extension
    from setuptools.dist import Distribution

    # Durcissement GLOBAL : pas de docstrings dans les binaires produits.
    Options.docstrings = False

    DIRECTIVES = {
        "language_level": "3",
        "annotation_typing": False,
    }

    # Console Windows en cp1252 : les messages d'erreur Cython peuvent contenir
    # des caracteres non encodables (emojis dans des f-strings du source). On
    # rend stdout/stderr tolerants pour ne PAS masquer le rapport d'echecs.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    bits = 64 if sys.maxsize > 2 ** 32 else 32
    print("== build_cython_full (Lot 5, etape 1/3) ==")
    print(f"Cython {Cython.__version__} | Python {sys.version.split()[0]} ({bits}-bit)")
    print(f"Racine repo : {ROOT}")
    print(f"Recette : directives={DIRECTIVES} | Options.docstrings={Options.docstrings}")

    sources = collect_sources()
    print(f"\nModules a compiler : {len(sources)}")

    # Nettoyage des sorties precedentes (sans JAMAIS toucher aux sources).
    for d in (COMPILED, CTMP, TEMP):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    compiled_ok: list[tuple[str, Path]] = []
    failures: list[tuple[str, str]] = []      # (module dote, message d'erreur)

    for i, rel in enumerate(sources, 1):
        dotted = module_name(rel)
        src = ROOT / rel
        print(f"[{i:3}/{len(sources)}] {dotted} ... ", end="", flush=True)
        log = io.StringIO()
        try:
            ext = Extension(dotted, [str(src)])
            with redirect_stdout(log), redirect_stderr(log):
                ext_modules = cythonize(
                    [ext],
                    build_dir=str(CTMP),
                    language_level=3,
                    compiler_directives=DIRECTIVES,
                    annotate=False,
                    quiet=True,
                )
                dist = Distribution({"name": "nova_cython_full", "ext_modules": ext_modules})
                cmd = dist.get_command_obj("build_ext")
                cmd.build_lib = str(COMPILED)
                cmd.build_temp = str(TEMP)
                cmd.inplace = 0
                cmd.ensure_finalized()
                cmd.run()
            # Verifier qu'un .pyd a bien ete produit pour ce module.
            expected_dir = COMPILED / rel.parent
            produced = list(expected_dir.glob(rel.stem + ".*.pyd")) if expected_dir.exists() else []
            if not produced:
                raise RuntimeError("aucun .pyd produit (build silencieux ?)")
            compiled_ok.append((dotted, produced[0]))
            print("OK")
        except SystemExit as e:
            # setuptools/distutils leve parfois SystemExit sur erreur de compilation.
            tail = log.getvalue().strip().splitlines()[-15:]
            msg = f"SystemExit({e.code})\n" + "\n".join(tail)
            failures.append((dotted, msg))
            print("ECHEC")
        except Exception:
            tb = traceback.format_exc().strip().splitlines()
            tail_log = log.getvalue().strip().splitlines()[-10:]
            msg = "\n".join(tb[-8:])
            if tail_log:
                msg += "\n  --- sortie compilateur (extrait) ---\n  " + "\n  ".join(tail_log)
            failures.append((dotted, msg))
            print("ECHEC")

    # ── Rapport ───────────────────────────────────────────────────────────────
    produced_all = sorted(COMPILED.rglob("*.pyd"))
    total_bytes = sum(p.stat().st_size for p in produced_all)
    lines = []
    lines.append("=" * 70)
    lines.append("RAPPORT BUILD CYTHON COMPLET")
    lines.append("=" * 70)
    lines.append(f"Recette appliquee : {DIRECTIVES} | docstrings={Options.docstrings}")
    lines.append(f"Modules cibles    : {len(sources)}")
    lines.append(f"Compiles OK       : {len(compiled_ok)}")
    lines.append(f"Echecs            : {len(failures)}")
    lines.append(f".pyd sur disque   : {len(produced_all)} ({total_bytes/1024:.0f} Ko) sous {COMPILED.relative_to(ROOT)}/")
    if failures:
        lines.append("")
        lines.append(f"--- DETAIL DES {len(failures)} ECHEC(S) ---")
        for dotted, msg in failures:
            lines.append("")
            lines.append(f"### {dotted}")
            for line in msg.splitlines():
                lines.append(f"    {line}")
    report = "\n".join(lines)

    # Rapport durable en UTF-8 (survit a l'encodage console).
    report_path = BUILD / "build_cython_full_report.txt"
    report_path.write_text(report, encoding="utf-8")

    print("\n" + report)
    print(f"\n(Rapport complet UTF-8 : {report_path.relative_to(ROOT)})")
    print("\n" + "=" * 70)
    if failures:
        print(f"BUILD INCOMPLET : {len(failures)} echec(s) — voir detail ci-dessus.")
        return 1
    print("BUILD COMPLET OK : tous les modules du perimetre ont ete compiles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
