#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/probe_fastapi_future.py — sonde ciblee Lot 5 phase 2.

Leve le DERNIER inconnu du build complet : un router FastAPI qui combine
`from __future__ import annotations` + Cython. 4 routers du repo sont dans ce
cas (routes_packing, routes_shipping, routes_intelligent_assistant,
routes_sap_session). La phase 1 n'avait teste un router que SANS
future-annotations.

Risque : sous future-annotations, les annotations des handlers sont des CHAINES ;
FastAPI appelle `typing.get_type_hints()` pour reconstruire le modele de requete.
Sur une cyfunction compilee, get_type_hints doit pouvoir resoudre les noms via les
globals du module. On verifie aussi qu'un defaut `Query(...)` / `Depends(...)`
survit a la compilation (annotation_typing=False, deja valide phase 1) et qu'un
modele de corps avec METHODE ordinaire passe (shim cython_pydantic_compat).

Demarche : on GENERE un fixture router auto-suffisant (pas une source du repo),
on le compile en .pyd, puis on compare le comportement HTTP source vs compile via
TestClient. A lancer sous environnement MSVC :
    scripts\\probe_fastapi_future.bat
"""
import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "phase2_fastapi"
SRC_DIR = BUILD / "src"
CTMP = BUILD / "cython_c"
TEMP = BUILD / "obj"
PYD = BUILD / "pyd"

FIXTURE_NAME = "fixture_future_router"

FIXTURE_SRC = '''\
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field


def get_token(x_token: str = Query(default="anon")) -> str:
    """Dependance simple, defaut via Query -> doit survivre a la compilation."""
    return x_token


class EchoBody(BaseModel):
    """Modele de corps avec une METHODE ordinaire (cyfunction apres compilation)."""
    name: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)

    def shout(self) -> str:          # methode ordinaire -> piege cyfunction
        return f"{self.name.upper()}x{self.count}"


router = APIRouter(prefix="/probe", tags=["probe"])


@router.get("/hello")
async def hello(q: str = Query(default="world", min_length=1),
                token: str = Depends(get_token)) -> dict:
    # q/token annotes = chaines sous future-annotations -> FastAPI get_type_hints
    return {"hello": q, "token": token}


@router.get("/item/{item_id}")
async def get_item(item_id: int, factor: Optional[int] = Query(default=2)) -> dict:
    return {"item_id": item_id, "product": item_id * (factor or 1)}


@router.post("/echo")
async def echo(body: EchoBody) -> dict:
    return {"shout": body.shout(), "count": body.count}
'''


def _write_fixture() -> Path:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    p = SRC_DIR / f"{FIXTURE_NAME}.py"
    p.write_text(FIXTURE_SRC, encoding="utf-8")
    return p


def _compile(src: Path) -> Path:
    from setuptools import Extension
    from setuptools.dist import Distribution
    from Cython.Build import cythonize

    ext = Extension(FIXTURE_NAME, [str(src)])
    ext_modules = cythonize(
        [ext], build_dir=str(CTMP), language_level=3,
        compiler_directives={"language_level": "3", "annotation_typing": False},
        annotate=False, quiet=True,
    )
    dist = Distribution({"name": "nova_probe_fastapi", "ext_modules": ext_modules})
    cmd = dist.get_command_obj("build_ext")
    cmd.build_lib = str(PYD)
    cmd.build_temp = str(TEMP)
    cmd.inplace = 0
    cmd.ensure_finalized()
    cmd.run()
    pyds = list(PYD.rglob(f"{FIXTURE_NAME}*.pyd"))
    if not pyds:
        raise RuntimeError("aucun .pyd produit pour le fixture")
    return pyds[0]


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def _exercise(router_mod, label: str) -> dict:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(router_mod.router)
    c = TestClient(app)
    out = {}
    r1 = c.get("/probe/hello", params={"q": "nova", "x_token": "T1"})
    out["hello"] = (r1.status_code, r1.json())
    r2 = c.get("/probe/item/21", params={"factor": 3})
    out["item"] = (r2.status_code, r2.json())
    r3 = c.post("/probe/echo", json={"name": "abc", "count": 2})
    out["echo"] = (r3.status_code, r3.json())
    r4 = c.get("/probe/hello", params={"q": ""})  # viole min_length -> 422 attendu
    out["validation_422"] = r4.status_code
    print(f"  [{label}] hello={out['hello']} item={out['item']} echo={out['echo']} 422={out['validation_422']}")
    return out


def main() -> int:
    print("== probe_fastapi_future ==")
    for d in (CTMP, TEMP, PYD):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    # Shim cyfunction<->pydantic AVANT toute creation de modele compile.
    sys.path.insert(0, str(ROOT / "scripts"))
    import cython_pydantic_compat
    print("  shim compat applique :", cython_pydantic_compat.apply())

    src = _write_fixture()
    print(f"  fixture : {src.relative_to(ROOT)} ({src.stat().st_size} octets)")

    # 1) comportement SOURCE
    src_mod = _load(f"{FIXTURE_NAME}_src", src)
    src_res = _exercise(src_mod, "source")

    # 2) compilation puis comportement COMPILE
    pyd = _compile(src)
    print(f"  .pyd : {pyd.relative_to(ROOT)} ({pyd.stat().st_size} octets)")
    comp_mod = _load(FIXTURE_NAME, pyd)
    assert comp_mod.__file__.endswith(".pyd"), comp_mod.__file__
    comp_res = _exercise(comp_mod, "compile")

    print("\n== verdict ==")
    ok = True
    for key in src_res:
        same = src_res[key] == comp_res[key]
        print(f"  [{'OK ' if same else 'FAIL'}] {key} : {comp_res[key]}")
        ok = ok and same
    # exigences explicites
    checks = [
        ("hello 200", comp_res["hello"][0] == 200 and comp_res["hello"][1]["hello"] == "nova"),
        ("Depends/Query token", comp_res["hello"][1]["token"] == "T1"),
        ("path param int", comp_res["item"][1]["product"] == 63),
        ("body model + methode (cyfunction)", comp_res["echo"][1]["shout"] == "ABCx2"),
        ("validation 422 preservee", comp_res["validation_422"] == 422),
    ]
    for label, cond in checks:
        print(f"  [{'OK ' if cond else 'FAIL'}] {label}")
        ok = ok and cond

    print("\nSUCCES : FastAPI + future-annotations + Cython OK." if ok else "\nECHEC.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
