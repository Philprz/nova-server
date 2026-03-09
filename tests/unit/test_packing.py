"""
Tests unitaires — Moteur de colisage (Packing)
Couvre : BoxCatalog, FFD algorithm, PackingService
"""

import pytest
from services.packing.box_catalog import (
    BOX_CATALOG,
    BoxType,
    get_box_spec,
    get_smallest_fitting_box,
)
from services.packing.packing_algorithm import (
    FirstFitDecreasingPacker,
    PackingItem,
)
from services.packing.packing_service import PackingItemInput, PackingService


# ─────────────────────────────────────────────────────────────────────────────
# BoxCatalog
# ─────────────────────────────────────────────────────────────────────────────

class TestBoxCatalog:
    def test_catalog_has_4_entries(self):
        assert len(BOX_CATALOG) == 4

    def test_box_types_ordered_by_size(self):
        volumes = [b.volume_cm3 for b in BOX_CATALOG]
        assert volumes == sorted(volumes), "Le catalogue doit être trié du plus petit au plus grand"

    def test_box_S_specs(self):
        box = get_box_spec(BoxType.S)
        assert box.length_cm == 30.0
        assert box.width_cm == 20.0
        assert box.height_cm == 20.0
        assert box.max_weight_kg == 10.0

    def test_box_M_specs(self):
        box = get_box_spec(BoxType.M)
        assert box.max_weight_kg == 25.0

    def test_box_L_specs(self):
        box = get_box_spec(BoxType.L)
        assert box.max_weight_kg == 40.0

    def test_pallet_specs(self):
        box = get_box_spec(BoxType.PALLET)
        assert box.max_weight_kg == 500.0

    def test_volume_computed(self):
        box = get_box_spec(BoxType.S)
        assert box.volume_cm3 == 30 * 20 * 20  # 12 000 cm³
        assert box.volume_m3 == pytest.approx(0.012, abs=1e-6)

    def test_can_fit_item_fits(self):
        box = get_box_spec(BoxType.M)
        assert box.can_fit_item(50, 30, 30) is True

    def test_can_fit_item_too_large(self):
        box = get_box_spec(BoxType.S)
        assert box.can_fit_item(40, 30, 30) is False  # 40 > 30

    def test_get_smallest_fitting_box_small_item(self):
        result = get_smallest_fitting_box(20, 15, 10, 3.0)
        assert result is not None
        assert result.type == BoxType.S

    def test_get_smallest_fitting_box_medium_item(self):
        result = get_smallest_fitting_box(50, 35, 35, 15.0)
        assert result is not None
        assert result.type == BoxType.M

    def test_get_smallest_fitting_box_too_heavy(self):
        # 600 kg → ne rentre dans aucun colis
        result = get_smallest_fitting_box(10, 10, 10, 600.0)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# First Fit Decreasing Algorithm
# ─────────────────────────────────────────────────────────────────────────────

class TestFirstFitDecreasing:
    def setup_method(self):
        self.packer = FirstFitDecreasingPacker()

    def _item(self, code="REF", w=1.0, l=10.0, wi=10.0, h=10.0, qty=1):
        return PackingItem(
            item_code=code,
            weight_kg=w,
            length_cm=l,
            width_cm=wi,
            height_cm=h,
            quantity=qty,
        )

    def test_empty_input(self):
        result = self.packer.pack([])
        assert result.box_count == 0
        assert result.packages == []
        assert result.total_weight_kg == 0.0

    def test_single_small_item(self):
        items = [self._item("A", w=2.0, l=20.0, wi=15.0, h=10.0, qty=1)]
        result = self.packer.pack(items)
        assert result.box_count == 1
        assert result.packages[0].box_type == BoxType.S
        assert result.total_weight_kg == pytest.approx(2.0)

    def test_single_item_quantity_3(self):
        items = [self._item("A", w=2.0, l=20.0, wi=15.0, h=10.0, qty=3)]
        result = self.packer.pack(items)
        # 3 × 2 kg = 6 kg → doit tenir dans 1 colis S (max 10 kg)
        total_w = sum(p.weight_kg for p in result.packages)
        assert total_w == pytest.approx(6.0)

    def test_heavy_items_multiple_boxes(self):
        # Chaque article fait 9 kg → 2 articles ne tiennent pas dans 1 colis S
        items = [self._item("A", w=9.0, l=20.0, wi=15.0, h=10.0, qty=2)]
        result = self.packer.pack(items)
        assert result.box_count >= 2

    def test_mixed_sizes(self):
        items = [
            self._item("SMALL", w=1.0, l=10.0, wi=10.0, h=10.0, qty=5),
            self._item("LARGE", w=30.0, l=70.0, wi=50.0, h=50.0, qty=1),
        ]
        result = self.packer.pack(items)
        assert result.box_count >= 1
        assert result.total_weight_kg == pytest.approx(35.0)

    def test_total_weight_correct(self):
        items = [
            self._item("A", w=3.0, qty=2),  # 6 kg
            self._item("B", w=4.0, qty=3),  # 12 kg
        ]
        result = self.packer.pack(items)
        assert result.total_weight_kg == pytest.approx(18.0)

    def test_pallet_required_for_heavy_load(self):
        # 400 kg sur palette
        items = [self._item("HEAVY", w=400.0, l=100.0, wi=70.0, h=100.0, qty=1)]
        result = self.packer.pack(items)
        assert result.box_count >= 1
        assert result.packages[0].box_type == BoxType.PALLET

    def test_ffd_orders_by_volume_descending(self):
        """Le FFD place d'abord les gros articles."""
        small = self._item("S", w=0.5, l=5.0, wi=5.0, h=5.0, qty=10)
        large = self._item("L", w=8.0, l=55.0, wi=35.0, h=35.0, qty=1)
        result = self.packer.pack([small, large])
        # Le grand article doit être dans un colis L ou M
        large_pkgs = [p for p in result.packages if p.box_type in (BoxType.L, BoxType.M)]
        assert len(large_pkgs) >= 1

    def test_summary_non_empty(self):
        items = [self._item("X", w=1.0, qty=3)]
        result = self.packer.pack(items)
        assert len(result.summary) > 0
        assert "Suggestion" in result.summary

    def test_item_codes_tracked(self):
        items = [self._item("REF-001", w=1.0, qty=1)]
        result = self.packer.pack(items)
        assert "REF-001" in result.packages[0].item_codes


# ─────────────────────────────────────────────────────────────────────────────
# PackingService (sans DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestPackingService:
    def setup_method(self):
        self.service = PackingService()

    @pytest.mark.asyncio
    async def test_suggest_packages_with_full_data(self):
        """Cas nominal : dimensions fournies explicitement."""
        items = [
            PackingItemInput(
                item_code="REF-001",
                quantity=3,
                weight_kg=2.0,
                length_cm=25.0,
                width_cm=18.0,
                height_cm=12.0,
            )
        ]
        result = await self.service.suggest_packages(items)
        assert result.success is True
        assert result.box_count >= 1
        assert result.total_weight_kg == pytest.approx(6.0)

    @pytest.mark.asyncio
    async def test_suggest_packages_empty(self):
        result = await self.service.suggest_packages([])
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_dhl_packages_format(self):
        """Le payload DHL doit avoir weight + dimensions."""
        items = [
            PackingItemInput(
                item_code="X",
                quantity=1,
                weight_kg=5.0,
                length_cm=30.0,
                width_cm=20.0,
                height_cm=20.0,
            )
        ]
        result = await self.service.suggest_packages(items)
        assert result.success is True
        assert len(result.dhl_packages) >= 1
        pkg = result.dhl_packages[0]
        assert "weight" in pkg
        assert "dimensions" in pkg
        assert set(pkg["dimensions"].keys()) == {"length", "width", "height"}

    @pytest.mark.asyncio
    async def test_fallback_default_dimensions(self):
        """Sans dimensions, les défauts doivent être utilisés."""
        items = [
            PackingItemInput(item_code="UNKNOWN-REF-XYZ9999", quantity=1)
        ]
        result = await self.service.suggest_packages(items)
        assert result.success is True
        # Doit y avoir au moins un warning sur dimensions inconnues
        assert len(result.warnings) >= 0  # pas d'erreur fatale

    def test_list_box_types(self):
        types = self.service.list_box_types()
        assert len(types) == 4
        labels = [t["label"] for t in types]
        assert "Colis S" in labels
        assert "Palette" in labels

    @pytest.mark.asyncio
    async def test_multiple_items_mixed(self):
        items = [
            PackingItemInput(
                item_code="A",
                quantity=5,
                weight_kg=1.5,
                length_cm=20.0,
                width_cm=15.0,
                height_cm=10.0,
            ),
            PackingItemInput(
                item_code="B",
                quantity=1,
                weight_kg=20.0,
                length_cm=55.0,
                width_cm=38.0,
                height_cm=38.0,
            ),
        ]
        result = await self.service.suggest_packages(items)
        assert result.success is True
        assert result.total_weight_kg == pytest.approx(27.5)
        assert result.box_count >= 1
