"""
services/currency_service.py
Service de gestion des taux de change et conversions de devises
"""

import os
import logging
import httpx
from typing import Optional, Dict
from datetime import datetime, timedelta
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExchangeRate(BaseModel):
    """Taux de change entre deux devises"""
    from_currency: str
    to_currency: str
    rate: float
    last_updated: datetime


class CurrencyService:
    """
    Service de taux de change avec cache
    Supporte EUR, USD, GBP, CHF
    """

    # Devises supportées
    SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "CHF"]

    # API par défaut : exchangerate-api.com (gratuit, 1500 requêtes/mois)
    # Alternative : fixer.io, currencyapi.com
    API_BASE_URL = "https://api.exchangerate-api.com/v4/latest"

    def __init__(self):
        self.base_currency = os.getenv("PRICING_BASE_CURRENCY", "EUR")
        self.cache: Dict[str, ExchangeRate] = {}
        self.cache_duration_hours = int(os.getenv("CURRENCY_CACHE_HOURS", "4"))  # 4h par défaut

    async def get_exchange_rate(
        self,
        from_currency: str,
        to_currency: str,
        force_refresh: bool = False
    ) -> Optional[ExchangeRate]:
        """
        Récupère le taux de change entre deux devises

        Args:
            from_currency: Devise source (EUR, USD, GBP, CHF)
            to_currency: Devise cible
            force_refresh: Force le rafraîchissement du cache

        Returns:
            ExchangeRate ou None si erreur
        """
        # Normaliser les devises
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # Vérifier devises supportées
        if from_currency not in self.SUPPORTED_CURRENCIES or to_currency not in self.SUPPORTED_CURRENCIES:
            logger.error(f"Devise non supportée: {from_currency} ou {to_currency}")
            return None

        # Même devise = taux 1.0
        if from_currency == to_currency:
            return ExchangeRate(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=1.0,
                last_updated=datetime.utcnow()
            )

        # Vérifier cache
        cache_key = f"{from_currency}_{to_currency}"
        if not force_refresh and cache_key in self.cache:
            cached_rate = self.cache[cache_key]
            age = datetime.utcnow() - cached_rate.last_updated
            if age < timedelta(hours=self.cache_duration_hours):
                logger.debug(f"✓ Cache hit: {cache_key} = {cached_rate.rate}")
                return cached_rate

        # Récupérer depuis l'API
        try:
            rate_value = await self._fetch_rate_from_api(from_currency, to_currency)
            if rate_value is None:
                return None

            exchange_rate = ExchangeRate(
                from_currency=from_currency,
                to_currency=to_currency,
                rate=rate_value,
                last_updated=datetime.utcnow()
            )

            # Mettre en cache
            self.cache[cache_key] = exchange_rate
            logger.info(f"✓ Taux de change mis à jour: {cache_key} = {rate_value}")

            return exchange_rate

        except Exception as e:
            logger.error(f"✗ Erreur récupération taux de change: {e}")
            return None

    async def _fetch_rate_from_api(
        self,
        from_currency: str,
        to_currency: str
    ) -> Optional[float]:
        """Récupère le taux depuis l'API externe"""
        url = f"{self.API_BASE_URL}/{from_currency}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.error(f"Erreur API taux de change: HTTP {response.status_code}")
                    return None

                data = response.json()

                if "rates" not in data or to_currency not in data["rates"]:
                    logger.error(f"Taux {to_currency} non trouvé dans la réponse")
                    return None

                rate = float(data["rates"][to_currency])
                return rate

        except httpx.RequestError as e:
            logger.error(f"Erreur réseau API taux de change: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur parsing réponse API: {e}")
            return None

    async def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str
    ) -> Optional[float]:
        """
        Convertit un montant d'une devise à une autre

        Args:
            amount: Montant à convertir
            from_currency: Devise source
            to_currency: Devise cible

        Returns:
            Montant converti ou None si erreur
        """
        if amount == 0:
            return 0.0

        rate_data = await self.get_exchange_rate(from_currency, to_currency)
        if rate_data is None:
            return None

        converted = round(amount * rate_data.rate, 2)
        logger.debug(f"✓ Conversion: {amount} {from_currency} = {converted} {to_currency}")

        return converted

    async def convert_to_base(
        self,
        amount: float,
        from_currency: str
    ) -> Optional[float]:
        """
        Convertit un montant vers la devise de base (EUR)
        """
        return await self.convert(amount, from_currency, self.base_currency)

    async def convert_from_base(
        self,
        amount: float,
        to_currency: str
    ) -> Optional[float]:
        """
        Convertit un montant depuis la devise de base (EUR)
        """
        return await self.convert(amount, self.base_currency, to_currency)

    async def get_all_rates_from_base(self) -> Dict[str, float]:
        """
        Récupère tous les taux depuis la devise de base
        """
        rates = {}

        for currency in self.SUPPORTED_CURRENCIES:
            if currency == self.base_currency:
                rates[currency] = 1.0
                continue

            rate_data = await self.get_exchange_rate(self.base_currency, currency)
            if rate_data:
                rates[currency] = rate_data.rate

        return rates

    def clear_cache(self):
        """Vide le cache des taux de change"""
        self.cache.clear()
        logger.info("✓ Cache taux de change vidé")

    def get_cache_status(self) -> Dict[str, any]:
        """Retourne le statut du cache"""
        cache_entries = []

        for key, rate in self.cache.items():
            age_seconds = (datetime.utcnow() - rate.last_updated).total_seconds()
            cache_entries.append({
                "pair": key,
                "rate": rate.rate,
                "age_seconds": int(age_seconds),
                "is_fresh": age_seconds < (self.cache_duration_hours * 3600)
            })

        return {
            "cached_pairs": len(self.cache),
            "cache_duration_hours": self.cache_duration_hours,
            "base_currency": self.base_currency,
            "supported_currencies": self.SUPPORTED_CURRENCIES,
            "entries": cache_entries
        }


# Singleton
_currency_service = None


def get_currency_service() -> CurrencyService:
    """Retourne l'instance singleton du service de devises"""
    global _currency_service
    if _currency_service is None:
        _currency_service = CurrencyService()
        logger.info("CurrencyService initialisé")
    return _currency_service
