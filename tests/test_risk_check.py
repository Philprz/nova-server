"""
Tests unitaires — risk_check_service

Couvre :
  - Entreprise saine → OK
  - Redressement judiciaire → WARNING
  - Liquidation judiciaire → BLOCKED
  - Radiée RCS → BLOCKED
  - API failure / timeout → UNKNOWN
  - is_blocked() / is_risky() helpers
  - Pipeline : résultat présent dans EmailAnalysisResult
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Fixer une fausse clé API pour les tests
os.environ.setdefault("PAPPERS_API_KEY", "test_key")

from services.risk_check_service import (
    get_company_risk,
    is_blocked,
    is_risky,
    _classify_procedures,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_pappers_response(procedures: list, statut_rcs: str = "Inscrite") -> dict:
    return {
        "siren": "123456789",
        "nom_entreprise": "ACME SAS",
        "statut_rcs": statut_rcs,
        "procedures_collectives": procedures,
    }


def _make_httpx_response(payload: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = payload
    mock.raise_for_status = MagicMock()
    return mock


# ─── Tests _classify_procedures (sync, sans HTTP) ───────────────────────────

class TestClassifyProcedures:

    def test_no_procedures_is_ok(self):
        status, reason = _classify_procedures([])
        assert status == "OK"

    def test_liquidation_is_blocked(self):
        status, reason = _classify_procedures([{"type": "Liquidation judiciaire", "date_jugement": "2024-01-15"}])
        assert status == "BLOCKED"
        assert "2024-01-15" in reason

    def test_redressement_is_warning(self):
        status, reason = _classify_procedures([{"type": "Redressement judiciaire"}])
        assert status == "WARNING"

    def test_sauvegarde_is_warning(self):
        status, reason = _classify_procedures([{"type": "Sauvegarde"}])
        assert status == "WARNING"

    def test_liquidation_takes_priority_over_warning(self):
        procs = [
            {"type": "Redressement judiciaire"},
            {"type": "Liquidation judiciaire"},
        ]
        status, _ = _classify_procedures(procs)
        assert status == "BLOCKED"


# ─── Tests get_company_risk (async, mock HTTP) ──────────────────────────────

class TestGetCompanyRisk:

    @pytest.mark.asyncio
    async def test_company_ok_by_siren(self):
        payload = _make_pappers_response(procedures=[])
        mock_resp = _make_httpx_response(payload)

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_client

            result = await get_company_risk(siren="123456789")

        assert result["status"] == "OK"
        assert result["source"] == "pappers"

    @pytest.mark.asyncio
    async def test_redressement_by_name_is_warning(self):
        proc = {"type": "Redressement judiciaire", "date_jugement": "2025-06-01"}
        payload = {"resultats": [_make_pappers_response([proc])]}
        mock_resp = _make_httpx_response(payload)

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_client

            result = await get_company_risk(company_name="ACME SAS")

        assert result["status"] == "WARNING"

    @pytest.mark.asyncio
    async def test_liquidation_by_siren_is_blocked(self):
        proc = {"type": "Liquidation judiciaire", "date_jugement": "2023-03-10"}
        payload = _make_pappers_response([proc])
        mock_resp = _make_httpx_response(payload)

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_client

            result = await get_company_risk(siren="123456789")

        assert result["status"] == "BLOCKED"
        assert is_blocked(result) is True

    @pytest.mark.asyncio
    async def test_radiee_rcs_is_blocked(self):
        payload = _make_pappers_response(procedures=[], statut_rcs="Radiée")
        mock_resp = _make_httpx_response(payload)

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_client

            result = await get_company_risk(siren="123456789")

        assert result["status"] == "BLOCKED"
        assert "radiée" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_api_timeout_returns_unknown(self):
        import httpx as real_httpx

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=real_httpx.TimeoutException("timeout"))
            MockClient.return_value = mock_client

            result = await get_company_risk(company_name="ACME SAS")

        assert result["status"] == "UNKNOWN"
        assert "timeout" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_network_error_returns_unknown(self):
        import httpx as real_httpx

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            MockClient.return_value = mock_client

            result = await get_company_risk(siren="123456789")

        assert result["status"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_no_identifier_returns_unknown(self):
        result = await get_company_risk()
        assert result["status"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_unknown(self):
        with patch("services.risk_check_service._PAPPERS_API_KEY", ""):
            result = await get_company_risk(company_name="ACME SAS")
        assert result["status"] == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_company_not_found_by_name_returns_unknown(self):
        payload = {"resultats": []}
        mock_resp = _make_httpx_response(payload)

        with patch("services.risk_check_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_client

            result = await get_company_risk(company_name="INTROUVABLE SARL")

        assert result["status"] == "UNKNOWN"


# ─── Tests helpers ───────────────────────────────────────────────────────────

class TestHelpers:

    def test_is_blocked_true(self):
        assert is_blocked({"status": "BLOCKED"}) is True

    def test_is_blocked_false_for_warning(self):
        assert is_blocked({"status": "WARNING"}) is False

    def test_is_risky_true_for_warning(self):
        assert is_risky({"status": "WARNING"}) is True

    def test_is_risky_true_for_blocked(self):
        assert is_risky({"status": "BLOCKED"}) is True

    def test_is_risky_false_for_ok(self):
        assert is_risky({"status": "OK"}) is False

    def test_is_risky_false_for_unknown(self):
        assert is_risky({"status": "UNKNOWN"}) is False


# ─── Test intégration pipeline (EmailAnalysisResult accepte client_risk) ────

class TestPipelineIntegration:

    def test_email_analysis_result_accepts_client_risk(self):
        from services.email_analyzer import EmailAnalysisResult
        result = EmailAnalysisResult(
            classification="QUOTE_REQUEST",
            confidence="high",
            is_quote_request=True,
            reasoning="Test",
            client_risk={"status": "WARNING", "reason": "Redressement", "source": "pappers", "raw": {}},
        )
        assert result.client_risk["status"] == "WARNING"

    def test_email_analysis_result_client_risk_defaults_to_none(self):
        from services.email_analyzer import EmailAnalysisResult
        result = EmailAnalysisResult(
            classification="OTHER",
            confidence="low",
            is_quote_request=False,
            reasoning="Test",
        )
        assert result.client_risk is None
