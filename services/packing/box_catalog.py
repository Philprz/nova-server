"""
Catalogue des types de colis standard NOVA
Définit les dimensions et limites de poids pour chaque format de boîte
"""

from __future__ import annotations
from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class BoxType(str, Enum):
    """Types de colis disponibles, classés du plus petit au plus grand"""
    S = "S"
    M = "M"
    L = "L"
    PALLET = "PALLET"


class BoxSpec(BaseModel):
    """Spécification d'un type de colis"""
    type: BoxType
    label: str = Field(description="Libellé lisible")
    length_cm: float = Field(gt=0, description="Longueur intérieure en cm")
    width_cm: float = Field(gt=0, description="Largeur intérieure en cm")
    height_cm: float = Field(gt=0, description="Hauteur intérieure en cm")
    max_weight_kg: float = Field(gt=0, description="Poids maximum supporté en kg")

    @property
    def volume_cm3(self) -> float:
        """Volume intérieur en cm³"""
        return self.length_cm * self.width_cm * self.height_cm

    @property
    def volume_m3(self) -> float:
        """Volume intérieur en m³"""
        return self.volume_cm3 / 1_000_000

    def can_fit_item(self, item_length: float, item_width: float, item_height: float) -> bool:
        """
        Vérifie si un article peut physiquement tenir dans ce colis.
        Teste toutes les orientations (6 permutations de dimensions).
        Dimensions attendues en cm.
        """
        dims_item = sorted([item_length, item_width, item_height])
        dims_box = sorted([self.length_cm, self.width_cm, self.height_cm])
        return all(i <= b for i, b in zip(dims_item, dims_box))

    def __repr__(self) -> str:
        return (
            f"BoxSpec({self.type.value}: "
            f"{self.length_cm}×{self.width_cm}×{self.height_cm} cm, "
            f"max {self.max_weight_kg} kg)"
        )


# Catalogue officiel — triés du plus petit au plus grand
BOX_CATALOG: List[BoxSpec] = [
    BoxSpec(
        type=BoxType.S,
        label="Colis S",
        length_cm=30.0,
        width_cm=20.0,
        height_cm=20.0,
        max_weight_kg=10.0,
    ),
    BoxSpec(
        type=BoxType.M,
        label="Colis M",
        length_cm=60.0,
        width_cm=40.0,
        height_cm=40.0,
        max_weight_kg=25.0,
    ),
    BoxSpec(
        type=BoxType.L,
        label="Colis L",
        length_cm=80.0,
        width_cm=60.0,
        height_cm=60.0,
        max_weight_kg=40.0,
    ),
    BoxSpec(
        type=BoxType.PALLET,
        label="Palette",
        length_cm=120.0,
        width_cm=80.0,
        height_cm=150.0,
        max_weight_kg=500.0,
    ),
]

# Accès rapide par type
BOX_BY_TYPE: dict[BoxType, BoxSpec] = {spec.type: spec for spec in BOX_CATALOG}


def get_box_spec(box_type: BoxType) -> BoxSpec:
    """Retourne la spec d'un colis par son type."""
    return BOX_BY_TYPE[box_type]


def get_smallest_fitting_box(
    item_length_cm: float,
    item_width_cm: float,
    item_height_cm: float,
    item_weight_kg: float,
) -> BoxSpec | None:
    """
    Retourne le plus petit colis pouvant contenir un article (dimensions + poids).
    Retourne None si aucun colis ne convient.
    """
    for box in BOX_CATALOG:
        if (
            box.max_weight_kg >= item_weight_kg
            and box.can_fit_item(item_length_cm, item_width_cm, item_height_cm)
        ):
            return box
    return None
