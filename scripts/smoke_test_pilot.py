#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/smoke_test_pilot.py — Smoke-test du pilote Cython (Lot 5).

Pour chacun des 3 modules compiles :
  1. charge la version .pyd DIRECTEMENT depuis build/compiled/ (par chemin de
     fichier, pour garantir qu'on teste bien le binaire et pas la source) ;
  2. execute un test minimal ;
  3. compare au comportement de la version source .py.

N'altere ni les sources, ni le demarrage de l'app. Aucun acces reseau.

Usage : .venv\\Scripts\\python.exe scripts\\smoke_test_pilot.py
"""
import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPILED = ROOT / "build" / "compiled"
sys.path.insert(0, str(ROOT))  # pour les imports inter-modules (services.*, etc.)

_FAILS = []


def _ok(label):
    print(f"  [OK]   {label}")


def _fail(label, exc):
    print(f"  [FAIL] {label} -> {exc!r}")
    _FAILS.append((label, exc))


def load_compiled(modname: str, rel_pyd_dir: str):
    """Charge un .pyd par chemin de fichier sous un nom dedie (evite la source)."""
    folder = COMPILED / rel_pyd_dir
    # Cibler le bon binaire : un dossier peut contenir plusieurs .pyd.
    matches = list(folder.glob(f"{modname}.*.pyd")) or list(folder.glob(f"{modname}.pyd"))
    if not matches:
        raise FileNotFoundError(f"aucun .pyd pour {modname} dans {folder}")
    pyd = matches[0]
    # Le nom du spec DOIT finir par le basename du module : une extension C
    # n'expose que PyInit_<basename>. Pas de collision avec la source, qui vit
    # sous un nom pointe (ex. services.pricing_models).
    spec = importlib.util.spec_from_file_location(modname, str(pyd))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.__file__.endswith(".pyd"), f"pas un .pyd : {mod.__file__}"
    return mod, pyd.name


# ---------------------------------------------------------------------------
# (b) Pydantic v2 : services/pricing_models.py
# ---------------------------------------------------------------------------
def test_pricing_models():
    print("\n[b] services/pricing_models.py  (Pydantic v2)")
    src = importlib.import_module("services.pricing_models")
    comp, fname = load_compiled("pricing_models", "services")
    _ok(f"import .pyd : {fname}")

    def scenario(M):
        # Construit + serialise un modele Pydantic v2 et exerce un field_validator.
        m = M.SupplierPriceVariation(previous_price=100.0, current_price=104.0)
        entry = M.SalesHistoryEntry(
            doc_entry=1, doc_num=2, doc_date="2025-01-15", card_code="C00001",
            item_code="REF-001", quantity=1.0, unit_price=10.0, line_total=10.0,
        )
        return (m.model_dump(mode="json"),
                entry.model_dump(mode="json"),
                [c.value for c in M.PricingCaseType])

    rs, rc = scenario(src), scenario(comp)
    try:
        # Objectif du pilote : le .pyd se comporte EXACTEMENT comme la source.
        assert rc == rs, f"divergence source/compile\n  src={rs}\n  pyd={rc}"
        _ok("model_dump + field_validator : comportement identique a la source")
        assert "previous_price" in rc[0] and "variation_percent" in rc[0]
        _ok(f"SupplierPriceVariation valide : {rc[0]}")
        _ok(f"SalesHistoryEntry (date->json) : doc_date={rc[1]['doc_date']}")
        _ok(f"Enum PricingCaseType : {len(rc[2])} valeurs identiques")
    except AssertionError as e:
        _fail("pricing_models", e)


# ---------------------------------------------------------------------------
# (a) service pur : services/currency_service.py
# ---------------------------------------------------------------------------
def test_currency_service():
    print("\n[a] services/currency_service.py  (service + async, hors reseau)")
    src = importlib.import_module("services.currency_service")
    comp, fname = load_compiled("currency_service", "services")
    _ok(f"import .pyd : {fname}")

    def scenario(M):
        svc = M.CurrencyService()
        same = asyncio.run(svc.get_exchange_rate("EUR", "EUR"))    # chemin hors reseau
        bad = asyncio.run(svc.get_exchange_rate("EUR", "XXX"))     # devise non supportee
        return (svc.SUPPORTED_CURRENCIES, same.rate, same.from_currency, bad)

    rs, rc = scenario(src), scenario(comp)
    try:
        assert rc[1] == 1.0 and rc[2] == "EUR", f"meme devise: {rc[1:3]}"
        _ok(f"async get_exchange_rate('EUR','EUR') -> rate={rc[1]}")
        assert rc[3] is None, f"devise non supportee devrait None: {rc[3]}"
        _ok("async get_exchange_rate('EUR','XXX') -> None")
        assert rc[0] == rs[0]
        _ok(f"SUPPORTED_CURRENCIES identique : {rc[0]}")
    except AssertionError as e:
        _fail("currency_service", e)


# ---------------------------------------------------------------------------
# (c) router FastAPI : routes/routes_products.py
# ---------------------------------------------------------------------------
def test_routes_products():
    print("\n[c] routes/routes_products.py  (router FastAPI, handlers async)")
    src = importlib.import_module("routes.routes_products")
    comp, fname = load_compiled("routes_products", "routes")
    _ok(f"import .pyd : {fname}")

    def routes_of(M):
        return sorted((r.path, tuple(sorted(r.methods))) for r in M.router.routes)

    rs, rc = routes_of(src), routes_of(comp)
    try:
        paths = [p for p, _ in rc]
        assert "/search_products_advanced" in paths, paths
        assert "/product_details/{item_code}" in paths, paths
        _ok(f"router expose {len(rc)} routes : {paths}")
        assert rc == rs, f"divergence routes source/compile\n  src={rs}\n  pyd={rc}"
        _ok("table de routes identique a la source")
        import inspect
        h = next(r.endpoint for r in comp.router.routes if r.path == "/product_details/{item_code}")
        assert inspect.iscoroutinefunction(h), "handler non-async"
        _ok("handler async preserve dans le .pyd")
    except AssertionError as e:
        _fail("routes_products", e)


def main():
    print(f"== smoke_test_pilot ==  Python {sys.version.split()[0]}")
    if not COMPILED.exists():
        print("ERREUR : build/compiled introuvable. Lance d'abord build_cython_pilot.py")
        return 2
    test_pricing_models()
    test_currency_service()
    test_routes_products()
    print("\n== bilan ==")
    if _FAILS:
        print(f"ECHEC : {len(_FAILS)} test(s) en erreur")
        return 1
    print("SUCCES : les 3 .pyd se comportent comme les sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
