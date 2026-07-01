"""
tests/test_lot5_namefix_regression.py

Regression Lot 5 (etape 1bis) : couvre un NameError latent revele par
l'analyse de portee statique Cython et corrige dans les sources metier.

Ces chemins n'etaient couverts par aucun test executable (les tests existants du
moteur de devis sont `async def` et donc SKIPPED faute de pytest-asyncio). On
pilote ici les methodes concernees en synchrone via asyncio.run, et on contourne
le __init__ lourd (services SAP/pricing) via __new__ pour rester isole et rapide.

Bug couvert :
- workflow/devis_workflow.py : `_create_validated_client` passait `sap_data`
  (inexistant, le dict est `sap_client_data`) et lisait `sap_results` au lieu
  de `result`.
"""

import asyncio
import sys

sys.path.insert(0, '.')


# ---------------------------------------------------------------------------
# Bug : devis_workflow._create_validated_client / sap_data + sap_results
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
