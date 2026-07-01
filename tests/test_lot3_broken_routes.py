"""
LOT 3 — Tests de non-régression des routes "avalées" SAP restantes
(AttributeError / TypeError à l'usage, + réponse honnête).

Couvre :
  - CAS 11 : POST /api/sap/quotations/from-email
             -> validate_and_enrich (inexistant sur ClientValidator) remplacé par
                validate_complete, seule candidate exposant {valid, enriched_data{...}}
                (cf. services/client_validator.py:178). La route lit toujours
                validation_result["valid"] puis enriched_data.get(...) ; les champs
                enrichis (denomination, numero_tva_intra, ...) sont propagés à
                create_business_partner.
  - CAS 10 : POST /api/graph/emails/{mid}/products/{item_code}/manual-code
             -> add_mapping (inexistant) supprimé ; save_mapping exige
                external_description + supplier_card_code, NON sourçables au site.
                Réponse honnête : aucun enregistrement, mapping_saved == False
                (plus de "true" mensonger). Le reste de la route (maj produit,
                validation SAP) n'est pas régressé.
  - DATA=PAYLOAD : SapCreationService.create_client / create_product
             -> call_sap(..., data=payload) corrigé en payload=payload
                (le kwarg réel est `payload`, cf. services/sap.py:46). Routes
                montées via /api/sap (routes_sap_creation). call_sap mocké :
                POST émis avec payload=, aucun TypeError.

Usage :
    .venv\\Scripts\\python.exe -m pytest tests/test_lot3_broken_routes.py -v
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user


# ── CAS 11 : POST /api/sap/quotations/from-email ────────────────────────────────

def _sap_business_client():
    # Le router porte déjà prefix="/api/sap" (pas de double préfixe).
    from routes.routes_sap_business import router as sap_business_router
    app = FastAPI()
    app.include_router(sap_business_router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test", "role": "ADMIN"}
    return TestClient(app)


class TestQuotationFromEmail:
    def test_candidate_method_resolution(self):
        """La candidate retenue existe et expose le contrat ; l'ancienne méthode
        (cause du bug) n'existe pas -> garde-fou anti-réintroduction."""
        from services.client_validator import ClientValidator
        assert not hasattr(ClientValidator, "validate_and_enrich")
        assert callable(getattr(ClientValidator, "validate_complete", None))

    def test_uses_validate_complete_and_propagates_enriched_data(self, monkeypatch):
        captured = {}

        # 1. Candidate réelle : validate_complete -> {valid, enriched_data{...}}
        async def fake_validate_complete(self, client_data, country="FR"):
            captured["client_data"] = client_data
            captured["country"] = country
            return {
                "valid": True,
                "errors": [],
                "enriched_data": {
                    "denomination": "ACME SARL",
                    "numero_tva_intra": "FR40123456789",
                    "forme_juridique": "SARL",
                    "telephone": "0102030405",
                    "siret": "12345678901234",
                    "adresse_ligne_1": "1 rue du Test",
                    "ville": "Paris",
                    "code_postal": "75001",
                    "code_pays": "FR",
                    "capital": "10000",
                },
            }

        import services.client_validator as cv
        monkeypatch.setattr(cv.ClientValidator, "validate_complete", fake_validate_complete)

        # 2. SAP business service factice
        class FakeItem:
            ItemCode = "ITM-1"

        class FakeSap:
            async def search_business_partner(self, name=None, email=None):
                return None  # force le chemin création + enrichissement

            async def create_business_partner(self, **kwargs):
                captured["bp_kwargs"] = kwargs
                return "C0001"

            async def search_items(self, reference, top=1):
                return [FakeItem()]

            async def create_quotation(self, card_code, lines, comments, reference):
                captured["quote"] = {"card_code": card_code, "lines": lines}
                return 4242

        import routes.routes_sap_business as rsb
        monkeypatch.setattr(rsb, "get_sap_business_service", lambda: FakeSap())

        # 3. Moteur pricing factice (article trouvé -> pricing intelligent)
        decision = SimpleNamespace(
            calculated_price=120.0, case_type="CAS1",
            justification="ok", requires_validation=False, margin_applied=45.0,
        )
        engine = SimpleNamespace()
        async def fake_calc(ctx):
            return SimpleNamespace(success=True, decision=decision)
        engine.calculate_price = fake_calc
        import services.pricing_engine as pe
        monkeypatch.setattr(pe, "get_pricing_engine", lambda: engine)

        client = _sap_business_client()
        resp = client.post(
            "/api/sap/quotations/from-email?email_id=EML-1",
            json={
                "client_name": "ACME",
                "client_email": "contact@acme.fr",
                "siret": "12345678901234",
                "phone": "0102030405",
                "products": [{"reference": "REF-1", "quantity": 3, "description": "Pièce"}],
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["doc_entry"] == 4242

        # validate_complete (renommée) bien appelée avec les données client
        assert captured["client_data"]["siret"] == "12345678901234"
        # La route lit valid + enriched_data : les champs enrichis atterrissent
        # dans create_business_partner (contrat de sortie préservé).
        bp = captured["bp_kwargs"]
        assert bp["card_name"] == "ACME SARL"          # enriched_data.denomination
        assert bp["tva_intra"] == "FR40123456789"      # numero_tva_intra
        assert bp["legal_form"] == "SARL"              # forme_juridique
        assert bp["city"] == "Paris"                   # ville

    def test_invalid_enrichment_falls_back_to_partial_data(self, monkeypatch):
        """valid=False -> la route n'enrichit pas et crée avec données partielles
        (le client_name brut), sans planter."""
        async def fake_validate_complete(self, client_data, country="FR"):
            return {"valid": False, "errors": ["nom obligatoire"], "enriched_data": {}}

        import services.client_validator as cv
        monkeypatch.setattr(cv.ClientValidator, "validate_complete", fake_validate_complete)

        captured = {}

        class FakeItem:
            ItemCode = "ITM-1"

        class FakeSap:
            async def search_business_partner(self, name=None, email=None):
                return None

            async def create_business_partner(self, **kwargs):
                captured["bp_kwargs"] = kwargs
                return "C0002"

            async def search_items(self, reference, top=1):
                return [FakeItem()]

            async def create_quotation(self, card_code, lines, comments, reference):
                return 4343

        import routes.routes_sap_business as rsb
        monkeypatch.setattr(rsb, "get_sap_business_service", lambda: FakeSap())

        decision = SimpleNamespace(
            calculated_price=10.0, case_type="CAS1",
            justification="ok", requires_validation=False, margin_applied=45.0,
        )
        engine = SimpleNamespace()
        async def fake_calc(ctx):
            return SimpleNamespace(success=True, decision=decision)
        engine.calculate_price = fake_calc
        import services.pricing_engine as pe
        monkeypatch.setattr(pe, "get_pricing_engine", lambda: engine)

        client = _sap_business_client()
        resp = client.post(
            "/api/sap/quotations/from-email?email_id=EML-2",
            json={
                "client_name": "ACME BRUT",
                "siret": "12345678901234",
                "products": [{"reference": "REF-1", "quantity": 1}],
            },
        )
        assert resp.status_code == 200, resp.text
        # Données partielles : card_name = client_name brut (pas de denomination)
        assert captured["bp_kwargs"]["card_name"] == "ACME BRUT"


# ── CAS 10 : POST /api/graph/.../manual-code ────────────────────────────────────

def _graph_client():
    from routes.routes_graph import router as graph_router
    app = FastAPI()
    app.include_router(graph_router, prefix="/api/graph")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test", "role": "ADMIN"}
    return TestClient(app)


class TestManualProductCode:
    def test_mapping_saved_false_when_not_persistable(self, monkeypatch):
        """save_mapping non appelable honnêtement (external_description +
        supplier_card_code absents) -> mapping_saved == False, le reste OK."""
        from services.sap_business_service import SAPItem

        result = SimpleNamespace(
            product_matches=[{"item_code": "EXT-999", "quantity": 2}],
            extracted_data=SimpleNamespace(client_card_code="C0001"),
        )

        import routes.routes_graph as rg
        monkeypatch.setattr(rg, "_load_analysis", lambda mid: result)
        monkeypatch.setattr(rg, "_persist_analysis", lambda mid, res: None)

        class FakeSap:
            async def get_item_by_code(self, code):
                return SAPItem(ItemCode="RON-123", ItemName="Vraie pièce", Price=None, InStock=None)

        import services.sap_business_service as sbs
        monkeypatch.setattr(sbs, "get_sap_business_service", lambda: FakeSap())

        # Pricing neutralisé (non critique, évite tout accès réseau)
        engine = SimpleNamespace()
        async def fake_calc(ctx):
            return SimpleNamespace(success=False, decision=None)
        engine.calculate_price = fake_calc
        import services.pricing_engine as pe
        monkeypatch.setattr(pe, "get_pricing_engine", lambda: engine)

        # Corrections DB neutralisée (évite l'écriture sur la vraie base)
        class FakeCorr:
            def save_correction(self, **kwargs):
                return None
        import services.quote_corrections_db as qcd
        monkeypatch.setattr(qcd, "get_quote_corrections_db", lambda: FakeCorr())

        client = _graph_client()
        resp = client.post(
            "/api/graph/emails/MSG-1/products/EXT-999/manual-code",
            json={"rondot_code": "RON-123"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Réponse honnête : pas d'enregistrement de mapping
        assert body["mapping_saved"] is False
        # Le reste du contrat est préservé
        assert body["success"] is True
        assert body["item_code"] == "RON-123"
        assert body["product_updated"] is True
        assert body["sap_validated"] is True


# ── DATA=PAYLOAD : SapCreationService.create_client / create_product ─────────────

class TestSapCreationPayloadKwarg:
    def test_create_client_posts_with_payload_kwarg(self, monkeypatch):
        import services.sap_creation_service as scs

        calls = []

        async def fake_call_sap(endpoint, method="GET", payload=None):
            # Signature IDENTIQUE à la vraie call_sap : un appel data= lèverait
            # TypeError ici (reproduit le bug d'origine).
            calls.append({"endpoint": endpoint, "method": method, "payload": payload})
            if endpoint == "/Companies":
                return {}  # _check_sap_connection OK
            return {"CardCode": "C0001"}

        monkeypatch.setattr(scs, "call_sap", fake_call_sap)

        service = scs.SapCreationService()
        client_data = scs.NewClientData(card_name="ACME", contact_email="a@acme.fr")

        import asyncio
        result = asyncio.run(service.create_client(client_data))

        assert result.success is True
        assert result.entity_code == "C0001"
        post = next(c for c in calls if c["method"] == "POST")
        assert post["endpoint"] == "/BusinessPartners"
        assert post["payload"]["CardName"] == "ACME"  # payload bien transmis

    def test_create_product_posts_with_payload_kwarg(self, monkeypatch):
        import services.sap_creation_service as scs

        calls = []

        async def fake_call_sap(endpoint, method="GET", payload=None):
            calls.append({"endpoint": endpoint, "method": method, "payload": payload})
            if endpoint == "/Companies":
                return {}
            return {"ItemCode": "ART-001"}

        monkeypatch.setattr(scs, "call_sap", fake_call_sap)

        service = scs.SapCreationService()
        product_data = scs.NewProductData(item_code="ART-001", item_name="Pièce test")

        import asyncio
        result = asyncio.run(service.create_product(product_data))

        assert result.success is True
        assert result.entity_code == "ART-001"
        post = next(c for c in calls if c["method"] == "POST")
        assert post["endpoint"] == "/Items"
        assert post["payload"]["ItemCode"] == "ART-001"
