"""
Service de calcul de transport

Phase 1 : Version basique utilisant les données supplier_products
Phase 2 : Intégration API transporteurs (DHL, UPS, Chronopost, Geodis)
"""

import logging
from typing import Optional, Dict
from pydantic import BaseModel
from services.supplier_tariffs_db import search_products

logger = logging.getLogger(__name__)


class TransportCost(BaseModel):
    """Résultat du calcul transport"""
    cost: float
    delivery_days: int
    carrier_name: str = "Standard"
    weight_kg: float = 0.0


class TransportCalculator:
    """
    Calculateur de coût de transport

    Phase 1 : Calcul basique depuis base supplier_products
    - Poids total = poids unitaire × quantité
    - Coût transport = transport_cost depuis base

    Phase 2 : API transporteurs en temps réel (DHL, UPS, etc.)
    """

    def __init__(self):
        self.default_carrier = "Standard"

    async def calculate_transport_cost(
        self,
        item_code: str,
        quantity: float = 1.0,
        destination_zip: Optional[str] = None,
        carrier: str = "default"
    ) -> Optional[TransportCost]:
        """
        Calcule le coût de transport pour un article

        Args:
            item_code: Code article
            quantity: Quantité commandée
            destination_zip: Code postal destination (non utilisé en Phase 1)
            carrier: Transporteur souhaité (non utilisé en Phase 1)

        Returns:
            TransportCost ou None si données manquantes
        """
        try:
            # Récupérer données produit depuis supplier_tariffs_db
            products = search_products(item_code, limit=1)

            if not products:
                logger.warning(f"Article {item_code} non trouvé dans tarifs fournisseurs")
                return None

            product = products[0]

            # Récupérer métadonnées transport
            unit_transport_cost = product.get('transport_cost')
            delivery_days = product.get('delivery_days')
            weight = product.get('weight')

            if unit_transport_cost is None:
                logger.warning(f"Coût transport non défini pour {item_code}")
                return None

            # Calcul Phase 1 : Coût unitaire × quantité
            total_transport_cost = float(unit_transport_cost) * quantity

            # Calcul poids total
            total_weight = float(weight) * quantity if weight else 0.0

            result = TransportCost(
                cost=round(total_transport_cost, 2),
                delivery_days=delivery_days if delivery_days else 7,  # Défaut 7 jours
                carrier_name=self.default_carrier,
                weight_kg=round(total_weight, 2)
            )

            logger.info(
                f"✓ Transport calculé pour {item_code} : "
                f"{result.cost:.2f} EUR (poids {result.weight_kg}kg, "
                f"délai {result.delivery_days}j)"
            )

            return result

        except Exception as e:
            logger.error(f"✗ Erreur calcul transport : {e}")
            return None

    async def calculate_total_transport(
        self,
        items: list[Dict],
        destination_zip: Optional[str] = None
    ) -> Dict:
        """
        Calcule le transport total pour plusieurs articles

        Args:
            items: Liste de {item_code, quantity}
            destination_zip: Code postal destination

        Returns:
            {total_cost, total_weight, max_delivery_days, carrier}
        """
        total_cost = 0.0
        total_weight = 0.0
        max_delivery_days = 0

        for item in items:
            item_code = item.get('item_code')
            quantity = item.get('quantity', 1.0)

            transport = await self.calculate_transport_cost(
                item_code,
                quantity,
                destination_zip
            )

            if transport:
                total_cost += transport.cost
                total_weight += transport.weight_kg
                max_delivery_days = max(max_delivery_days, transport.delivery_days)

        result = {
            "total_cost": round(total_cost, 2),
            "total_weight_kg": round(total_weight, 2),
            "max_delivery_days": max_delivery_days,
            "carrier": self.default_carrier
        }

        logger.info(
            f"✓ Transport total : {result['total_cost']:.2f} EUR, "
            f"{result['total_weight_kg']}kg, délai {result['max_delivery_days']}j"
        )

        return result


# Instance singleton
_transport_calculator: Optional[TransportCalculator] = None


def get_transport_calculator() -> TransportCalculator:
    """Factory pour obtenir l'instance du calculateur"""
    global _transport_calculator
    if _transport_calculator is None:
        _transport_calculator = TransportCalculator()
        logger.info("TransportCalculator initialisé (Phase 1 - Basique)")
    return _transport_calculator
