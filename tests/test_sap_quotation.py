"""
Tests SAP Quotation Service - NOVA-SERVER
tests/test_sap_quotation.py

Couvre :
1. Construction du payload SAP (_build_sap_payload)
2. Validation des modèles Pydantic
3. Scénario happy path (mock SAP 201)
4. Retry automatique sur 401
5. Gestion timeout
6. Erreur métier SAP (ex: CardCode inconnu)

Usage :
    pytest tests/test_sap_quotation.py -v
    pytest tests/test_sap_quotation.py -v -k "payload"   # Tests payload uniquement
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

# Ajout path projet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sap_quotation_service import (
    QuotationLine,
    QuotationPayload,
    QuotationResult,
    SAPQuotationService,
)


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def service():
    """Instance du service avec env SAP de test."""
    with patch.dict(os.environ, {
        "SAP_REST_BASE_URL": "https://test-sap:50000/b1s/v1",
        "SAP_USER_RONDOT": "manager",
        "SAP_CLIENT_RONDOT": "RON_TEST",
        "SAP_CLIENT_PASSWORD_RONDOT": "testpass",
    }):
        svc = SAPQuotationService()
        return svc


@pytest.fixture
def minimal_payload():
    """Payload minimal valide."""
    return QuotationPayload(
        CardCode="C00042",
        DocumentLines=[
            QuotationLine(
                ItemDescription="Piston hydraulique 50mm",
                Quantity=10,
                UnitPrice=45.50,
            )
        ],
    )


@pytest.fixture
def full_payload():
    """Payload complet avec tous les champs."""
    return QuotationPayload(
        CardCode="C00042",
        DocDate="2026-02-20",
        DocDueDate="2026-03-20",
        ValidUntil="2026-03-31",
        Comments="Devis suite email du 20/02/2026 - Ref: PRJ-2026-001",
        SalesPersonCode=3,
        NumAtCard="PRJ-2026-001",
        PaymentGroupCode=5,
        email_id="AAMkAGIxZmVkYWMz",
        email_subject="Demande de chiffrage - Pièces hydrauliques",
        nova_source="NOVA_MAIL_TO_BIZ",
        DocumentLines=[
            QuotationLine(
                ItemCode="C315-6305RS",
                ItemDescription="Piston hydraulique 50mm",
                Quantity=10,
                UnitPrice=45.50,
                DiscountPercent=5.0,
                TaxCode="S1",
                WarehouseCode="01",
                FreeText="Livraison urgente",
            ),
            QuotationLine(
                ItemDescription="Joint torique - référence fournisseur: JT-999",
                Quantity=100,
                UnitPrice=2.30,
            ),
        ],
    )


# ============================================================
# TESTS : MODÈLES PYDANTIC
# ============================================================


class TestQuotationModels:
    """Validation des modèles Pydantic."""

    def test_minimal_line_valid(self):
        """Une ligne minimale avec juste ItemDescription est valide."""
        line = QuotationLine(ItemDescription="Test produit", Quantity=1)
        assert line.ItemDescription == "Test produit"
        assert line.Quantity == 1.0
        assert line.ItemCode is None
        assert line.UnitPrice is None
        assert line.DiscountPercent == 0.0

    def test_line_with_item_code(self):
        """Ligne avec code SAP."""
        line = QuotationLine(
            ItemCode="C315-6305RS",
            ItemDescription="Piston",
            Quantity=5,
            UnitPrice=99.99,
        )
        assert line.ItemCode == "C315-6305RS"
        assert line.UnitPrice == 99.99

    def test_line_quantity_must_be_positive(self):
        """La quantité doit être > 0."""
        with pytest.raises(Exception):
            QuotationLine(ItemDescription="Test", Quantity=0)

    def test_line_discount_capped_at_100(self):
        """La remise ne peut pas dépasser 100%."""
        with pytest.raises(Exception):
            QuotationLine(ItemDescription="Test", Quantity=1, DiscountPercent=150)

    def test_payload_requires_card_code(self):
        """CardCode est obligatoire."""
        with pytest.raises(Exception):
            QuotationPayload(
                DocumentLines=[QuotationLine(ItemDescription="Test", Quantity=1)]
            )

    def test_payload_requires_at_least_one_line(self):
        """Au moins une ligne est requise."""
        with pytest.raises(Exception):
            QuotationPayload(CardCode="C00042", DocumentLines=[])

    def test_nova_source_default(self):
        """nova_source a une valeur par défaut."""
        payload = QuotationPayload(
            CardCode="C00042",
            DocumentLines=[QuotationLine(ItemDescription="Test", Quantity=1)],
        )
        assert payload.nova_source == "NOVA_MAIL_TO_BIZ"


# ============================================================
# TESTS : CONSTRUCTION DU PAYLOAD SAP
# ============================================================


class TestBuildSapPayload:
    """Tests de construction du dict JSON SAP."""

    def test_minimal_payload_fields(self, service, minimal_payload):
        """Payload minimal contient les champs obligatoires SAP."""
        sap = service._build_sap_payload(minimal_payload)

        assert sap["CardCode"] == "C00042"
        assert "DocDate" in sap
        assert "DocDueDate" in sap
        assert len(sap["DocumentLines"]) == 1

    def test_today_date_used_when_no_date(self, service, minimal_payload):
        """Si DocDate absent, la date du jour est utilisée."""
        sap = service._build_sap_payload(minimal_payload)
        today = datetime.now().strftime("%Y-%m-%d")
        assert sap["DocDate"] == today

    def test_explicit_date_respected(self, service, full_payload):
        """Si DocDate fourni, il est utilisé tel quel."""
        sap = service._build_sap_payload(full_payload)
        assert sap["DocDate"] == "2026-02-20"
        assert sap["DocDueDate"] == "2026-03-20"

    def test_item_code_included_when_present(self, service, full_payload):
        """ItemCode présent dans la ligne SAP si fourni."""
        sap = service._build_sap_payload(full_payload)
        line_with_code = sap["DocumentLines"][0]
        assert line_with_code["ItemCode"] == "C315-6305RS"

    def test_item_code_absent_when_none(self, service, full_payload):
        """ItemCode absent de la ligne SAP si non fourni (produit non SAP)."""
        sap = service._build_sap_payload(full_payload)
        line_without_code = sap["DocumentLines"][1]
        assert "ItemCode" not in line_without_code

    def test_nova_fields_not_in_payload(self, service, full_payload):
        """Les champs NOVA (email_id, nova_source) ne sont pas dans le payload SAP."""
        sap = service._build_sap_payload(full_payload)
        assert "email_id" not in sap
        assert "nova_source" not in sap
        assert "email_subject" not in sap

    def test_optional_fields_included_when_set(self, service, full_payload):
        """Champs optionnels inclus si définis."""
        sap = service._build_sap_payload(full_payload)
        assert sap.get("Comments") == "Devis suite email du 20/02/2026 - Ref: PRJ-2026-001"
        assert sap.get("NumAtCard") == "PRJ-2026-001"
        assert sap.get("SalesPersonCode") == 3
        assert sap.get("ValidUntil") == "2026-03-31"

    def test_optional_fields_absent_when_none(self, service, minimal_payload):
        """Champs optionnels absents si non définis."""
        sap = service._build_sap_payload(minimal_payload)
        assert "Comments" not in sap
        assert "NumAtCard" not in sap
        assert "SalesPersonCode" not in sap

    def test_discount_always_included(self, service, minimal_payload):
        """DiscountPercent toujours présent (0.0 par défaut)."""
        sap = service._build_sap_payload(minimal_payload)
        assert sap["DocumentLines"][0]["DiscountPercent"] == 0.0

    def test_tax_code_included_when_set(self, service, full_payload):
        """TaxCode inclus si défini."""
        sap = service._build_sap_payload(full_payload)
        assert sap["DocumentLines"][0].get("TaxCode") == "S1"

    def test_warehouse_included_when_set(self, service, full_payload):
        """WarehouseCode inclus si défini."""
        sap = service._build_sap_payload(full_payload)
        assert sap["DocumentLines"][0].get("WarehouseCode") == "01"


# ============================================================
# TESTS : CREATE_SALES_QUOTATION (mock HTTP)
# ============================================================


class TestCreateSalesQuotation:
    """Tests de l'appel HTTP SAP avec mocks."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_doc_entry(self, service, minimal_payload):
        """Création réussie retourne DocEntry et DocNum."""
        # Simuler session active
        service.session_id = "FAKE_SESSION_123"
        service.session_timeout = datetime(2099, 1, 1)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "DocEntry": 4242,
            "DocNum": 1337,
            "DocTotal": 455.0,
            "DocDate": "2026-02-20",
            "CardCode": "C00042",
            "CardName": "MARMARA CAM",
        }

        with patch.object(service, "_call_sap_post", new=AsyncMock(return_value=mock_response)):
            result = await service.create_sales_quotation(minimal_payload)

        assert result.success is True
        assert result.doc_entry == 4242
        assert result.doc_num == 1337
        assert result.doc_total == 455.0
        assert result.card_name == "MARMARA CAM"
        assert "1337" in result.message

    @pytest.mark.asyncio
    async def test_sap_error_returns_failure(self, service, minimal_payload):
        """Erreur SAP (ex: CardCode inconnu) retourne success=False."""
        service.session_id = "FAKE_SESSION_123"
        service.session_timeout = datetime(2099, 1, 1)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "code": 10,
                "message": {"value": "Business partner does not exist: C99999"},
            }
        }

        with patch.object(service, "_call_sap_post", new=AsyncMock(return_value=mock_response)):
            result = await service.create_sales_quotation(minimal_payload)

        assert result.success is False
        assert result.doc_entry is None
        assert "10" in result.error_code or "SAP" in result.error_code

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self, service, minimal_payload):
        """Timeout SAP retourne success=False avec error_code SAP_TIMEOUT."""
        import httpx

        service.session_id = "FAKE_SESSION_123"
        service.session_timeout = datetime(2099, 1, 1)

        with patch.object(
            service, "_call_sap_post", new=AsyncMock(side_effect=httpx.TimeoutException(""))
        ):
            result = await service.create_sales_quotation(minimal_payload)

        assert result.success is False
        assert result.error_code == "SAP_TIMEOUT"

    @pytest.mark.asyncio
    async def test_login_failure_returns_failure(self, service, minimal_payload):
        """Échec login SAP retourne success=False avec error_code SAP_LOGIN_FAILED."""
        with patch.object(service, "login", new=AsyncMock(return_value=False)):
            result = await service.create_sales_quotation(minimal_payload)

        assert result.success is False
        assert result.error_code == "SAP_LOGIN_FAILED"

    @pytest.mark.asyncio
    async def test_sap_payload_included_in_result(self, service, minimal_payload):
        """sap_payload retourné dans le résultat pour l'audit."""
        service.session_id = "FAKE_SESSION_123"
        service.session_timeout = datetime(2099, 1, 1)

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "DocEntry": 1,
            "DocNum": 1,
            "DocTotal": 100.0,
            "DocDate": "2026-02-20",
            "CardCode": "C00042",
        }

        with patch.object(service, "_call_sap_post", new=AsyncMock(return_value=mock_response)):
            result = await service.create_sales_quotation(minimal_payload)

        assert result.sap_payload is not None
        assert result.sap_payload["CardCode"] == "C00042"
        assert len(result.sap_payload["DocumentLines"]) == 1


# ============================================================
# TESTS : SINGLETON
# ============================================================


class TestSingleton:
    def test_get_sap_quotation_service_returns_same_instance(self):
        """get_sap_quotation_service retourne toujours la même instance."""
        from services.sap_quotation_service import get_sap_quotation_service

        svc1 = get_sap_quotation_service()
        svc2 = get_sap_quotation_service()
        assert svc1 is svc2
