#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cython_pydantic_compat — shim de compatibilite Cython <-> Pydantic v2 (Lot 5).

PROBLEME (decouvert phase 2) : un modele Pydantic v2 qui definit une METHODE
ordinaire (ni @property, ni @classmethod/@staticmethod, ni validateur decore)
casse une fois COMPILE par Cython. Cython transforme la methode en
`cython_function_or_method` (cyfunction), un type que la metaclasse Pydantic
(`inspect_namespace`) ne reconnait pas comme fonction : elle figure dans
`default_ignored_types()` = (FunctionType, property, classmethod, staticmethod,
...), or une cyfunction n'est PAS un `types.FunctionType`. Pydantic la prend
donc pour un champ sans annotation et leve :
    PydanticUserError: A non-annotated attribute was detected: `<methode> = ...`

CORRECTIF GLOBAL (zero modification des ~160 sources) : on etend la liste des
types ignores par Pydantic avec un MARQUEUR dont la metaclasse repond True a
`isinstance(<cyfunction>, marqueur)`. Aucune dependance a un module compile
prealable : la detection se fait par NOM de type a l'execution, ce qui couvre
toutes les cyfunctions sans avoir a en importer une au prealable.

USAGE : importer `apply()` AVANT la creation de tout modele Pydantic compile,
c.-a-d. tout en haut de l'entrypoint (run.py) et du repli dev (main.py) :

    import cython_pydantic_compat
    cython_pydantic_compat.apply()

Idempotent et inerte hors-compilation (un .py pur n'a pas de cyfunction, le
marqueur ne matche jamais rien -> aucun effet de bord).
"""
from __future__ import annotations

# Noms des types fonctionnels generes par Cython (3.x : cyfunction ;
# fused/lambda compiles : meme type). On matche par nom pour ne dependre
# d'aucun module compile importe au prealable.
_CYTHON_FUNC_TYPE_NAMES = frozenset({
    "cython_function_or_method",
    "fused_cython_function",
})

_applied = False


class _CythonCallableMeta(type):
    """Metaclasse dont isinstance() repond True pour toute cyfunction Cython."""
    def __instancecheck__(cls, instance) -> bool:  # noqa: N805
        return type(instance).__name__ in _CYTHON_FUNC_TYPE_NAMES


class CythonCallableMarker(metaclass=_CythonCallableMeta):
    """Marqueur a ajouter aux ignored_types de Pydantic (ne s'instancie pas)."""
    pass


def apply() -> bool:
    """
    Monkeypatch `default_ignored_types` de Pydantic v2 pour y inclure le
    marqueur. Retourne True si le patch a ete applique, False s'il l'etait deja
    ou si Pydantic est absent/incompatible. N'echoue jamais (best-effort).
    """
    global _applied
    if _applied:
        return False
    try:
        from pydantic._internal import _model_construction as _mc
    except Exception:
        return False

    _orig = _mc.default_ignored_types

    def _patched():
        base = _orig()
        if CythonCallableMarker in base:
            return base
        return base + (CythonCallableMarker,)

    # Marqueur pour idempotence/inspection.
    _patched._cython_compat = True  # type: ignore[attr-defined]
    if getattr(_mc.default_ignored_types, "_cython_compat", False):
        _applied = True
        return False

    _mc.default_ignored_types = _patched
    _applied = True
    return True


if __name__ == "__main__":
    print("apply() ->", apply())
    from pydantic._internal._model_construction import default_ignored_types
    print("marqueur present :", CythonCallableMarker in default_ignored_types())
