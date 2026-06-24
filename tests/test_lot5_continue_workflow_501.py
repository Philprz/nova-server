"""
tests/test_lot5_continue_workflow_501.py

Lot 5 (etape 1quater) : neutralisation HTTP 501 de la branche PRODUIT de
/assistant/continue_workflow (choice_type == "product_selected").

L'appel workflow.apply_product_choices(...) ciblait une methode INEXISTANTE
(seule apply_product_suggestions est definie, avec un payload different). La
branche renvoie desormais un HTTP 501 « non implemente », exactement comme la
branche CLIENT voisine (handle_client_selection_and_continue absente).

On pilote la coroutine `continue_workflow_with_choice` en synchrone via
`asyncio.run`, avec une fausse Request et un DevisWorkflow neutralise (le 501
doit etre leve AVANT toute utilisation reelle du workflow / de SAP).
"""

import asyncio
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, '.')


class _FakeRequest:
    """Request minimale : seule .json() est consommee par la route."""

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _InertWorkflow:
    """DevisWorkflow neutralise : aucune methode metier ne doit etre appelee."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        raise AssertionError(
            f"Aucune methode workflow ne doit etre appelee sur la branche 501 "
            f"(appel inattendu: {name})"
        )


def _patch_route(monkeypatch):
    import routes.routes_intelligent_assistant as ria

    async def _fake_context(task_id):
        return {}

    monkeypatch.setattr(ria, "get_workflow_context", _fake_context)
    monkeypatch.setattr(ria, "DevisWorkflow", _InertWorkflow)
    return ria


def test_product_selected_renvoie_501_sans_attributeerror(monkeypatch):
    """La branche produit doit lever HTTPException 501, pas un AttributeError/500."""
    ria = _patch_route(monkeypatch)

    request = _FakeRequest({
        "task_id": "quote_test_501",
        "choice_type": "product_selected",
        "products": [{"code": "P1", "quantity": 2}],
    })

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ria.continue_workflow_with_choice(request))

    assert exc_info.value.status_code == 501
    # Methode inexistante nommee + renvoi explicite au chantier separe.
    assert "apply_product_choices" in exc_info.value.detail
    assert "chantier" in exc_info.value.detail.lower()


def test_client_selected_renvoie_501_coherence(monkeypatch):
    """La branche client voisine reste en 501 (coherence des deux branches)."""
    ria = _patch_route(monkeypatch)

    request = _FakeRequest({
        "task_id": "quote_test_501",
        "choice_type": "client_selected",
    })

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ria.continue_workflow_with_choice(request))

    assert exc_info.value.status_code == 501
