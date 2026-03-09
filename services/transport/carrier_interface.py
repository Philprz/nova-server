"""
Interface abstraite pour les adapters transporteurs NOVA
Permet d'ajouter facilement un nouveau transporteur (UPS, Chronopost, Geodis…)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PackageInput(BaseModel):
    """Colis à expédier — format normalisé inter-carrier"""
    weight_kg: float = Field(gt=0, description="Poids brut en kg")
    length_cm: float = Field(gt=0)
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)

    @property
    def volume_m3(self) -> float:
        return (self.length_cm * self.width_cm * self.height_cm) / 1_000_000

    @property
    def volumetric_weight_kg(self) -> float:
        """Poids volumétrique DHL : L×W×H (cm) / 5000"""
        return (self.length_cm * self.width_cm * self.height_cm) / 5000

    @property
    def chargeable_weight_kg(self) -> float:
        """Poids taxable = max(poids réel, poids volumétrique)"""
        return max(self.weight_kg, self.volumetric_weight_kg)


class Destination(BaseModel):
    """Adresse de livraison"""
    postal_code: str = Field(description="Code postal ou ville selon pays")
    city_name: str
    country_code: str = Field(min_length=2, max_length=2, description="Code ISO-2")
    address_line: Optional[str] = None
    state_code: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "postal_code": "75001",
                "city_name": "PARIS",
                "country_code": "FR"
            }
        }


class Shipper(BaseModel):
    """Expéditeur"""
    postal_code: str = Field(default="13002")
    city_name: str = Field(default="MARSEILLE")
    country_code: str = Field(default="FR")
    account_number: Optional[str] = None


class ShippingRate(BaseModel):
    """Tarif retourné par un carrier"""
    carrier: str = Field(description="Nom du transporteur (ex: DHL)")
    service_code: str = Field(description="Code service (ex: P, U, K…)")
    service_name: str = Field(description="Libellé service (ex: DHL EXPRESS WORLDWIDE)")
    price: float = Field(description="Coût en devise")
    currency: str = Field(default="EUR")
    delivery_days: int = Field(default=1, description="Délai livraison estimé")
    delivery_date: Optional[str] = Field(None, description="Date livraison estimée ISO")
    total_weight_kg: float = Field(default=0.0)
    package_count: int = Field(default=1)
    raw_response: Optional[Dict[str, Any]] = Field(
        None, description="Réponse brute API pour traçabilité"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "carrier": "DHL",
                "service_code": "P",
                "service_name": "DHL EXPRESS WORLDWIDE",
                "price": 45.20,
                "currency": "EUR",
                "delivery_days": 2,
                "total_weight_kg": 10.5,
                "package_count": 2
            }
        }


class CarrierAdapter(ABC):
    """
    Interface abstraite pour tous les adapters transporteurs.

    Pour ajouter un nouveau transporteur :
    1. Créer services/transport/carriers/<nom>_adapter.py
    2. Étendre CarrierAdapter
    3. Implémenter get_rate()
    4. Enregistrer dans TransportService
    """

    @property
    @abstractmethod
    def carrier_name(self) -> str:
        """Nom lisible du transporteur"""
        ...

    @abstractmethod
    async def get_rate(
        self,
        packages: List[PackageInput],
        destination: Destination,
        shipper: Optional[Shipper] = None,
        declared_value: float = 100.0,
        currency: str = "EUR",
    ) -> List[ShippingRate]:
        """
        Appelle l'API du transporteur et retourne les tarifs disponibles.

        Args:
            packages: Liste de colis (poids + dimensions)
            destination: Adresse de destination
            shipper: Expéditeur (défaut : Marseille RONDOT-SAS)
            declared_value: Valeur déclarée en douane
            currency: Devise de la valeur déclarée

        Returns:
            Liste de ShippingRate (un par service disponible)

        Raises:
            CarrierAPIError: En cas d'erreur API non récupérable
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Vérifie si l'adapter est configuré et disponible"""
        ...


class CarrierAPIError(Exception):
    """Erreur lors de l'appel à l'API d'un transporteur"""

    def __init__(self, carrier: str, message: str, status_code: Optional[int] = None):
        self.carrier = carrier
        self.status_code = status_code
        super().__init__(f"[{carrier}] {message}")
