#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/smoke_test_phase2.py — Smoke-test du pilote Cython PHASE 2 (Lot 5).

Leve les 4 patterns non couverts par la phase 1, sur le package services/packing/
compile en .pyd (cf. build_cython_phase2.py). Compare le comportement compile au
comportement source.

Architecture : pour garantir une ISOLATION stricte des imports (pas de melange
source .py / binaire .pyd via le cache de modules), chaque cas tourne dans un
SOUS-PROCESS dedie. Le process parent orchestre 3 enfants et compare :
  --mode source            : importe le package SOURCE (.py) depuis la racine repo
  --mode variant_init_pyd  : importe le package STAGE avec __init__.pyd compile
  --mode variant_init_src  : importe le package STAGE avec __init__.py source
Chaque enfant emet une ligne JSON prefixee par RESULT_JSON: decrivant ses
observations. Le parent agrege et conclut OUI/NON par pattern.

Usage : .venv\\Scripts\\python.exe scripts\\smoke_test_phase2.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "phase2"
VAR_INIT_PYD = BUILD / "variant_init_pyd"
VAR_INIT_SRC = BUILD / "variant_init_src"
MARKER = "RESULT_JSON:"


# ===========================================================================
# Cote ENFANT : importe le package et collecte des observations reproductibles
# ===========================================================================
def _kind(path: str) -> str:
    return "pyd" if str(path).endswith(".pyd") else ("py" if str(path).endswith(".py") else "?")


def child_collect(mode: str) -> dict:
    # Isolation du sys.path selon le mode.
    if mode == "source":
        root = ROOT
    elif mode == "variant_init_pyd":
        root = VAR_INIT_PYD
    elif mode == "variant_init_src":
        root = VAR_INIT_SRC
    else:
        raise SystemExit(f"mode inconnu : {mode}")
    # On insere UNIQUEMENT le root choisi. On ne met JAMAIS la racine repo pour
    # les variantes -> le seul package `services` importable est celui stage.
    sys.path.insert(0, str(root))

    obs = {"mode": mode, "root": str(root)}

    # --- shim de compat Cython<->Pydantic (decouverte phase 2 : methodes des
    #     modeles -> cyfunctions non reconnues par Pydantic). Inerte sur source. ---
    import cython_pydantic_compat  # voisin dans scripts/ (cwd = scripts au lancement)
    obs["compat_applied"] = cython_pydantic_compat.apply()

    # --- import du package (Pattern 4 : __init__ .pyd vs .py ; Pattern 1 import) ---
    import importlib
    pkg = importlib.import_module("services.packing")
    box_catalog = importlib.import_module("services.packing.box_catalog")
    packing_algorithm = importlib.import_module("services.packing.packing_algorithm")
    packing_service = importlib.import_module("services.packing.packing_service")

    obs["files"] = {
        "__init__": _kind(getattr(pkg, "__file__", "")),
        "box_catalog": _kind(box_catalog.__file__),
        "packing_algorithm": _kind(packing_algorithm.__file__),
        "packing_service": _kind(packing_service.__file__),
    }
    # Pattern 4 : les re-exports du __init__ sont-ils accessibles ?
    obs["init_reexports_ok"] = all(
        hasattr(pkg, n)
        for n in ("PackingService", "get_packing_service", "FirstFitDecreasingPacker",
                  "BOX_CATALOG", "BoxSpec", "BoxType")
    )

    # Pattern 3 : packing_algorithm a-t-il bien importe box_catalog (compile),
    # et est-ce le MEME objet que le module charge (import croise resolu) ?
    obs["xmod_same_boxspec"] = (packing_algorithm.BoxSpec is box_catalog.BoxSpec)
    obs["xmod_same_boxtype"] = (packing_service.BoxSpec is box_catalog.BoxSpec)

    # --- Pattern 2 : Pydantic v2 + reference de type INTER-MODULE sous
    #     `from __future__ import annotations` (annotation = chaine a resoudre) ---
    BoxSpec = box_catalog.BoxSpec
    BoxType = box_catalog.BoxType
    FilledBox = packing_algorithm.FilledBox
    PackingItem = packing_algorithm.PackingItem

    spec = BoxSpec(type=BoxType.M, label="Colis M", length_cm=60.0, width_cm=40.0,
                   height_cm=40.0, max_weight_kg=25.0)
    # FilledBox.box_spec est annote `BoxSpec` (autre module) -> resolution forward-ref.
    fb = FilledBox(box_spec=spec)
    fb.add_item("REF-1", 2.0, 5000.0)
    obs["filledbox_dump"] = fb.model_dump(mode="json")

    # Forcer la re-resolution des forward-refs (ce que ferait model_rebuild en cas
    # de reference non resolvable a la creation de la classe). Doit reussir.
    rebuild_ret = FilledBox.model_rebuild(force=True)
    obs["model_rebuild_force"] = rebuild_ret  # True / None selon resolution
    # Apres rebuild, le modele reste fonctionnel et valide toujours le sous-modele.
    fb2 = FilledBox(box_spec=spec)
    obs["post_rebuild_ok"] = isinstance(fb2.box_spec, BoxSpec)
    # La validation imbriquee fonctionne (dict -> BoxSpec) : preuve que l'annotation
    # chaine "BoxSpec" a bien ete resolue vers la vraie classe.
    fb3 = FilledBox(box_spec={"type": "S", "label": "Colis S", "length_cm": 30.0,
                              "width_cm": 20.0, "height_cm": 20.0, "max_weight_kg": 10.0})
    obs["nested_validation_ok"] = isinstance(fb3.box_spec, BoxSpec) and fb3.box_spec.type == BoxType.S

    # --- Comportement metier : FFD packer (doit etre IDENTIQUE source vs compile) ---
    Packer = packing_algorithm.FirstFitDecreasingPacker
    items = [
        PackingItem(item_code="A", weight_kg=3.0, length_cm=20, width_cm=15, height_cm=10, quantity=4),
        PackingItem(item_code="B", weight_kg=12.0, length_cm=50, width_cm=30, height_cm=30, quantity=1),
        PackingItem(item_code="C", weight_kg=0.5, length_cm=10, width_cm=10, height_cm=10, quantity=10),
    ]
    res = Packer().pack(items)
    obs["pack_result"] = {
        "box_count": res.box_count,
        "total_weight_kg": res.total_weight_kg,
        "total_volume_m3": res.total_volume_m3,
        "labels": sorted(p.label for p in res.packages),
        "summary_lines": res.summary.count("\n"),
    }

    # PackingService est constructible (sans toucher la DB) -> Pattern 1/3 valides
    # jusqu'au service de plus haut niveau.
    svc = packing_service.PackingService()
    obs["service_constructible"] = svc is not None and hasattr(svc, "suggest_packages")

    return obs


# ===========================================================================
# Cote PARENT : orchestre les enfants et conclut
# ===========================================================================
def run_child(mode: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", mode],
        capture_output=True, text=True, cwd=str(ROOT / "scripts"),
    )
    line = None
    for ln in proc.stdout.splitlines():
        if ln.startswith(MARKER):
            line = ln[len(MARKER):]
            break
    if line is None:
        print(f"  [FAIL] enfant {mode} : pas de RESULT_JSON")
        print("  --- stdout ---\n" + proc.stdout)
        print("  --- stderr ---\n" + proc.stderr)
        return {"mode": mode, "error": True}
    return json.loads(line)


def main() -> int:
    print(f"== smoke_test_phase2 ==  Python {sys.version.split()[0]}")
    if not VAR_INIT_PYD.exists() or not VAR_INIT_SRC.exists():
        print("ERREUR : build/phase2 introuvable. Lance d'abord build_cython_phase2.(bat)")
        return 2

    src = run_child("source")
    va = run_child("variant_init_pyd")
    vb = run_child("variant_init_src")
    if any(o.get("error") for o in (src, va, vb)):
        return 1

    fails = []

    def check(label, cond):
        print(f"  [{'OK ' if cond else 'FAIL'}] {label}")
        if not cond:
            fails.append(label)

    print("\n[Pattern 4] __init__.py : compile (.pyd) vs source (.py)")
    print(f"  variante (a) fichiers : {va['files']}")
    print(f"  variante (b) fichiers : {vb['files']}")
    check("(a) __init__ compile en .pyd, sous-modules .pyd, import OK",
          va["files"]["__init__"] == "pyd" and va["files"]["box_catalog"] == "pyd")
    check("(a) re-exports du __init__.pyd accessibles", va["init_reexports_ok"])
    check("(b) __init__ laisse en .py, sous-modules .pyd, import OK",
          vb["files"]["__init__"] == "py" and vb["files"]["box_catalog"] == "pyd")
    check("(b) re-exports du __init__.py accessibles", vb["init_reexports_ok"])

    print("\n[Pattern 3] import croise entre modules TOUS compiles (.pyd <-> .pyd)")
    for o in (va, vb):
        check(f"[{o['mode']}] packing_algorithm.pyd voit box_catalog.pyd (meme BoxSpec)",
              o["xmod_same_boxspec"])
        check(f"[{o['mode']}] packing_service.pyd voit box_catalog.pyd (meme BoxSpec)",
              o["xmod_same_boxtype"])

    print("\n[Pattern 1] from __future__ import annotations (3 sous-modules)")
    for o in (va, vb):
        # Le seul fait que box_catalog/packing_algorithm/packing_service se chargent
        # et s'instancient prouve que le futur-annotations passe TEL QUEL en .pyd.
        check(f"[{o['mode']}] modules future-annotations charges + modeles instancies",
              o["service_constructible"] and o["nested_validation_ok"])

    print("\n[Pattern 2] forward-refs Pydantic v2 inter-modules + model_rebuild")
    for o in (va, vb):
        check(f"[{o['mode']}] validation imbriquee BoxSpec resolue (annotation chaine -> classe)",
              o["nested_validation_ok"])
        check(f"[{o['mode']}] FilledBox.model_rebuild(force=True) OK",
              o["model_rebuild_force"] in (True, None) and o["post_rebuild_ok"])

    print("\n[Equivalence] comportement compile == source")
    for o in (va, vb):
        check(f"[{o['mode']}] FFD pack() identique a la source",
              o["pack_result"] == src["pack_result"])
        check(f"[{o['mode']}] FilledBox.model_dump identique a la source",
              o["filledbox_dump"] == src["filledbox_dump"])

    print("\n== bilan ==")
    if fails:
        print(f"ECHEC : {len(fails)} verification(s) en erreur")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("SUCCES : les 4 patterns sont leves ; .pyd == source.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--child":
        try:
            result = child_collect(sys.argv[2])
            print(MARKER + json.dumps(result))
            raise SystemExit(0)
        except SystemExit:
            raise
        except BaseException as exc:
            import traceback
            traceback.print_exc()
            print(MARKER + json.dumps({"mode": sys.argv[2], "error": True, "exc": repr(exc)}))
            raise SystemExit(3)
    raise SystemExit(main())
