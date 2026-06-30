"""
tests/test_lot5_b5b6b8b9.py

Lot 5 (etape 1ter) : tests cibles sur les chemins B5/B6/B8/B9 finalises selon
les contrats valides. Ces chemins n'etaient couverts par aucun test executable.

Comme pour test_lot5_namefix_regression.py, on pilote des methodes `async` en
synchrone via `asyncio.run` (les tests `async def` sont SKIPPED faute de
pytest-asyncio) et on contourne le __init__ lourd via `__new__`.

- B5 : devis_workflow._search_local_by_code -> dict produit unique ou None.
- B6 : devis_workflow._process_quote_workflow -> payload quote_validation porte
       client_info sous l'enveloppe conventionnelle {data, found, status}.
- B8 : routes_intelligent_assistant.get_workflow_context -> contexte persiste
       portant extracted_info/products/original_prompt/task_id, consomme par
       apply_product_suggestions.
- B9 : routes_intelligent_assistant.handle_client_search_intent -> filtre Nom
       (casse ignoree) + mapping {id, name, industry, location_display}.
"""

import asyncio
import os
import sys

sys.path.insert(0, '.')


# ---------------------------------------------------------------------------
# B5 : _search_local_by_code -> dict produit unique (ItemCode/ItemName) ou None
# ---------------------------------------------------------------------------

class _FakeRow:
    item_code = "ITM001"
    item_name = "Vis tete fraisee M6"
    u_description = "Acier inox A2"
    avg_price = 12.5
    on_hand = 7
    items_group_code = "100"
    manufacturer = "ACME"
    sales_unit = "UN"


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        return _FakeResult(self._row)


def _patch_local_db(monkeypatch, row):
    """Branche un faux moteur SQLAlchemy renvoyant `row` (ou None)."""
    import sqlalchemy
    import sqlalchemy.orm

    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: object())
    monkeypatch.setattr(
        sqlalchemy.orm, "sessionmaker", lambda *a, **k: (lambda: _FakeSession(row))
    )


def test_b5_search_local_by_code_present_renvoie_dict(monkeypatch):
    from workflow.devis_workflow import EnhancedDevisWorkflow

    _patch_local_db(monkeypatch, _FakeRow())
    wf = EnhancedDevisWorkflow.__new__(EnhancedDevisWorkflow)

    result = asyncio.run(wf._search_local_by_code("ITM001"))

    assert isinstance(result, dict)
    assert result["ItemCode"] == "ITM001"
    assert result["ItemName"] == "Vis tete fraisee M6"
    # Le consommateur (_smart_product_search:4085-4089) lit .get('ItemName') et
    # encapsule le dict dans une liste : un dict unique est donc la bonne forme.
    assert result["source"] == "local_db"


def test_b5_search_local_by_code_absent_renvoie_none(monkeypatch):
    from workflow.devis_workflow import EnhancedDevisWorkflow

    _patch_local_db(monkeypatch, None)
    wf = EnhancedDevisWorkflow.__new__(EnhancedDevisWorkflow)

    result = asyncio.run(wf._search_local_by_code("INEXISTANT"))

    assert result is None


# ---------------------------------------------------------------------------
# B6 : payload quote_validation -> client_info = enveloppe {data, found, status}
# ---------------------------------------------------------------------------

def test_b6_quote_validation_porte_enveloppe_client_info():
    from workflow.devis_workflow import EnhancedDevisWorkflow

    wf = EnhancedDevisWorkflow.__new__(EnhancedDevisWorkflow)
    wf.context = {}
    wf.current_task = None        # neutralise require_user_validation
    wf.task_id = "T_B6"

    async def _fake_parallel(client_name, products):
        # Force le repli vers le chemin sequentiel (ou la branche B6 est construite).
        return {"status": "fallback_to_sequential"}

    async def _fake_client_validation(client_name):
        return {
            "status": "found",
            "data": {"Name": "ACME Corp", "CardName": "ACME SA", "CardCode": "CACME"},
            "message": "Client trouve",
        }

    async def _fake_dupes(client_info, products):
        return {}

    async def _fake_products(products):
        return {"status": "ok", "products": [{"ItemCode": "P1", "Name": "Produit 1"}]}

    async def _fake_preview(client_result, products_result):
        return {"total_amount": 123.0, "currency": "EUR"}

    wf._parallel_client_product_search = _fake_parallel
    wf._process_client_validation = _fake_client_validation
    wf._check_duplicate_quotes = _fake_dupes
    wf._process_products_retrieval = _fake_products
    wf._prepare_quote_preview = _fake_preview
    for name in ("_track_step_start", "_track_step_complete",
                 "_track_step_fail", "_track_step_progress"):
        setattr(wf, name, lambda *a, **k: None)

    extracted_info = {"client": "ACME Corp", "products": [{"code": "P1", "quantity": 2}]}
    result = asyncio.run(wf._process_quote_workflow(extracted_info))

    assert result.get("status") == "user_interaction_required"
    assert result.get("type") == "quote_validation"

    client_info = result["interaction_data"]["client_info"]
    assert set(client_info.keys()) == {"data", "found", "status"}
    assert client_info["found"] is True
    assert client_info["status"] == "found"
    # L'enregistrement client reste lisible (Name / CardName).
    assert client_info["data"]["Name"] == "ACME Corp"
    assert client_info["data"]["CardName"] == "ACME SA"


# ---------------------------------------------------------------------------
# B8 : get_workflow_context -> contexte persiste (task_id + original_prompt)
#      consomme par apply_product_suggestions (chemin PRODUIT)
# ---------------------------------------------------------------------------

class _FakePersistedTask:
    task_id = "quote_20260623_b8"
    user_prompt = "Faire un devis pour 10 vis M6 pour ACME"
    context = {
        "extracted_info": {
            "client": "ACME",
            "products": [{"code": "VIS-M6", "quantity": 10}],
        }
    }


def test_b8_get_workflow_context_porte_les_cles_produit(monkeypatch):
    import routes.routes_intelligent_assistant as ria

    monkeypatch.setattr(ria.progress_tracker, "get_task",
                        lambda task_id: _FakePersistedTask())

    ctx = asyncio.run(ria.get_workflow_context("quote_20260623_b8"))

    # Les 3 cles attendues par apply_product_suggestions sont presentes.
    assert ctx["task_id"] == "quote_20260623_b8"
    assert ctx["extracted_info"]["original_prompt"] == "Faire un devis pour 10 vis M6 pour ACME"
    assert ctx["extracted_info"]["products"] == [{"code": "VIS-M6", "quantity": 10}]


def test_b8_get_workflow_context_tache_absente_renvoie_dict_vide(monkeypatch):
    import routes.routes_intelligent_assistant as ria

    monkeypatch.setattr(ria.progress_tracker, "get_task", lambda task_id: None)

    ctx = asyncio.run(ria.get_workflow_context("inconnu"))
    assert ctx == {}


def test_b8_apply_product_suggestions_consomme_le_contexte_persiste(monkeypatch):
    import routes.routes_intelligent_assistant as ria
    from workflow.devis_workflow import EnhancedDevisWorkflow

    monkeypatch.setattr(ria.progress_tracker, "get_task",
                        lambda task_id: _FakePersistedTask())
    ctx = asyncio.run(ria.get_workflow_context("quote_20260623_b8"))

    wf = EnhancedDevisWorkflow.__new__(EnhancedDevisWorkflow)
    captured = {}

    async def _fake_process_prompt(prompt, task_id=None):
        captured["prompt"] = prompt
        captured["task_id"] = task_id
        captured["products"] = ctx["extracted_info"]["products"]
        return {"ok": True}

    wf.process_prompt = _fake_process_prompt

    product_choices = [{
        "type": "use_suggestion",
        "selected_product": {"code": "NEW-REF-1"},
        "quantity": 3,
    }]
    result = asyncio.run(wf.apply_product_suggestions(product_choices, ctx))

    assert result == {"ok": True}
    # original_prompt + task_id correctement transmis au re-traitement.
    assert captured["prompt"] == "Faire un devis pour 10 vis M6 pour ACME"
    assert captured["task_id"] == "quote_20260623_b8"
    # Les produits ont ete remplaces par le choix utilisateur.
    assert captured["products"] == [{"code": "NEW-REF-1", "quantity": 3}]


# ---------------------------------------------------------------------------
# B9 : handle_client_search_intent -> filtre Nom (casse ignoree) + mapping
# ---------------------------------------------------------------------------

def test_b9_handle_client_search_filtre_et_mappe(monkeypatch):
    import routes.routes_intelligent_assistant as ria

    async def _fake_unified(data_type, limit=20):
        return {
            "clients": [
                {"Id": "001A", "Name": "Microsoft France",
                 "Industry": "Informatique",
                 "BillingCity": "Paris", "BillingCountry": "France"},
                {"Id": "001B", "Name": "Orange SA",
                 "Industry": "Telecom",
                 "BillingCity": "Lyon", "BillingCountry": "France"},
            ]
        }

    monkeypatch.setattr(ria, "get_unified_data", _fake_unified)

    # Casse volontairement differente ("microSOFT" vs "Microsoft France").
    result = asyncio.run(
        ria.handle_client_search_intent("peu importe",
                                        {"client_names": ["microSOFT"]})
    )

    assert result["type"] == "client_search_results"
    message = result["message"]
    # Le client correspondant (insensible a la casse, sur Name seul) est present...
    assert "Microsoft France" in message
    # ... et le non-correspondant est exclu.
    assert "Orange" not in message
    # Mapping : location_display = "Ville, Pays", industry, id.
    assert "Paris, France" in message
    assert "Informatique" in message
    assert "001A" in message
    # Suggestion d'action construite sur le name normalise.
    assert result["suggestions"][0] == "Utiliser Microsoft France"


def test_b9_handle_client_search_aucun_resultat_propose_creation(monkeypatch):
    import routes.routes_intelligent_assistant as ria

    async def _fake_unified(data_type, limit=20):
        return {"clients": [{"Id": "001B", "Name": "Orange SA",
                             "Industry": "Telecom",
                             "BillingCity": "Lyon", "BillingCountry": "France"}]}

    monkeypatch.setattr(ria, "get_unified_data", _fake_unified)

    result = asyncio.run(
        ria.handle_client_search_intent("x", {"client_names": ["IntrouvableSARL"]})
    )

    assert result["type"] == "client_search_results"
    assert result.get("create_option", {}).get("client_name") == "IntrouvableSARL"
