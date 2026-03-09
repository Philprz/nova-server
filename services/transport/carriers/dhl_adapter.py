"""
Adapter DHL Express — API MyDHL
Documentation : https://developer.dhl.com/api-reference/mydhl-api-dhl-express

Authentification : Basic Auth
  Username : rondotFR
  Password : H$3xI$7rU@1kB^9z

Endpoints :
  Test : https://express.api.dhl.com/mydhlapi/test/rates
  Prod : https://express.api.dhl.com/mydhlapi/rates
"""

from __future__ import annotations
import asyncio
import base64
import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

from ..carrier_interface import (
    CarrierAdapter,
    CarrierAPIError,
    Destination,
    PackageInput,
    Shipper,
    ShippingRate,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration DHL (depuis .env ou valeurs par défaut)
# ─────────────────────────────────────────────────────────────────────────────

DHL_USERNAME = os.getenv("DHL_USERNAME", "rondotFR")
DHL_PASSWORD = os.getenv("DHL_PASSWORD", "H$3xI$7rU@1kB^9z")
DHL_ACCOUNT_NUMBER = os.getenv("DHL_ACCOUNT_NUMBER", "220294850")
DHL_SHIPPER_POSTAL = os.getenv("DHL_SHIPPER_POSTAL", "13002")
DHL_SHIPPER_CITY = os.getenv("DHL_SHIPPER_CITY", "MARSEILLE")
DHL_SHIPPER_COUNTRY = os.getenv("DHL_SHIPPER_COUNTRY", "FR")

DHL_USE_TEST_ENV = os.getenv("DHL_USE_TEST_ENV", "true").lower() in ("true", "1", "yes")
DHL_URL_TEST = "https://express.api.dhl.com/mydhlapi/test/rates"
DHL_URL_PROD = "https://express.api.dhl.com/mydhlapi/rates"

DHL_TIMEOUT_SECONDS = float(os.getenv("DHL_TIMEOUT_SECONDS", "15"))
DHL_CACHE_TTL_SECONDS = int(os.getenv("DHL_CACHE_TTL_SECONDS", "300"))  # 5 minutes
DHL_MAX_RETRIES = int(os.getenv("DHL_MAX_RETRIES", "2"))


# ─────────────────────────────────────────────────────────────────────────────
# Cache en mémoire (TTL 5 min)
# ─────────────────────────────────────────────────────────────────────────────

class _RateCache:
    """Cache simple TTL pour les tarifs DHL."""

    def __init__(self, ttl_seconds: int = DHL_CACHE_TTL_SECONDS, max_entries: int = 100):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: Dict[str, Tuple[float, List[ShippingRate]]] = {}

    def _make_key(
        self,
        packages: List[PackageInput],
        destination: Destination,
    ) -> str:
        """Clé de cache : destination + poids total + volume total"""
        total_weight = round(sum(p.weight_kg for p in packages), 2)
        total_volume = round(sum(p.volume_m3 for p in packages), 4)
        raw = (
            f"{destination.country_code}:{destination.postal_code}:"
            f"{destination.city_name}:{total_weight}:{total_volume}"
        )
        return hashlib.md5(raw.encode()).hexdigest()

    def get(
        self, packages: List[PackageInput], destination: Destination
    ) -> Optional[List[ShippingRate]]:
        key = self._make_key(packages, destination)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, rates = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        logger.debug(f"✓ Cache DHL hit : {key[:8]}…")
        return rates

    def set(
        self,
        packages: List[PackageInput],
        destination: Destination,
        rates: List[ShippingRate],
    ) -> None:
        # FIFO cleanup si trop plein
        if len(self._store) >= self._max:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
        key = self._make_key(packages, destination)
        self._store[key] = (time.time(), rates)

    def invalidate(self) -> None:
        self._store.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Adapter DHL
# ─────────────────────────────────────────────────────────────────────────────

class DHLCarrierAdapter(CarrierAdapter):
    """
    Adapter pour l'API DHL Express (MyDHL API).

    Fonctionnalités :
    - Authentification Basic Auth
    - Calcul tarifs (endpoint /rates)
    - Cache TTL 5 minutes par destination + poids/volume
    - Retry automatique (max 2 tentatives)
    - Fallback gracieux sur erreur API
    """

    def __init__(self) -> None:
        self._cache = _RateCache()
        self._base_url = DHL_URL_TEST if DHL_USE_TEST_ENV else DHL_URL_PROD
        self._auth_header = self._build_auth_header()
        env_label = "TEST" if DHL_USE_TEST_ENV else "PROD"
        logger.info(f"✓ DHLCarrierAdapter initialisé [{env_label}] → {self._base_url}")

    @property
    def carrier_name(self) -> str:
        return "DHL Express"

    def is_available(self) -> bool:
        return bool(DHL_USERNAME and DHL_PASSWORD and DHL_ACCOUNT_NUMBER)

    def use_production(self) -> None:
        """Bascule sur l'environnement de production."""
        self._base_url = DHL_URL_PROD
        logger.info("✓ DHL basculé sur environnement PRODUCTION")

    def use_test(self) -> None:
        """Bascule sur l'environnement de test."""
        self._base_url = DHL_URL_TEST
        logger.info("✓ DHL basculé sur environnement TEST")

    # ─────────────────────────────────────────────────────────────
    # Méthode principale
    # ─────────────────────────────────────────────────────────────

    async def get_rate(
        self,
        packages: List[PackageInput],
        destination: Destination,
        shipper: Optional[Shipper] = None,
        declared_value: float = 100.0,
        currency: str = "EUR",
    ) -> List[ShippingRate]:
        """
        Récupère les tarifs DHL Express pour une expédition.

        Args:
            packages: Colis à expédier (poids + dimensions)
            destination: Adresse de livraison
            shipper: Expéditeur (défaut : Marseille RONDOT-SAS)
            declared_value: Valeur déclarée pour douane
            currency: Devise de la valeur déclarée

        Returns:
            Liste des tarifs disponibles, triés par prix croissant

        Raises:
            CarrierAPIError: Si l'API DHL retourne une erreur fatale
        """
        if not self.is_available():
            raise CarrierAPIError("DHL", "Credentials non configurés")

        # Vérifier le cache
        cached = self._cache.get(packages, destination)
        if cached is not None:
            return cached

        # Construire le payload
        effective_shipper = shipper or Shipper()
        payload = self._build_payload(
            packages, destination, effective_shipper, declared_value, currency
        )

        # Appel API avec retry
        raw_response = await self._call_with_retry(payload)

        # Parser la réponse
        rates = self._parse_response(raw_response, packages)

        # Mettre en cache
        self._cache.set(packages, destination, rates)

        return rates

    # ─────────────────────────────────────────────────────────────
    # Construction du payload DHL
    # ─────────────────────────────────────────────────────────────

    def _build_payload(
        self,
        packages: List[PackageInput],
        destination: Destination,
        shipper: Shipper,
        declared_value: float,
        currency: str,
    ) -> Dict[str, Any]:
        """Construit le payload JSON pour l'API DHL /rates"""

        # Date d'expédition = prochain jour ouvré (J+1 à 16h UTC)
        shipping_date = self._next_business_day()

        dhl_packages = []
        for pkg in packages:
            dhl_packages.append(
                {
                    "weight": round(max(pkg.weight_kg, 0.1), 2),  # min 0.1 kg
                    "dimensions": {
                        "length": max(1, int(pkg.length_cm)),
                        "width": max(1, int(pkg.width_cm)),
                        "height": max(1, int(pkg.height_cm)),
                    },
                }
            )

        effective_shipper = shipper if shipper is not None else Shipper()
        payload: Dict[str, Any] = {
            "customerDetails": {
                "shipperDetails": {
                    "postalCode": effective_shipper.postal_code,
                    "cityName": effective_shipper.city_name,
                    "countryCode": effective_shipper.country_code,
                },
                "receiverDetails": {
                    "postalCode": destination.postal_code,
                    "cityName": destination.city_name,
                    "countryCode": destination.country_code,
                },
            },
            "accounts": [
                {
                    "typeCode": "shipper",
                    "number": DHL_ACCOUNT_NUMBER,
                }
            ],
            "plannedShippingDateAndTime": shipping_date,
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": destination.country_code != "FR",  # Vrai si hors France
            "monetaryAmount": [
                {
                    "typeCode": "declaredValue",
                    "value": max(declared_value, 1.0),
                    "currency": currency,
                }
            ],
            "requestAllValueAddedServices": False,
            "returnStandardProductsOnly": True,
            "nextBusinessDay": True,
            "packages": dhl_packages,
        }

        return payload

    # ─────────────────────────────────────────────────────────────
    # Appel HTTP avec retry
    # ─────────────────────────────────────────────────────────────

    async def _call_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Appelle l'API DHL avec retry automatique."""
        last_error: Optional[Exception] = None

        for attempt in range(1, DHL_MAX_RETRIES + 1):
            try:
                return await self._call_api(payload)

            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    f"⚠️ DHL timeout tentative {attempt}/{DHL_MAX_RETRIES}"
                )
                if attempt < DHL_MAX_RETRIES:
                    await asyncio.sleep(1)

            except CarrierAPIError:
                raise  # Ne pas retenter sur erreurs métier

            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"⚠️ DHL erreur tentative {attempt}/{DHL_MAX_RETRIES}: {exc}"
                )
                if attempt < DHL_MAX_RETRIES:
                    await asyncio.sleep(1)

        raise CarrierAPIError(
            "DHL",
            f"Échec après {DHL_MAX_RETRIES} tentatives : {last_error}",
        )

    async def _call_api(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Appelle l'endpoint DHL /rates."""
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(
            verify=True, timeout=DHL_TIMEOUT_SECONDS
        ) as client:
            logger.debug(f"→ DHL POST {self._base_url}")
            response = await client.post(
                self._base_url, json=payload, headers=headers
            )

        if response.status_code == 200:
            logger.info(f"✓ DHL API réponse 200 OK")
            return response.json()

        # Gestion des erreurs HTTP
        try:
            error_body = response.json()
            detail = error_body.get("detail") or error_body.get("message") or str(error_body)
        except Exception:
            detail = response.text[:200]

        if response.status_code == 401:
            raise CarrierAPIError("DHL", f"Authentification invalide : {detail}", 401)
        if response.status_code == 400:
            raise CarrierAPIError("DHL", f"Payload invalide : {detail}", 400)
        if response.status_code == 404:
            raise CarrierAPIError("DHL", f"Aucun tarif disponible : {detail}", 404)
        if response.status_code >= 500:
            raise CarrierAPIError(
                "DHL", f"Erreur serveur DHL ({response.status_code}) : {detail}",
                response.status_code,
            )

        raise CarrierAPIError(
            "DHL", f"HTTP {response.status_code} : {detail}", response.status_code
        )

    # ─────────────────────────────────────────────────────────────
    # Parsing de la réponse
    # ─────────────────────────────────────────────────────────────

    def _parse_response(
        self,
        raw: Dict[str, Any],
        packages: List[PackageInput],
    ) -> List[ShippingRate]:
        """
        Parse la réponse DHL et retourne une liste de ShippingRate triée par prix.

        Structure DHL response :
        {
            "products": [
                {
                    "productCode": "P",
                    "productName": "DHL EXPRESS WORLDWIDE",
                    "totalPrice": [{"price": 45.20, "priceCurrency": "EUR"}],
                    "deliveryCapabilities": {"estimatedDeliveryDateAndTime": "...", "totalTransitDays": 2}
                }
            ]
        }
        """
        products = raw.get("products", [])
        if not products:
            logger.warning("⚠️ DHL API : aucun produit retourné")
            return []

        total_weight = round(sum(p.weight_kg for p in packages), 2)
        package_count = len(packages)

        rates: List[ShippingRate] = []

        for product in products:
            try:
                service_code = product.get("productCode", "")
                service_name = product.get("productName", service_code)

                # Prix
                price_list = product.get("totalPrice", [])
                price = 0.0
                price_currency = "EUR"
                for price_entry in price_list:
                    if price_entry.get("priceCurrency", "").upper() == "EUR":
                        price = float(price_entry.get("price", 0))
                        price_currency = "EUR"
                        break
                # Fallback : premier prix dispo
                if price == 0.0 and price_list:
                    price = float(price_list[0].get("price", 0))
                    price_currency = price_list[0].get("priceCurrency", "EUR")

                # Délai livraison
                delivery_caps = product.get("deliveryCapabilities", {})
                transit_days = int(delivery_caps.get("totalTransitDays", 1) or 1)
                delivery_date = delivery_caps.get("estimatedDeliveryDateAndTime")

                rates.append(
                    ShippingRate(
                        carrier="DHL Express",
                        service_code=service_code,
                        service_name=service_name,
                        price=round(price, 2),
                        currency=price_currency,
                        delivery_days=transit_days,
                        delivery_date=delivery_date,
                        total_weight_kg=total_weight,
                        package_count=package_count,
                        raw_response=product,
                    )
                )

            except Exception as exc:
                logger.warning(f"⚠️ Parsing produit DHL ignoré : {exc}")
                continue

        # Trier par prix croissant
        rates.sort(key=lambda r: r.price)

        logger.info(
            f"✓ DHL : {len(rates)} tarif(s) — "
            f"min {rates[0].price:.2f} {rates[0].currency} "
            f"({rates[0].service_name})"
            if rates else "✓ DHL : aucun tarif"
        )

        return rates

    # ─────────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────────

    def _build_auth_header(self) -> str:
        """Construit le header Authorization Basic."""
        credentials = f"{DHL_USERNAME}:{DHL_PASSWORD}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    @staticmethod
    def _next_business_day() -> str:
        """Retourne le prochain jour ouvré à 16h UTC au format DHL."""
        now = datetime.now(tz=timezone.utc)
        # Avancer d'un jour
        candidate = now + timedelta(days=1)
        # Sauter le week-end
        while candidate.weekday() >= 5:  # 5=Sam, 6=Dim
            candidate += timedelta(days=1)
        # Formater : "2026-03-05T16:00:00GMT+00:00"
        return candidate.strftime("%Y-%m-%dT16:00:00GMT+00:00")


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_dhl_adapter: Optional[DHLCarrierAdapter] = None


def get_dhl_adapter() -> DHLCarrierAdapter:
    """Factory singleton de l'adapter DHL."""
    global _dhl_adapter
    if _dhl_adapter is None:
        _dhl_adapter = DHLCarrierAdapter()
    return _dhl_adapter
