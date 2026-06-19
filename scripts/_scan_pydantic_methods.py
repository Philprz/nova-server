#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Outil d'analyse (jetable) : mesure l'ampleur du pattern "modele Pydantic avec
methode ordinaire" qui casse a la compilation Cython (cf. cython_pydantic_compat).

Parcourt tout le repo, repere les classes heritant de BaseModel et compte celles
qui definissent au moins une METHODE ordinaire (ni @property, ni
@classmethod/@staticmethod, ni validateur/serializer decore Pydantic, ni dunder).
Ce sont exactement les modeles qui declenchent PydanticUserError une fois compiles
SANS le shim.

Usage : .venv\\Scripts\\python.exe scripts\\_scan_pydantic_methods.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", "build", "__pycache__", ".git", "node_modules", "tests"}

# Decorateurs qui rendent une "methode" inoffensive pour Pydantic compile.
SAFE_DECORATORS = {
    "property", "cached_property", "staticmethod", "classmethod",
    "field_validator", "model_validator", "field_serializer", "model_serializer",
    "computed_field", "validator", "root_validator",
}


def _is_basemodel(node: ast.ClassDef) -> bool:
    for b in node.bases:
        name = b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", None)
        if name in ("BaseModel", "BaseSettings"):
            return True
    return False


def _decorator_names(fn: ast.FunctionDef):
    out = set()
    for d in fn.decorator_list:
        if isinstance(d, ast.Name):
            out.add(d.id)
        elif isinstance(d, ast.Attribute):
            out.add(d.attr)
        elif isinstance(d, ast.Call):
            t = d.func
            out.add(t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", ""))
    return out


def main() -> int:
    files = []
    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)

    total_models = 0
    risky_models = 0
    risky_files = {}
    for p in files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_basemodel(node):
                continue
            total_models += 1
            risky_methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("__") and item.name.endswith("__"):
                        continue  # dunders : geres a part par Pydantic/Cython
                    if _decorator_names(item) & SAFE_DECORATORS:
                        continue
                    risky_methods.append(item.name)
            if risky_methods:
                risky_models += 1
                rel = str(p.relative_to(ROOT))
                risky_files.setdefault(rel, []).append(f"{node.name}: {risky_methods}")

    print(f"Fichiers .py scannes (hors venv/build/tests) : {len(files)}")
    print(f"Modeles Pydantic (BaseModel/BaseSettings)     : {total_models}")
    print(f"Modeles a RISQUE (methode ordinaire)          : {risky_models}")
    print(f"Fichiers concernes                            : {len(risky_files)}")
    print("\n-- detail --")
    for rel in sorted(risky_files):
        print(f"  {rel}")
        for m in risky_files[rel]:
            print(f"      {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
