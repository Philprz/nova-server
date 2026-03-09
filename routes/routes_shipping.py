"""
Routes API — Transport / Expédition
Préfixe : /api/shipping
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.transport.transport_service import (
    ShippingRequest,
    ShippingResponse,
    get_transport_service,
)
from services.transport.carrier_interface import Destination, Shipper

router = APIRouter(prefix="/api/shipping", tags=["Transport"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/quote", response_model=ShippingResponse, summary="Tarif transport DHL Express")
async def get_shipping_quote(request: ShippingRequest) -> ShippingResponse:
    """
    Calcule le tarif d'expédition DHL Express pour une liste de colis.

    **Authentification DHL** : Basic Auth (rondotFR / credentials .env)

    **Format packages** :
    ```json
    [
      {
        "weight": 10.0,
        "dimensions": {"length": 60, "width": 40, "height": 40}
      }
    ]
    ```

    **Retourne** :
    - `rates` : tous les services DHL disponibles (triés par prix)
    - `best_rate` : tarif le moins cher
    - `total_weight_kg` : poids total des colis
    """
    logger.info(
        f"→ POST /api/shipping/quote — "
        f"{len(request.packages)} colis → "
        f"{request.destination.city_name} ({request.destination.country_code})"
    )

    service = get_transport_service()
    result = await service.calculate_shipping(
        packages=request.packages,
        destination=request.destination,
        shipper=request.shipper,
        declared_value=request.declared_value,
        currency=request.currency,
        carrier=request.carrier,
    )

    if not result.success and not result.rates:
        raise HTTPException(
            status_code=502,
            detail={
                "message": result.error or "Erreur carrier",
                "carrier_errors": result.carrier_errors,
            }
        )

    return result


@router.get("/carriers", summary="Liste des transporteurs disponibles")
async def list_carriers() -> Dict[str, Any]:
    """
    Retourne la liste des transporteurs configurés et disponibles.
    """
    service = get_transport_service()
    carriers = service.list_carriers()
    return {
        "success": True,
        "carriers": carriers,
        "count": len(carriers)
    }


@router.post(
    "/dhl/test",
    summary="Test de connectivité DHL Express (endpoint test)",
)
async def test_dhl_connectivity() -> Dict[str, Any]:
    """
    Teste la connectivité avec l'API DHL Express en utilisant un payload standard.

    **Expédition de test** :
    - Expéditeur : Marseille, FR
    - Destination : Paris, FR
    - Colis : 1 kg, 30×20×20 cm

    Retourne les tarifs disponibles ou un message d'erreur détaillé.
    """
    from services.transport.carriers.dhl_adapter import get_dhl_adapter
    from services.transport.carrier_interface import PackageInput

    logger.info("→ POST /api/shipping/dhl/test — test de connectivité")

    adapter = get_dhl_adapter()

    test_packages = [
        PackageInput(weight_kg=1.0, length_cm=30.0, width_cm=20.0, height_cm=20.0)
    ]
    test_destination = Destination(
        postal_code="75001",
        city_name="PARIS",
        country_code="FR",
    )

    try:
        rates = await adapter.get_rate(
            packages=test_packages,
            destination=test_destination,
            declared_value=10.0,
        )
        return {
            "success": True,
            "message": f"DHL API opérationnelle — {len(rates)} tarif(s) disponible(s)",
            "environment": "TEST" if "test" in adapter._base_url else "PROD",
            "rates_count": len(rates),
            "rates": [
                {
                    "service": r.service_name,
                    "price": r.price,
                    "currency": r.currency,
                    "delivery_days": r.delivery_days,
                }
                for r in rates[:3]  # Afficher max 3 tarifs
            ],
        }
    except Exception as exc:
        logger.error(f"✗ Test DHL échoué : {exc}")
        return {
            "success": False,
            "message": f"Erreur API DHL : {exc}",
            "environment": "TEST" if "test" in adapter._base_url else "PROD",
        }


@router.post(
    "/dhl/switch-env",
    summary="Bascule DHL Test ↔ Production",
)
async def switch_dhl_environment(
    use_production: bool = Query(default=False, description="True = Production, False = Test")
) -> Dict[str, Any]:
    """
    Bascule l'adapter DHL entre l'environnement de test et de production.

    **ATTENTION** : En production, les appels génèrent de vraies expéditions.
    """
    from services.transport.carriers.dhl_adapter import get_dhl_adapter

    adapter = get_dhl_adapter()

    if use_production:
        adapter.use_production()
        env = "PRODUCTION"
    else:
        adapter.use_test()
        env = "TEST"

    logger.info(f"✓ DHL basculé sur {env}")
    return {
        "success": True,
        "environment": env,
        "message": f"DHL adapter basculé sur {env}"
    }
