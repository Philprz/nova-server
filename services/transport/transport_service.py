"""
Service de transport NOVA
Orchestre les adapters carriers et expose calculate_shipping()

Pipeline :
  PackingResponse (dhl_packages)
    → TransportService.calculate_shipping()
    → DHLCarrierAdapter.get_rate()
    → ShippingRate (prix, délai, service)
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .carrier_interface import (
    CarrierAdapter,
    CarrierAPIError,
    Destination,
    PackageInput,
    Shipper,
    ShippingRate,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Modèles d'entrée / sortie du service
# ─────────────────────────────────────────────────────────────────────────────

class ShippingRequest(BaseModel):
    """Requête de calcul transport"""
    packages: List[Dict[str, Any]] = Field(
        description="Colis au format DHL : [{weight, dimensions:{length,width,height}}]"
    )
    destination: Destination
    shipper: Optional[Shipper] = None
    declared_value: float = Field(default=100.0, ge=0.0)
    currency: str = Field(default="EUR")
    carrier: str = Field(default="dhl", description="Carrier à utiliser (dhl, all)")

    class Config:
        json_schema_extra = {
            "example": {
                "packages": [
                    {"weight": 10.0, "dimensions": {"length": 60, "width": 40, "height": 40}}
                ],
                "destination": {
                    "postal_code": "75001",
                    "city_name": "PARIS",
                    "country_code": "FR"
                },
                "declared_value": 500.0,
                "currency": "EUR"
            }
        }


class ShippingResponse(BaseModel):
    """Réponse du service de transport"""
    success: bool
    rates: List[Dict[str, Any]] = Field(default_factory=list)
    best_rate: Optional[Dict[str, Any]] = None
    total_weight_kg: float = Field(default=0.0)
    package_count: int = Field(default=0)
    error: Optional[str] = None
    carrier_errors: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "rates": [
                    {
                        "carrier": "DHL Express",
                        "service_code": "P",
                        "service_name": "DHL EXPRESS WORLDWIDE",
                        "price": 45.20,
                        "currency": "EUR",
                        "delivery_days": 2
                    }
                ],
                "best_rate": {"carrier": "DHL Express", "price": 45.20},
                "total_weight_kg": 10.5,
                "package_count": 2
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Service principal
# ─────────────────────────────────────────────────────────────────────────────

class TransportService:
    """
    Service de transport NOVA.

    Responsabilités :
    - Orchestrer un ou plusieurs adapters carriers
    - Normaliser les données packages depuis PackingResponse
    - Retourner les tarifs disponibles triés par prix
    - Gérer les erreurs carrier avec fallback gracieux
    """

    def __init__(self) -> None:
        self._carriers: Dict[str, CarrierAdapter] = {}
        self._register_default_carriers()

    def _register_default_carriers(self) -> None:
        """Initialise les adapters configurés."""
        try:
            from .carriers.dhl_adapter import get_dhl_adapter
            dhl = get_dhl_adapter()
            if dhl.is_available():
                self._carriers["dhl"] = dhl
                logger.info("✓ TransportService : DHL Express enregistré")
            else:
                logger.warning("⚠️ DHL credentials absents — carrier non enregistré")
        except Exception as exc:
            logger.error(f"✗ Erreur chargement adapter DHL : {exc}")

    def register_carrier(self, key: str, adapter: CarrierAdapter) -> None:
        """Enregistre un carrier supplémentaire (UPS, Chronopost…)."""
        self._carriers[key] = adapter
        logger.info(f"✓ Carrier '{key}' ({adapter.carrier_name}) enregistré")

    # ─────────────────────────────────────────────────────────────
    # Méthode principale
    # ─────────────────────────────────────────────────────────────

    async def calculate_shipping(
        self,
        packages: List[Dict[str, Any]],
        destination: Destination,
        shipper: Optional[Shipper] = None,
        declared_value: float = 100.0,
        currency: str = "EUR",
        carrier: str = "dhl",
    ) -> ShippingResponse:
        """
        Calcule le coût d'expédition pour une liste de colis.

        Args:
            packages: Colis au format [{weight, dimensions:{length,width,height}}]
            destination: Adresse de livraison
            shipper: Expéditeur (défaut : Marseille)
            declared_value: Valeur déclarée pour la douane
            currency: Devise de la valeur déclarée
            carrier: "dhl" ou "all" pour interroger tous les carriers

        Returns:
            ShippingResponse avec tarifs triés + meilleur tarif
        """
        if not self._carriers:
            return ShippingResponse(
                success=False,
                error="Aucun carrier configuré"
            )

        # Normaliser les packages
        package_inputs = self._normalize_packages(packages)
        if not package_inputs:
            return ShippingResponse(
                success=False,
                error="Aucun colis valide fourni"
            )

        total_weight = round(sum(p.weight_kg for p in package_inputs), 2)

        # Sélectionner les carriers à interroger
        carriers_to_query: Dict[str, CarrierAdapter] = {}
        if carrier == "all":
            carriers_to_query = self._carriers
        elif carrier in self._carriers:
            carriers_to_query = {carrier: self._carriers[carrier]}
        else:
            # Fallback sur premier carrier disponible
            first_key = next(iter(self._carriers))
            carriers_to_query = {first_key: self._carriers[first_key]}
            logger.warning(
                f"⚠️ Carrier '{carrier}' inconnu — fallback sur '{first_key}'"
            )

        # Appeler chaque carrier
        all_rates: List[ShippingRate] = []
        carrier_errors: List[str] = []

        for key, adapter in carriers_to_query.items():
            try:
                rates = await adapter.get_rate(
                    packages=package_inputs,
                    destination=destination,
                    shipper=shipper,
                    declared_value=declared_value,
                    currency=currency,
                )
                all_rates.extend(rates)
                logger.info(
                    f"✓ {adapter.carrier_name} : {len(rates)} tarif(s)"
                )
            except CarrierAPIError as exc:
                msg = f"{adapter.carrier_name} : {exc}"
                carrier_errors.append(msg)
                logger.error(f"✗ {msg}")
            except Exception as exc:
                msg = f"{adapter.carrier_name} : erreur inattendue — {exc}"
                carrier_errors.append(msg)
                logger.error(f"✗ {msg}", exc_info=True)

        if not all_rates and carrier_errors:
            return ShippingResponse(
                success=False,
                error="Tous les carriers ont échoué",
                carrier_errors=carrier_errors,
                total_weight_kg=total_weight,
                package_count=len(package_inputs),
            )

        # Trier par prix croissant
        all_rates.sort(key=lambda r: r.price)

        rates_dicts = [r.model_dump(exclude={"raw_response"}) for r in all_rates]
        best_rate = rates_dicts[0] if rates_dicts else None

        return ShippingResponse(
            success=True,
            rates=rates_dicts,
            best_rate=best_rate,
            total_weight_kg=total_weight,
            package_count=len(package_inputs),
            carrier_errors=carrier_errors,
        )

    # ─────────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────────

    def _normalize_packages(
        self, raw_packages: List[Dict[str, Any]]
    ) -> List[PackageInput]:
        """
        Convertit les dicts packages (format DHL packing_service) en PackageInput.

        Format attendu :
          {"weight": 10.0, "dimensions": {"length": 60, "width": 40, "height": 40}}
        """
        result: List[PackageInput] = []
        for i, pkg in enumerate(raw_packages):
            try:
                weight = float(pkg.get("weight", 0))
                dims = pkg.get("dimensions", {})
                length = float(dims.get("length", 1))
                width = float(dims.get("width", 1))
                height = float(dims.get("height", 1))

                if weight <= 0:
                    logger.warning(f"⚠️ Colis #{i+1} : poids invalide ({weight}) — ignoré")
                    continue

                result.append(
                    PackageInput(
                        weight_kg=weight,
                        length_cm=length,
                        width_cm=width,
                        height_cm=height,
                    )
                )
            except (TypeError, ValueError) as exc:
                logger.warning(f"⚠️ Colis #{i+1} malformé : {exc}")
                continue

        return result

    def list_carriers(self) -> List[Dict[str, str]]:
        """Retourne la liste des carriers disponibles."""
        return [
            {"key": key, "name": adapter.carrier_name, "available": str(adapter.is_available())}
            for key, adapter in self._carriers.items()
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_transport_service: Optional[TransportService] = None


def get_transport_service() -> TransportService:
    """Factory singleton du service de transport."""
    global _transport_service
    if _transport_service is None:
        _transport_service = TransportService()
        logger.info("✓ TransportService initialisé")
    return _transport_service
