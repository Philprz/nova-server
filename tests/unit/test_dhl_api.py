"""
Tests DHL Express API — Adapter + Service Transport
Couvre : DHLCarrierAdapter, TransportService, mapping réponse, gestion erreurs

IMPORTANT : Ces tests appellent l'API DHL réelle (env TEST).
  Username : rondotFR
  Password : H$3xI$7rU@1kB^9z
  Endpoint : https://express.api.dhl.com/mydhlapi/test/rates

Pour exécuter en isolation sans réseau, utiliser le marqueur --skip-api.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.transport.carrier_interface import (
    Destination,
    PackageInput,
    ShippingRate,
    Shipper,
)
from services.transport.carriers.dhl_adapter import (
    DHLCarrierAdapter,
    _RateCache,
    DHL_URL_TEST,
)
from services.transport.transport_service import TransportService


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def adapter():
    """Adapter DHL pointant sur l'env TEST."""
    a = DHLCarrierAdapter()
    a._base_url = DHL_URL_TEST
    return a


@pytest.fixture
def one_package():
    return [PackageInput(weight_kg=1.0, length_cm=30.0, width_cm=20.0, height_cm=20.0)]


@pytest.fixture
def destination_paris():
    return Destination(postal_code="75001", city_name="PARIS", country_code="FR")


@pytest.fixture
def destination_dubai():
    return Destination(postal_code="DUBAI", city_name="DUBAI", country_code="AE")


# ─────────────────────────────────────────────────────────────────────────────
# RateCache
# ─────────────────────────────────────────────────────────────────────────────

class TestRateCache:
    def test_cache_miss(self, one_package, destination_paris):
        cache = _RateCache(ttl_seconds=300)
        assert cache.get(one_package, destination_paris) is None

    def test_cache_hit(self, one_package, destination_paris):
        cache = _RateCache(ttl_seconds=300)
        fake_rates = [
            ShippingRate(
                carrier="DHL Express",
                service_code="P",
                service_name="DHL EXPRESS WORLDWIDE",
                price=45.0,
                currency="EUR",
                delivery_days=2,
            )
        ]
        cache.set(one_package, destination_paris, fake_rates)
        result = cache.get(one_package, destination_paris)
        assert result is not None
        assert len(result) == 1
        assert result[0].price == 45.0

    def test_cache_ttl_expired(self, one_package, destination_paris):
        cache = _RateCache(ttl_seconds=0)  # TTL immédiat
        fake_rates = [
            ShippingRate(
                carrier="DHL Express",
                service_code="P",
                service_name="TEST",
                price=10.0,
                currency="EUR",
                delivery_days=1,
            )
        ]
        cache.set(one_package, destination_paris, fake_rates)
        import time
        time.sleep(0.01)
        assert cache.get(one_package, destination_paris) is None

    def test_different_destinations_different_keys(self, one_package, destination_paris, destination_dubai):
        cache = _RateCache()
        fake = [ShippingRate(carrier="DHL", service_code="P", service_name="X", price=10, currency="EUR", delivery_days=1)]
        cache.set(one_package, destination_paris, fake)
        assert cache.get(one_package, destination_dubai) is None

    def test_invalidate_clears_cache(self, one_package, destination_paris):
        cache = _RateCache()
        fake = [ShippingRate(carrier="DHL", service_code="P", service_name="X", price=10, currency="EUR", delivery_days=1)]
        cache.set(one_package, destination_paris, fake)
        cache.invalidate()
        assert cache.get(one_package, destination_paris) is None


# ─────────────────────────────────────────────────────────────────────────────
# DHLCarrierAdapter — Construction payload
# ─────────────────────────────────────────────────────────────────────────────

class TestDHLPayloadBuilding:
    def test_build_payload_structure(self, adapter, one_package, destination_paris):
        payload = adapter._build_payload(
            packages=one_package,
            destination=destination_paris,
            shipper=Shipper(),
            declared_value=100.0,
            currency="EUR",
        )
        assert "customerDetails" in payload
        assert "accounts" in payload
        assert "packages" in payload
        assert "plannedShippingDateAndTime" in payload
        assert payload["unitOfMeasurement"] == "metric"

    def test_shipper_defaults(self, adapter, one_package, destination_paris):
        payload = adapter._build_payload(
            packages=one_package,
            destination=destination_paris,
            shipper=Shipper(),
            declared_value=100.0,
            currency="EUR",
        )
        shipper = payload["customerDetails"]["shipperDetails"]
        assert shipper["countryCode"] == "FR"
        assert shipper["cityName"] == "MARSEILLE"
        assert shipper["postalCode"] == "13002"

    def test_account_number_set(self, adapter, one_package, destination_paris):
        payload = adapter._build_payload(
            one_package, destination_paris, Shipper(), 100.0, "EUR"
        )
        assert payload["accounts"][0]["number"] == "220294850"
        assert payload["accounts"][0]["typeCode"] == "shipper"

    def test_package_format(self, adapter, one_package, destination_paris):
        payload = adapter._build_payload(
            one_package, destination_paris, Shipper(), 100.0, "EUR"
        )
        pkg = payload["packages"][0]
        assert "weight" in pkg
        assert "dimensions" in pkg
        assert set(pkg["dimensions"].keys()) == {"length", "width", "height"}

    def test_min_weight_enforced(self, adapter, destination_paris):
        tiny = [PackageInput(weight_kg=0.05, length_cm=5.0, width_cm=5.0, height_cm=5.0)]
        payload = adapter._build_payload(tiny, destination_paris, Shipper(), 10.0, "EUR")
        assert payload["packages"][0]["weight"] >= 0.1

    def test_international_sets_customs(self, adapter, one_package, destination_dubai):
        payload = adapter._build_payload(
            one_package, destination_dubai, Shipper(), 500.0, "EUR"
        )
        assert payload["isCustomsDeclarable"] is True

    def test_domestic_no_customs(self, adapter, one_package, destination_paris):
        payload = adapter._build_payload(
            one_package, destination_paris, Shipper(), 100.0, "EUR"
        )
        assert payload["isCustomsDeclarable"] is False

    def test_next_business_day_format(self, adapter):
        date_str = adapter._next_business_day()
        assert "GMT+00:00" in date_str
        assert "T16:00:00" in date_str


# ─────────────────────────────────────────────────────────────────────────────
# DHLCarrierAdapter — Parsing réponse
# ─────────────────────────────────────────────────────────────────────────────

class TestDHLResponseParsing:
    def _sample_response(self) -> dict:
        return {
            "products": [
                {
                    "productCode": "P",
                    "productName": "DHL EXPRESS WORLDWIDE",
                    "totalPrice": [{"price": 45.20, "priceCurrency": "EUR"}],
                    "deliveryCapabilities": {
                        "estimatedDeliveryDateAndTime": "2026-03-06T12:00:00",
                        "totalTransitDays": 2,
                    },
                },
                {
                    "productCode": "K",
                    "productName": "DHL EXPRESS 9:00",
                    "totalPrice": [{"price": 78.50, "priceCurrency": "EUR"}],
                    "deliveryCapabilities": {
                        "totalTransitDays": 1,
                    },
                },
            ]
        }

    def test_parse_returns_rates(self, adapter, one_package):
        rates = adapter._parse_response(self._sample_response(), one_package)
        assert len(rates) == 2

    def test_rates_sorted_by_price(self, adapter, one_package):
        rates = adapter._parse_response(self._sample_response(), one_package)
        prices = [r.price for r in rates]
        assert prices == sorted(prices)

    def test_rate_fields(self, adapter, one_package):
        rates = adapter._parse_response(self._sample_response(), one_package)
        r = rates[0]
        assert r.carrier == "DHL Express"
        assert r.service_code == "P"
        assert r.price == pytest.approx(45.20)
        assert r.currency == "EUR"
        assert r.delivery_days == 2

    def test_empty_products(self, adapter, one_package):
        rates = adapter._parse_response({"products": []}, one_package)
        assert rates == []

    def test_total_weight_set(self, adapter):
        packages = [
            PackageInput(weight_kg=5.0, length_cm=30.0, width_cm=20.0, height_cm=20.0),
            PackageInput(weight_kg=3.0, length_cm=20.0, width_cm=15.0, height_cm=15.0),
        ]
        rates = adapter._parse_response(self._sample_response(), packages)
        assert rates[0].total_weight_kg == pytest.approx(8.0)
        assert rates[0].package_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# DHLCarrierAdapter — Gestion erreurs HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestDHLErrorHandling:
    @pytest.mark.asyncio
    async def test_401_raises_carrier_error(self, adapter, one_package, destination_paris):
        from services.transport.carrier_interface import CarrierAPIError
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Unauthorized"}

        with patch.object(adapter, "_call_api", side_effect=CarrierAPIError("DHL", "Authentification invalide", 401)):
            with pytest.raises(CarrierAPIError) as exc_info:
                await adapter.get_rate(one_package, destination_paris)
            assert "Authentification" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_retries(self, adapter, one_package, destination_paris):
        import httpx
        call_count = 0

        async def failing_call(payload):
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timeout")

        with patch.object(adapter, "_call_api", side_effect=failing_call):
            from services.transport.carrier_interface import CarrierAPIError
            with pytest.raises(CarrierAPIError):
                await adapter.get_rate(one_package, destination_paris)

        # Doit avoir tenté DHL_MAX_RETRIES fois
        from services.transport.carriers.dhl_adapter import DHL_MAX_RETRIES
        assert call_count == DHL_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_cache_used_on_second_call(self, adapter, one_package, destination_paris):
        """Le second appel doit utiliser le cache, pas appeler l'API."""
        fake_rates = [
            ShippingRate(
                carrier="DHL Express",
                service_code="P",
                service_name="DHL EXPRESS WORLDWIDE",
                price=50.0,
                currency="EUR",
                delivery_days=2,
            )
        ]
        # Pré-remplir le cache
        adapter._cache.set(one_package, destination_paris, fake_rates)

        call_count = 0

        async def api_call(payload):
            nonlocal call_count
            call_count += 1
            return {"products": []}

        with patch.object(adapter, "_call_api", side_effect=api_call):
            rates = await adapter.get_rate(one_package, destination_paris)

        assert call_count == 0  # API non appelée grâce au cache
        assert len(rates) == 1
        assert rates[0].price == 50.0


# ─────────────────────────────────────────────────────────────────────────────
# TransportService — Normalisation packages
# ─────────────────────────────────────────────────────────────────────────────

class TestTransportServiceNormalization:
    def setup_method(self):
        self.service = TransportService.__new__(TransportService)
        self.service._carriers = {}  # Pas de carriers pour ces tests unitaires

    def test_normalize_valid_package(self):
        raw = [{"weight": 10.0, "dimensions": {"length": 60, "width": 40, "height": 40}}]
        result = self.service._normalize_packages(raw)
        assert len(result) == 1
        assert result[0].weight_kg == 10.0
        assert result[0].length_cm == 60.0

    def test_normalize_multiple_packages(self):
        raw = [
            {"weight": 5.0, "dimensions": {"length": 30, "width": 20, "height": 20}},
            {"weight": 15.0, "dimensions": {"length": 60, "width": 40, "height": 40}},
        ]
        result = self.service._normalize_packages(raw)
        assert len(result) == 2

    def test_normalize_zero_weight_ignored(self):
        raw = [{"weight": 0.0, "dimensions": {"length": 30, "width": 20, "height": 20}}]
        result = self.service._normalize_packages(raw)
        assert len(result) == 0

    def test_normalize_missing_dimensions_defaults_to_1(self):
        raw = [{"weight": 5.0, "dimensions": {}}]
        result = self.service._normalize_packages(raw)
        assert len(result) == 1
        assert result[0].length_cm == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Test d'intégration (API réelle DHL TEST)
# Désactiver avec : pytest -k "not integration"
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_dhl_api_real_call():
    """
    Test d'intégration réel — appelle l'API DHL TEST.
    Nécessite une connexion réseau et des credentials valides.
    """
    adapter = DHLCarrierAdapter()
    packages = [PackageInput(weight_kg=1.0, length_cm=30.0, width_cm=20.0, height_cm=20.0)]
    destination = Destination(postal_code="75001", city_name="PARIS", country_code="FR")

    rates = await adapter.get_rate(packages=packages, destination=destination, declared_value=10.0)

    # L'env TEST peut retourner 0 tarifs selon configuration DHL
    assert isinstance(rates, list)
    for rate in rates:
        assert rate.price >= 0
        assert rate.currency != ""
        assert rate.service_code != ""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dhl_api_international():
    """Test international France → Dubaï."""
    adapter = DHLCarrierAdapter()
    packages = [PackageInput(weight_kg=5.0, length_cm=40.0, width_cm=30.0, height_cm=30.0)]
    destination = Destination(postal_code="DUBAI", city_name="DUBAI", country_code="AE")

    rates = await adapter.get_rate(
        packages=packages,
        destination=destination,
        declared_value=100.0,
    )

    assert isinstance(rates, list)
