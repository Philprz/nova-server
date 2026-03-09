"""
Module de colisage (packing) NOVA
Algorithme First Fit Decreasing pour calcul automatique des colis
"""

from .packing_service import PackingService, get_packing_service
from .packing_algorithm import FirstFitDecreasingPacker
from .box_catalog import BOX_CATALOG, BoxSpec, BoxType

__all__ = [
    "PackingService",
    "get_packing_service",
    "FirstFitDecreasingPacker",
    "BOX_CATALOG",
    "BoxSpec",
    "BoxType",
]
