"""
tests/test_lot5_namefix_regression.py

Regression Lot 5 (etape 1bis) : couvre les deux NameError latents reveles par
l'analyse de portee statique Cython et corriges dans les sources metier.

Ces chemins n'etaient couverts par aucun test executable (les tests existants du
moteur de devis sont `async def` et donc SKIPPED faute de pytest-asyncio). On
pilote ici les methodes concernees en synchrone via asyncio.run, et on contourne
le __init__ lourd (services SAP/pricing) via __new__ pour rester isole et rapide.

Bugs couverts :
- services/quote_workflow_engine.py : `_optimize_transport` referencait
  `total_weight_kg` jamais bindee -> calcul du poids total.
- workflow/devis_workflow.py : `_create_validated_client` passait `sap_data`
  (inexistant, le dict est `sap_client_data`) et lisait `sap_results` au lieu
  de `result`.
"""

import asyncio
import sys

sys.path.insert(0, '.')


# ---------------------------------------------------------------------------
# Bug #1 : quote_workflow_engine._optimize_transport / total_weight_kg
# ---------------------------------------------------------------------------

def test_optimize_transport_calcule_le_poids_total():
    from services.quote_workflow_engine import (
        QuoteWorkflowEngine,
        QuoteDraft,
        Product,
        WorkflowState,
    )

    class _FakeTransportCost:
        carrier_name = "TestCarrier"
        cost = 12.34
        delivery_days = 3

    class _FakeTransportCalculator:
        async def calculate_transport_cost(self, **kwargs):
            return _FakeTransportCost()

    # Bypass du __init__ (services lourds) : on n'a besoin que du calculateur.
    engine = QuoteWorkflowEngine.__new__(QuoteWorkflowEngine)
    engine.transport_calculator = _FakeTransportCalculator()

    draft = QuoteDraft(quote_id="REG_TRANSPORT_001")
    draft.products = [
        Product(item_code="P1", item_name="Produit 1", quantity=10.0, weight_kg=2.5),
        Product(item_code="P2", item_name="Produit 2", quantity=5.0, weight_kg=1.0),
        # weight_kg None -> doit etre traite comme 0.0 (et non NameError/TypeError)
        Product(item_code="P3", item_name="Produit 3", quantity=3.0, weight_kg=None),
    ]

    result = asyncio.run(engine._optimize_transport(draft))

    assert result.current_state == WorkflowState.TRANSPORT_OPTIMIZED
    # 2.5*10 + 1.0*5 + 0*3 = 30.0 kg
    transport_traces = [t for t in result.traces if "Poids total" in t.justification]
    assert transport_traces, "La trace transport doit mentionner le poids total"
    assert "30.00 kg" in transport_traces[-1].justification


# ---------------------------------------------------------------------------
# Bug #2 : devis_workflow._create_validated_client / sap_data + sap_results
# ---------------------------------------------------------------------------

def test_create_validated_client_chemin_succes():
    from workflow.devis_workflow import EnhancedDevisWorkflow

    captured = {}

    class _FakeMcpConnector:
        async def call_sap_mcp(self, action, payload):
            captured["sap_action"] = action
            captured["sap_payload"] = payload
            # Le bug lisait `sap_results.get(...)` au lieu de `result` : on
            # renvoie un succes pour que le chemin nominal soit reellement suivi.
            return {"success": True, "data": {"CardCode": payload}}

        async def call_mcp(self, server, action, payload):
            return {"success": True, "data": {"Id": "001REG0000001"}}

    wf = EnhancedDevisWorkflow.__new__(EnhancedDevisWorkflow)
    wf.mcp_connector = _FakeMcpConnector()

    enrichment = {
        "company_name": "Regression SARL",
        "siret": "12345678900011",
        "address": {"street": "1 rue du Test", "postal_code": "75001", "city": "Paris"},
    }

    result = asyncio.run(wf._create_validated_client("Regression SARL", enrichment))

    assert result.get("created") is True, result
    # Le payload SAP doit bien venir du dict construit (sap_client_data), donc
    # contenir CardName/CardType issus de l'enrichissement.
    sap_customer = captured["sap_payload"]["customer_data"]
    assert sap_customer["CardName"] == "Regression SARL"
    assert sap_customer["CardType"] == "cCustomer"
    assert result.get("sap_card_code", "").startswith("C")
