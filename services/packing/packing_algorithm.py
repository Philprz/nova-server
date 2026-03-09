"""
Algorithme de colisage First Fit Decreasing (FFD)
Optimise le remplissage des colis par volume décroissant
"""

from __future__ import annotations
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from .box_catalog import BOX_CATALOG, BoxSpec, BoxType, get_smallest_fitting_box

logger = logging.getLogger(__name__)

# Marge de sécurité volumétrique (15% de volume supplémentaire pour calage/protection)
VOLUME_SAFETY_MARGIN = 0.85  # Utiliser 85% du volume disponible


class PackingItem(BaseModel):
    """Article à emballer"""
    item_code: str = Field(default="UNKNOWN", description="Code article")
    weight_kg: float = Field(default=0.0, ge=0.0, description="Poids unitaire en kg")
    length_cm: float = Field(default=10.0, ge=0.0, description="Longueur en cm")
    width_cm: float = Field(default=10.0, ge=0.0, description="Largeur en cm")
    height_cm: float = Field(default=10.0, ge=0.0, description="Hauteur en cm")
    quantity: int = Field(default=1, ge=1, description="Quantité")

    @property
    def volume_cm3(self) -> float:
        return self.length_cm * self.width_cm * self.height_cm

    @property
    def total_weight_kg(self) -> float:
        return self.weight_kg * self.quantity

    @property
    def total_volume_cm3(self) -> float:
        return self.volume_cm3 * self.quantity


class FilledBox(BaseModel):
    """Colis en cours de remplissage"""
    box_spec: BoxSpec
    items_packed: List[str] = Field(default_factory=list, description="Codes articles dans ce colis")
    current_weight_kg: float = Field(default=0.0)
    current_volume_cm3: float = Field(default=0.0)

    @property
    def remaining_weight_kg(self) -> float:
        return self.box_spec.max_weight_kg - self.current_weight_kg

    @property
    def available_volume_cm3(self) -> float:
        """Volume disponible avec marge de sécurité"""
        return (self.box_spec.volume_cm3 * VOLUME_SAFETY_MARGIN) - self.current_volume_cm3

    def can_add_item(self, item_weight_kg: float, item_volume_cm3: float) -> bool:
        """Vérifie si un article peut être ajouté (poids + volume)"""
        return (
            item_weight_kg <= self.remaining_weight_kg
            and item_volume_cm3 <= self.available_volume_cm3
        )

    def add_item(self, item_code: str, weight_kg: float, volume_cm3: float) -> None:
        """Ajoute un article au colis"""
        self.items_packed.append(item_code)
        self.current_weight_kg += weight_kg
        self.current_volume_cm3 += volume_cm3


class PackageResult(BaseModel):
    """Résultat d'un colis finalisé — format compatible DHL API"""
    box_type: BoxType
    label: str
    length_cm: float
    width_cm: float
    height_cm: float
    weight_kg: float
    volume_cm3: float
    items_count: int = Field(default=1)
    item_codes: List[str] = Field(default_factory=list)

    @property
    def volume_m3(self) -> float:
        return self.volume_cm3 / 1_000_000


class PackingResult(BaseModel):
    """Résultat complet du calcul de colisage"""
    packages: List[PackageResult] = Field(default_factory=list)
    total_weight_kg: float = Field(default=0.0)
    total_volume_m3: float = Field(default=0.0)
    box_count: int = Field(default=0)
    summary: str = Field(default="", description="Résumé lisible pour l'utilisateur")
    warnings: List[str] = Field(default_factory=list)

    def build_summary(self) -> str:
        """Génère un résumé lisible de la suggestion de colisage"""
        if not self.packages:
            return "Aucun colis calculé"
        counts: dict[str, int] = {}
        for pkg in self.packages:
            counts[pkg.label] = counts.get(pkg.label, 0) + 1
        lines = ["Suggestion colisage :"]
        for label, count in sorted(counts.items()):
            lines.append(f"  • {count} × {label}")
        lines.append(f"  Poids total : {self.total_weight_kg:.2f} kg")
        lines.append(f"  Volume total : {self.total_volume_m3:.4f} m³")
        return "\n".join(lines)


class FirstFitDecreasingPacker:
    """
    Algorithme First Fit Decreasing (FFD) pour optimisation du colisage.

    Principe :
    1. Développer les items (quantité → unités individuelles)
    2. Trier par volume décroissant
    3. Pour chaque unité : trouver le premier colis ouvert pouvant l'accueillir
    4. Si aucun colis ne convient : ouvrir un nouveau colis (le plus petit adapté)
    """

    def pack(self, items: List[PackingItem]) -> PackingResult:
        """
        Lance l'algorithme FFD sur la liste d'articles.

        Args:
            items: Articles à emballer (avec quantités)

        Returns:
            PackingResult avec la liste des colis et statistiques
        """
        if not items:
            return PackingResult()

        warnings: List[str] = []

        # 1. Développer les quantités en unités individuelles
        units = self._expand_to_units(items)

        # 2. Trier par volume décroissant (FFD)
        units.sort(key=lambda u: u.volume_cm3, reverse=True)

        # 3. Placement FFD
        open_boxes: List[FilledBox] = []

        for unit in units:
            placed = False

            # Chercher le premier colis ouvert pouvant accueillir l'unité
            for box in open_boxes:
                if box.can_add_item(unit.weight_kg, unit.volume_cm3):
                    box.add_item(unit.item_code, unit.weight_kg, unit.volume_cm3)
                    placed = True
                    break

            if not placed:
                # Ouvrir un nouveau colis — choisir le plus petit adapté
                new_box_spec = self._select_box_for_item(unit, warnings)
                if new_box_spec is None:
                    # L'article ne rentre dans aucun colis connu
                    warnings.append(
                        f"Article {unit.item_code} ({unit.weight_kg}kg, "
                        f"{unit.volume_cm3:.0f}cm³) dépasse tous les formats disponibles — "
                        "placé en palette par défaut"
                    )
                    new_box_spec = BOX_CATALOG[-1]  # Palette (le plus grand)

                new_box = FilledBox(box_spec=new_box_spec)
                new_box.add_item(unit.item_code, unit.weight_kg, unit.volume_cm3)
                open_boxes.append(new_box)

        # 4. Convertir en PackageResult
        packages = self._finalize_boxes(open_boxes)

        total_weight = round(sum(p.weight_kg for p in packages), 3)
        total_volume = round(sum(p.volume_m3 for p in packages), 6)

        result = PackingResult(
            packages=packages,
            total_weight_kg=total_weight,
            total_volume_m3=total_volume,
            box_count=len(packages),
            warnings=warnings,
        )
        result.summary = result.build_summary()

        logger.info(
            f"✓ Colisage FFD : {len(packages)} colis | "
            f"{total_weight} kg | {total_volume:.4f} m³"
        )

        return result

    # ─────────────────────────────────────────────────────────────
    # Méthodes privées
    # ─────────────────────────────────────────────────────────────

    def _expand_to_units(self, items: List[PackingItem]) -> List[PackingItem]:
        """Développe les articles avec quantité > 1 en unités individuelles"""
        units: List[PackingItem] = []
        for item in items:
            for _ in range(item.quantity):
                units.append(
                    PackingItem(
                        item_code=item.item_code,
                        weight_kg=item.weight_kg,
                        length_cm=item.length_cm,
                        width_cm=item.width_cm,
                        height_cm=item.height_cm,
                        quantity=1,
                    )
                )
        return units

    def _select_box_for_item(
        self, unit: PackingItem, warnings: List[str]
    ) -> Optional[BoxSpec]:
        """
        Sélectionne le plus petit colis pouvant contenir l'article.
        Critères : poids ET volume.
        """
        for box in BOX_CATALOG:
            # Vérifier poids
            if unit.weight_kg > box.max_weight_kg:
                continue
            # Vérifier volume avec marge de sécurité
            usable_volume = box.volume_cm3 * VOLUME_SAFETY_MARGIN
            if unit.volume_cm3 <= usable_volume:
                return box
            # Vérifier dimensions physiques
            if box.can_fit_item(unit.length_cm, unit.width_cm, unit.height_cm):
                return box
        return None

    def _finalize_boxes(self, open_boxes: List[FilledBox]) -> List[PackageResult]:
        """Convertit les boîtes remplies en PackageResult"""
        packages: List[PackageResult] = []
        for box in open_boxes:
            packages.append(
                PackageResult(
                    box_type=box.box_spec.type,
                    label=box.box_spec.label,
                    length_cm=box.box_spec.length_cm,
                    width_cm=box.box_spec.width_cm,
                    height_cm=box.box_spec.height_cm,
                    weight_kg=round(box.current_weight_kg, 3),
                    volume_cm3=round(box.current_volume_cm3, 1),
                    items_count=len(box.items_packed),
                    item_codes=list(dict.fromkeys(box.items_packed)),  # dédupliqué
                )
            )
        return packages
