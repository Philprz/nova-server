"""
Tests Quota de devis - NOVA-SERVER
tests/test_quote_quota.py

Couvre :
1. QuoteQuotaService (sur SQLite en mémoire, aucune dépendance PostgreSQL) :
   - 50e devis accepté, 51e bloqué (QuotaDevisDepasse)
   - increment atomique cumulant les deux chemins de création (quota partagé)
   - remise à zéro au changement de mois calendaire
2. Branchement sur create_sales_quotation (mock SAP, aucun vrai devis créé) :
   - quota atteint → QuotaDevisDepasse levée AVANT l'appel SAP (pas de création)
   - création réussie → compteur incrémenté

Usage :
    pytest tests/test_quote_quota.py -v
"""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database_models import Base, QuoteUsageCounter
from services.quote_quota_service import QuoteQuotaService, QuotaDevisDepasse


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def session_factory():
    """sessionmaker sur une base SQLite en mémoire partagée (table créée)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def quota(session_factory):
    """Service de quota de test : max 50, société 'RONDOT'."""
    return QuoteQuotaService(
        session_factory=session_factory,
        default_society="RONDOT",
        default_max_quota=50,
    )


# ============================================================
# TESTS : SERVICE QUOTA
# ============================================================


class TestQuotaService:

    def test_first_check_creates_row_at_zero(self, quota, session_factory):
        """Le premier check_quota crée la ligne du mois à 0 et renvoie le restant."""
        remaining = quota.check_quota()
        assert remaining == 50
        with session_factory() as s:
            rows = s.query(QuoteUsageCounter).all()
            assert len(rows) == 1
            assert rows[0].count == 0
            assert rows[0].max_quota == 50

    def test_increment_increases_count(self, quota):
        """increment renvoie le nouveau compteur."""
        assert quota.increment() == 1
        assert quota.increment() == 2

    def test_50th_accepted_51st_blocked(self, quota):
        """Les 50 premiers passent, le 51e est bloqué (QuotaDevisDepasse)."""
        for i in range(50):
            # check_quota ne doit pas lever tant que count < 50
            quota.check_quota()
            quota.increment()

        # Le compteur est à 50 → le 51e check doit lever
        with pytest.raises(QuotaDevisDepasse) as exc_info:
            quota.check_quota()

        err = exc_info.value
        assert err.count == 50
        assert err.max_quota == 50
        assert err.error_code == "QUOTA_DEVIS_DEPASSE"
        assert err.period == datetime.now().strftime("%Y-%m")

    def test_shared_quota_across_two_paths(self, quota):
        """Quota partagé : deux 'bases SAP' (mêmes society/period) cumulent.

        Simule les deux chemins de création en incrémentant la même clé logique :
        le total doit plafonner à 50, pas 100.
        """
        for _ in range(25):
            quota.increment(society="RONDOT")  # chemin A
            quota.increment(society="RONDOT")  # chemin B
        with pytest.raises(QuotaDevisDepasse):
            quota.check_quota(society="RONDOT")

    def test_reset_on_month_change(self, quota):
        """Au changement de mois calendaire, le compteur repart de zéro."""
        # Remplir le mois M
        for _ in range(50):
            quota.increment(period="2026-06")
        with pytest.raises(QuotaDevisDepasse):
            quota.check_quota(period="2026-06")

        # Mois suivant M+1 : ligne distincte, quota de nouveau disponible
        remaining = quota.check_quota(period="2026-07")
        assert remaining == 50
        assert quota.increment(period="2026-07") == 1

    def test_period_isolation(self, quota, session_factory):
        """Deux périodes => deux lignes distinctes."""
        quota.increment(period="2026-06")
        quota.increment(period="2026-07")
        with session_factory() as s:
            assert s.query(QuoteUsageCounter).count() == 2


# ============================================================
# TESTS : BRANCHEMENT create_sales_quotation (mock SAP)
# ============================================================


class TestQuotaWiringSalesQuotation:

    @pytest.fixture
    def sap_service(self):
        from services.sap_quotation_service import SAPQuotationService
        with patch.dict(os.environ, {
            "SAP_REST_BASE_URL": "https://test-sap:50000/b1s/v1",
            "SAP_USER_RONDOT": "manager",
            "SAP_CLIENT_RONDOT": "RON_TEST",
            "SAP_CLIENT_PASSWORD_RONDOT": "testpass",
        }):
            return SAPQuotationService()

    @pytest.fixture
    def payload(self):
        from services.sap_quotation_service import QuotationLine, QuotationPayload
        return QuotationPayload(
            CardCode="C00042",
            DocumentLines=[QuotationLine(ItemDescription="Pièce test", Quantity=1, UnitPrice=10.0)],
        )

    @pytest.mark.asyncio
    async def test_quota_exceeded_blocks_before_sap(self, sap_service, payload, quota):
        """Quota plein → QuotaDevisDepasse AVANT tout appel SAP (aucune création)."""
        # Remplir le quota
        for _ in range(50):
            quota.increment()

        no_sap = AsyncMock(side_effect=AssertionError("SAP ne doit pas être appelé"))
        with patch("services.sap_quotation_service.get_quote_quota_service", return_value=quota), \
             patch.object(sap_service, "ensure_session", new=AsyncMock(return_value=True)), \
             patch.object(sap_service, "_call_sap_post", new=no_sap):
            with pytest.raises(QuotaDevisDepasse):
                await sap_service.create_sales_quotation(payload)

        no_sap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_successful_creation_increments_counter(self, sap_service, payload, quota, session_factory):
        """Création SAP réussie → compteur incrémenté de 1."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "DocEntry": 4242, "DocNum": 1337, "DocTotal": 10.0,
            "DocDate": "2026-06-17", "CardCode": "C00042",
        }

        sap_service.session_id = "FAKE"
        sap_service.session_timeout = datetime(2099, 1, 1)

        with patch("services.sap_quotation_service.get_quote_quota_service", return_value=quota), \
             patch.object(sap_service, "ensure_session", new=AsyncMock(return_value=True)), \
             patch.object(sap_service, "_call_sap_post", new=AsyncMock(return_value=mock_response)):
            result = await sap_service.create_sales_quotation(payload)

        assert result.success is True
        with session_factory() as s:
            row = s.query(QuoteUsageCounter).filter_by(society_id="RONDOT").first()
            assert row is not None
            assert row.count == 1


# ============================================================
# TESTS : BRANCHEMENT 3e chemin — routes_sap_rondot (mock SAP)
# ============================================================


class TestQuotaWiringRondotRoute:
    """Le 3e chemin de création (POST /api/sap-rondot/quotations) est aussi gété."""

    def _request(self):
        from routes.routes_sap_rondot import CreateQuoteRequest, QuoteLine
        return CreateQuoteRequest(
            CardCode="C00042",
            DocumentLines=[QuoteLine(ItemCode="ART-1", Quantity=1, UnitPrice=10.0)],
        )

    @pytest.mark.asyncio
    async def test_quota_exceeded_blocks_before_sap(self, quota):
        """Quota plein → QuotaDevisDepasse AVANT call_sap_rondot (aucune création)."""
        from routes import routes_sap_rondot

        for _ in range(50):
            quota.increment()

        no_sap = AsyncMock(side_effect=AssertionError("SAP ne doit pas être appelé"))
        with patch.object(routes_sap_rondot, "get_quote_quota_service", return_value=quota), \
             patch.object(routes_sap_rondot, "call_sap_rondot", new=no_sap):
            with pytest.raises(QuotaDevisDepasse):
                await routes_sap_rondot.create_sap_rondot_quotation(self._request())

        no_sap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_successful_creation_increments_counter(self, quota, session_factory):
        """Création réussie via le chemin rondot → compteur incrémenté de 1."""
        from routes import routes_sap_rondot

        sap_ok = AsyncMock(return_value={
            "DocEntry": 77, "DocNum": 88, "CardCode": "C00042", "DocTotal": 10.0,
        })
        with patch.object(routes_sap_rondot, "get_quote_quota_service", return_value=quota), \
             patch.object(routes_sap_rondot, "call_sap_rondot", new=sap_ok):
            resp = await routes_sap_rondot.create_sap_rondot_quotation(self._request())

        assert resp["success"] is True
        assert resp["quotation"]["DocEntry"] == 77
        with session_factory() as s:
            row = s.query(QuoteUsageCounter).filter_by(society_id="RONDOT").first()
            assert row is not None
            assert row.count == 1
