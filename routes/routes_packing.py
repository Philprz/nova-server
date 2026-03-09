"""
Routes API — Colisage (Packing)
Préfixe : /api/packing
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.packing.packing_service import (
    PackingItemInput,
    PackingResponse,
    get_packing_service,
)

router = APIRouter(prefix="/api/packing", tags=["Colisage"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Modèles de requête
# ─────────────────────────────────────────────────────────────────────────────

class PackingCalculateRequest(BaseModel):
    """Corps de requête pour /calculate"""
    items: List[PackingItemInput] = Field(
        min_length=1,
        description="Articles à emballer"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "item_code": "REF-001",
                        "quantity": 5,
                        "weight_kg": 2.0,
                        "length_cm": 30.0,
                        "width_cm": 20.0,
                        "height_cm": 15.0
                    },
                    {
                        "item_code": "REF-002",
                        "quantity": 2,
                        "weight_kg": 8.0,
                        "length_cm": 50.0,
                        "width_cm": 35.0,
                        "height_cm": 25.0
                    }
                ]
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/calculate", response_model=PackingResponse, summary="Calcul de colisage")
async def calculate_packing(request: PackingCalculateRequest) -> PackingResponse:
    """
    Calcule le colisage optimal pour une liste d'articles.

    **Algorithme** : First Fit Decreasing (FFD)

    **Catalogue colis** :
    - S : 30×20×20 cm, max 10 kg
    - M : 60×40×40 cm, max 25 kg
    - L : 80×60×60 cm, max 40 kg
    - Palette : 120×80×150 cm, max 500 kg

    **Enrichissement automatique** :
    Si les dimensions/poids ne sont pas fournis, ils sont récupérés depuis la base
    de données des tarifs fournisseurs (supplier_tariffs.db).

    **Retourne** :
    - Liste des colis avec dimensions et poids
    - Résumé lisible de la suggestion
    - Payload `dhl_packages` prêt pour l'API DHL
    """
    logger.info(
        f"→ POST /api/packing/calculate — {len(request.items)} article(s)"
    )

    service = get_packing_service()
    result = await service.suggest_packages(request.items)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    logger.info(
        f"✓ Colisage calculé : {result.box_count} colis, "
        f"{result.total_weight_kg} kg"
    )
    return result


@router.get("/box-types", summary="Catalogue des types de colis")
async def list_box_types() -> Dict[str, Any]:
    """
    Retourne le catalogue des types de colis disponibles avec leurs caractéristiques.

    Utile pour afficher les options à l'utilisateur avant validation.
    """
    service = get_packing_service()
    return {
        "success": True,
        "box_types": service.list_box_types(),
        "count": 4
    }


@router.post("/calculate-and-ship", summary="Colisage + tarif transport en une requête")
async def calculate_packing_and_shipping(
    request: PackingCalculateRequest,
    destination_postal_code: str,
    destination_city: str,
    destination_country: str = "FR",
    declared_value: float = 100.0,
) -> Dict[str, Any]:
    """
    Enchaîne calcul de colisage puis récupération du tarif DHL Express.

    **Pipeline** :
    1. Algorithme FFD → suggestion de colis
    2. API DHL → tarif transport

    **Paramètres query** :
    - `destination_postal_code` : code postal destination
    - `destination_city` : ville destination
    - `destination_country` : code ISO-2 pays (défaut : FR)
    - `declared_value` : valeur déclarée en douane (EUR)
    """
    from services.transport.transport_service import get_transport_service
    from services.transport.carrier_interface import Destination

    logger.info(
        f"→ POST /api/packing/calculate-and-ship — "
        f"{len(request.items)} article(s) → {destination_city} ({destination_country})"
    )

    # 1. Colisage
    packing_service = get_packing_service()
    packing_result = await packing_service.suggest_packages(request.items)

    if not packing_result.success:
        raise HTTPException(status_code=400, detail=f"Colisage impossible : {packing_result.error}")

    # 2. Transport DHL
    transport_service = get_transport_service()
    destination = Destination(
        postal_code=destination_postal_code,
        city_name=destination_city.upper(),
        country_code=destination_country.upper(),
    )

    shipping_result = await transport_service.calculate_shipping(
        packages=packing_result.dhl_packages,
        destination=destination,
        declared_value=declared_value,
    )

    return {
        "success": packing_result.success,
        "packing": {
            "packages": packing_result.packages,
            "total_weight_kg": packing_result.total_weight_kg,
            "total_volume_m3": packing_result.total_volume_m3,
            "box_count": packing_result.box_count,
            "summary": packing_result.summary,
            "warnings": packing_result.warnings,
        },
        "shipping": {
            "success": shipping_result.success,
            "rates": shipping_result.rates,
            "best_rate": shipping_result.best_rate,
            "errors": shipping_result.carrier_errors,
        },
    }
