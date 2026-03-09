"""
Service de colisage NOVA
Orchestre le calcul de colisage et enrichit les données depuis supplier_tariffs_db
"""

from __future__ import annotations
import json
import logging
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from .packing_algorithm import FirstFitDecreasingPacker, PackingItem, PackingResult
from .box_catalog import BOX_CATALOG, BoxSpec

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Modèles d'entrée / sortie du service
# ─────────────────────────────────────────────────────────────────────────────

class PackingItemInput(BaseModel):
    """Article fourni par l'appelant pour le calcul de colisage"""
    item_code: str = Field(description="Code article SAP ou fournisseur")
    quantity: int = Field(default=1, ge=1)
    # Dimensions optionnelles : si non fournies, récupérées depuis supplier_tariffs_db
    weight_kg: Optional[float] = Field(None, ge=0.0, description="Poids unitaire kg")
    length_cm: Optional[float] = Field(None, ge=0.0)
    width_cm: Optional[float] = Field(None, ge=0.0)
    height_cm: Optional[float] = Field(None, ge=0.0)


class PackingResponse(BaseModel):
    """Réponse complète du service de colisage"""
    success: bool
    packages: List[Dict[str, Any]] = Field(default_factory=list)
    total_weight_kg: float = Field(default=0.0)
    total_volume_m3: float = Field(default=0.0)
    box_count: int = Field(default=0)
    summary: str = Field(default="")
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None

    # Données brutes pour intégration DHL
    dhl_packages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Packages au format attendu par l'API DHL"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Service principal
# ─────────────────────────────────────────────────────────────────────────────

class PackingService:
    """
    Service de colisage NOVA.

    Responsabilités :
    - Résoudre les dimensions/poids depuis supplier_tariffs_db si absent
    - Déléguer le calcul FFD à FirstFitDecreasingPacker
    - Formater la réponse pour l'API et pour l'intégration DHL
    """

    # Valeurs par défaut si dimensions inconnues
    DEFAULT_WEIGHT_KG = 1.0
    DEFAULT_LENGTH_CM = 20.0
    DEFAULT_WIDTH_CM = 15.0
    DEFAULT_HEIGHT_CM = 10.0

    def __init__(self) -> None:
        self._packer = FirstFitDecreasingPacker()

    async def suggest_packages(
        self, items: List[PackingItemInput]
    ) -> PackingResponse:
        """
        Calcule le colisage optimal pour une liste d'articles.

        Pipeline :
        1. Résoudre poids/dimensions depuis la DB si non fournis
        2. Appliquer l'algorithme FFD
        3. Formater la réponse (résumé, payload DHL)

        Args:
            items: Articles avec quantités (+ éventuellement dimensions)

        Returns:
            PackingResponse avec colis, poids total et payload DHL
        """
        try:
            # 1. Construire les PackingItem avec dimensions résolues
            packing_items = await self._resolve_items(items)
            if not packing_items:
                return PackingResponse(
                    success=False,
                    error="Aucun article valide à emballer"
                )

            # 2. Algorithme FFD
            result: PackingResult = self._packer.pack(packing_items)

            # 3. Construire réponse
            packages_dicts = [pkg.model_dump() for pkg in result.packages]

            dhl_packages = self._build_dhl_packages(result)

            return PackingResponse(
                success=True,
                packages=packages_dicts,
                total_weight_kg=result.total_weight_kg,
                total_volume_m3=result.total_volume_m3,
                box_count=result.box_count,
                summary=result.summary,
                warnings=result.warnings,
                dhl_packages=dhl_packages,
            )

        except Exception as exc:
            logger.error(f"✗ Erreur calcul colisage : {exc}", exc_info=True)
            return PackingResponse(success=False, error=str(exc))

    # ─────────────────────────────────────────────────────────────
    # Résolution des dimensions
    # ─────────────────────────────────────────────────────────────

    async def _resolve_items(
        self, inputs: List[PackingItemInput]
    ) -> List[PackingItem]:
        """
        Enrichit chaque article avec poids/dimensions depuis supplier_tariffs_db
        si les données ne sont pas fournies dans la requête.
        """
        resolved: List[PackingItem] = []

        for inp in inputs:
            weight = inp.weight_kg
            length = inp.length_cm
            width = inp.width_cm
            height = inp.height_cm

            # Si dimensions manquantes, chercher en DB
            if any(v is None for v in (weight, length, width, height)):
                db_data = await self._fetch_dimensions_from_db(inp.item_code)
                if db_data:
                    weight = weight if weight is not None else db_data.get("weight")
                    length = length if length is not None else db_data.get("length_cm")
                    width = width if width is not None else db_data.get("width_cm")
                    height = height if height is not None else db_data.get("height_cm")

            # Fallback sur valeurs par défaut
            if weight is None:
                logger.warning(
                    f"⚠️ Poids inconnu pour {inp.item_code} — "
                    f"défaut {self.DEFAULT_WEIGHT_KG} kg utilisé"
                )
                weight = self.DEFAULT_WEIGHT_KG

            if any(v is None for v in (length, width, height)):
                logger.warning(
                    f"⚠️ Dimensions inconnues pour {inp.item_code} — "
                    f"défaut {self.DEFAULT_LENGTH_CM}×{self.DEFAULT_WIDTH_CM}"
                    f"×{self.DEFAULT_HEIGHT_CM} cm utilisé"
                )
                length = length or self.DEFAULT_LENGTH_CM
                width = width or self.DEFAULT_WIDTH_CM
                height = height or self.DEFAULT_HEIGHT_CM

            resolved.append(
                PackingItem(
                    item_code=inp.item_code,
                    weight_kg=float(weight),
                    length_cm=float(length),
                    width_cm=float(width),
                    height_cm=float(height),
                    quantity=inp.quantity,
                )
            )

        return resolved

    async def _fetch_dimensions_from_db(
        self, item_code: str
    ) -> Optional[Dict[str, float]]:
        """Cherche poids + dimensions dans supplier_tariffs_db."""
        try:
            from services.supplier_tariffs_db import search_products  # éviter import circulaire

            products = search_products(item_code, limit=1)
            if not products:
                return None

            product = products[0]
            result: Dict[str, float] = {}

            # Poids
            if product.get("weight"):
                result["weight"] = float(product["weight"])

            # Dimensions (stockées en JSON : {"length": x, "width": y, "height": z})
            dims_raw = product.get("dimensions")
            if dims_raw:
                try:
                    dims = json.loads(dims_raw) if isinstance(dims_raw, str) else dims_raw
                    # Tolérer "l", "w", "h" ou "length", "width", "height"
                    result["length_cm"] = float(
                        dims.get("length") or dims.get("l") or dims.get("longueur") or 0
                    )
                    result["width_cm"] = float(
                        dims.get("width") or dims.get("w") or dims.get("largeur") or 0
                    )
                    result["height_cm"] = float(
                        dims.get("height") or dims.get("h") or dims.get("hauteur") or 0
                    )
                    # Supprimer les zéros (données absentes)
                    result = {k: v for k, v in result.items() if v > 0}
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.warning(
                        f"⚠️ Impossible de parser dimensions pour {item_code}: {exc}"
                    )

            return result if result else None

        except Exception as exc:
            logger.error(f"✗ Erreur DB dimensions pour {item_code}: {exc}")
            return None

    # ─────────────────────────────────────────────────────────────
    # Formatage payload DHL
    # ─────────────────────────────────────────────────────────────

    def _build_dhl_packages(self, result: PackingResult) -> List[Dict[str, Any]]:
        """
        Convertit les PackageResult au format DHL Express API.

        Format DHL attendu :
        {
            "weight": 10.0,
            "dimensions": {"length": 60, "width": 40, "height": 40}
        }
        """
        dhl_packages = []
        for pkg in result.packages:
            dhl_packages.append(
                {
                    "weight": round(max(pkg.weight_kg, 0.1), 2),  # DHL min 0.1 kg
                    "dimensions": {
                        "length": int(pkg.length_cm),
                        "width": int(pkg.width_cm),
                        "height": int(pkg.height_cm),
                    },
                }
            )
        return dhl_packages

    # ─────────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────────

    def list_box_types(self) -> List[Dict[str, Any]]:
        """Retourne le catalogue des colis disponibles."""
        return [
            {
                "type": spec.type.value,
                "label": spec.label,
                "dimensions_cm": {
                    "length": spec.length_cm,
                    "width": spec.width_cm,
                    "height": spec.height_cm,
                },
                "max_weight_kg": spec.max_weight_kg,
                "volume_m3": round(spec.volume_m3, 4),
            }
            for spec in BOX_CATALOG
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_packing_service: Optional[PackingService] = None


def get_packing_service() -> PackingService:
    """Factory singleton du service de colisage."""
    global _packing_service
    if _packing_service is None:
        _packing_service = PackingService()
        logger.info("✓ PackingService initialisé (algorithme FFD)")
    return _packing_service
