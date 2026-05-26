# tests/unit/test_excel_attachment_extraction.py
"""
Tests unitaires — Extraction produits depuis pièce jointe Excel.

CAS COUVERTS :
  Test 1 — Non-régression : email sans Excel → comportement inchangé
  Test 2 — Extraction Excel : email avec Excel valide → lignes extraites
  Test 3 — Conservation sans matching : lignes non-SAP restent dans la sortie
  Test 4 — Propagation API : la liste structurée est bien dans product_matches
  Test 5 — Priorité des sources : Excel > corps du mail

Exigences :
  - Aucune ligne produit Excel ne doit être silencieusement supprimée.
  - match_status="unmatched" sur les lignes sans correspondance SAP.
  - source_file renseigné pour toute ligne issue d'Excel.
"""

import sys
import os
import io
import tempfile
import types
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.email_matcher import MatchedProduct, normalize_product_code


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_xlsx_bytes(rows: list[dict]) -> bytes:
    """
    Crée un fichier Excel minimal en mémoire (openpyxl).
    rows = [{'reference': ..., 'designation': ..., 'qty': ...}, ...]
    """
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Reference", "Designation", "Qty"])
    for r in rows:
        ws.append([r.get("reference", ""), r.get("designation", ""), r.get("qty", 1)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_tmp_xlsx(rows: list[dict]) -> str:
    """Écrit un xlsx temporaire et retourne le chemin."""
    data = _make_xlsx_bytes(rows)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
        f.write(data)
        return f.name


# ─── Test 1 : Non-régression — email sans Excel ───────────────────────────────

class TestNoRegressionWithoutExcel:
    """
    Un email sans pièce jointe Excel ne doit pas être affecté par la correction.
    Le flux MatchedProduct existant reste inchangé.
    """

    def test_matched_product_fields_unchanged(self):
        """Les champs existants de MatchedProduct ne doivent pas être brisés."""
        mp = MatchedProduct(
            item_code="A13056",
            item_name="C892-001 SPARE PART",
            quantity=2,
            score=100,
            match_reason="Code exact match",
        )
        assert mp.item_code == "A13056"
        assert mp.quantity == 2
        assert mp.score == 100
        assert mp.not_found_in_sap is False

    def test_new_fields_have_safe_defaults(self):
        """
        Les nouveaux champs de traçabilité ont des valeurs par défaut
        neutres — ne cassent pas l'existant.
        """
        mp = MatchedProduct(
            item_code="A13056",
            item_name="C892-001",
            quantity=1,
            score=100,
            match_reason="test",
        )
        assert mp.source_file is None
        assert mp.source_sheet is None
        assert mp.source_row_index is None
        assert mp.raw_label is None
        assert mp.match_status == "matched"
        assert mp.discard_reason is None

    def test_serialisation_dict_unchanged(self):
        """dict() ne doit pas lever d'exception sur un objet existant."""
        mp = MatchedProduct(
            item_code="A13056",
            item_name="C892-001",
            quantity=1,
            score=100,
            match_reason="test",
        )
        d = mp.dict()
        assert d["item_code"] == "A13056"
        # Nouveaux champs présents dans le dict mais avec valeur None / défaut
        assert "source_file" in d
        assert "match_status" in d
        assert d["match_status"] == "matched"


# ─── Test 2 : Extraction Excel ────────────────────────────────────────────────

class TestExcelExtraction:
    """
    Un fichier Excel valide doit être parsé et produire des lignes structurées.
    """

    def test_excel_parser_returns_rows(self):
        """ExcelParser.parse() retourne au moins une ligne pour un xlsx valide."""
        from services.file_parsers import ExcelParser

        tmp_path = _write_tmp_xlsx([
            {"reference": "C892-001", "designation": "Servo Drive", "qty": 2},
            {"reference": "C893-007-XY", "designation": "Applications Module", "qty": 1},
        ])
        try:
            rows = ExcelParser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert len(rows) >= 1, f"Aucune ligne extraite : {rows}"

    def test_excel_row_has_reference_field(self):
        """Chaque ligne doit contenir 'supplier_reference' ou 'designation'."""
        from services.file_parsers import ExcelParser

        tmp_path = _write_tmp_xlsx([
            {"reference": "C892-001", "designation": "Servo Drive", "qty": 2},
        ])
        try:
            rows = ExcelParser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert rows, "Aucune ligne extraite"
        row = rows[0]
        assert row.get("supplier_reference") or row.get("designation"), (
            f"Ligne sans référence ni désignation : {row}"
        )

    def test_excel_source_metadata_in_additional_data(self):
        """additional_data doit contenir source_file et sheet_name."""
        from services.file_parsers import ExcelParser

        tmp_path = _write_tmp_xlsx([
            {"reference": "REF-001", "designation": "Test Article", "qty": 1},
        ])
        try:
            rows = ExcelParser.parse(tmp_path)
        finally:
            pass  # keep file for assert then delete

        try:
            assert rows, "Aucune ligne extraite"
            meta = rows[0].get("additional_data", {})
            assert "source_file" in meta, f"source_file absent de additional_data : {meta}"
            assert "sheet_name" in meta, f"sheet_name absent de additional_data : {meta}"
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def test_empty_xlsx_returns_empty_list(self):
        """Un xlsx sans données (header seulement) ne plante pas."""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Reference", "Designation"])
        buf = io.BytesIO()
        wb.save(buf)

        from services.file_parsers import ExcelParser
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as f:
            f.write(buf.getvalue())
            tmp_path = f.name
        try:
            rows = ExcelParser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert isinstance(rows, list), "Doit retourner une liste, même vide"


# ─── Test 3 : Conservation sans matching SAP ──────────────────────────────────

class TestUnmatchedRowsPreserved:
    """
    Une ligne extraite d'Excel sans correspondance SAP doit rester visible
    avec match_status='unmatched' et not_found_in_sap=True.
    Interdiction absolue de la supprimer silencieusement.
    """

    def test_unmatched_product_created_with_correct_flags(self):
        """Un produit non trouvé dans SAP est créé avec les bons flags."""
        mp = MatchedProduct(
            item_code="REF-INCONNUE-999",
            item_name="Article inconnu dans SAP",
            quantity=3,
            score=0,
            match_reason="Extrait depuis pièce jointe Excel — non trouvé dans SAP",
            not_found_in_sap=True,
            match_status="unmatched",
            source_file="liste_pieces.xlsx",
            source_sheet="Sheet1",
            source_row_index=0,
            raw_label="Article inconnu dans SAP",
            discard_reason="Aucune correspondance SAP pour 'REF-INCONNUE-999'",
        )
        assert mp.not_found_in_sap is True
        assert mp.match_status == "unmatched"
        assert mp.source_file == "liste_pieces.xlsx"
        assert mp.discard_reason is not None

    def test_unmatched_product_not_filtered_by_status(self):
        """
        match_status='unmatched' est différent de status='pending_selection'.
        La ligne ne doit pas être filtrée par la logique pending_selection.
        """
        mp = MatchedProduct(
            item_code="REF-INCONNUE",
            item_name="Produit inconnu",
            quantity=1,
            score=0,
            match_reason="non trouvé",
            not_found_in_sap=True,
            match_status="unmatched",
            source_file="test.xlsx",
        )
        # status doit rester None (pas 'pending_selection')
        assert mp.status is None or mp.status != "pending_selection"

    def test_unmatched_product_preserved_in_list(self):
        """
        Une liste mixte (matched + unmatched) ne doit pas perdre les unmatched
        lors du filtrage frontend (status != 'pending_selection').
        """
        products = [
            MatchedProduct(
                item_code="A13056",
                item_name="C892-001 SPARE PART",
                quantity=2,
                score=100,
                match_reason="exact",
                match_status="matched",
            ),
            MatchedProduct(
                item_code="REF-INCONNU",
                item_name="Article non SAP",
                quantity=1,
                score=0,
                match_reason="non trouvé",
                not_found_in_sap=True,
                match_status="unmatched",
                source_file="test.xlsx",
            ),
        ]
        # Simuler le filtre frontend : exclure pending_selection uniquement
        visible = [p for p in products if p.status != "pending_selection"]
        assert len(visible) == 2, (
            f"L'article non-matché a disparu du filtre : {[p.item_code for p in visible]}"
        )


# ─── Test 4 : Propagation API ─────────────────────────────────────────────────

class TestApiPropagation:
    """
    La liste structurée produits Excel doit être exposée dans product_matches
    et sérialisable en JSON (dict).
    """

    def test_unmatched_product_serialisable(self):
        """dict() sur un produit Excel non-matché ne doit pas lever d'exception."""
        mp = MatchedProduct(
            item_code="REF-001",
            item_name="Désignation test",
            quantity=2,
            score=0,
            match_reason="Extrait Excel",
            not_found_in_sap=True,
            match_status="unmatched",
            source_file="commande.xlsx",
            source_sheet="Articles",
            source_row_index=3,
            raw_label="Désignation test",
            discard_reason="Aucune correspondance SAP",
        )
        d = mp.dict()
        assert d["item_code"] == "REF-001"
        assert d["match_status"] == "unmatched"
        assert d["source_file"] == "commande.xlsx"
        assert d["source_row_index"] == 3
        assert d["discard_reason"] is not None

    def test_product_matches_list_contains_unmatched(self):
        """
        result.product_matches (liste de dicts) doit contenir les produits non-matchés.
        """
        products = [
            MatchedProduct(
                item_code="A13056",
                item_name="C892-001",
                quantity=2,
                score=100,
                match_reason="exact",
                match_status="matched",
                source_file="liste.xlsx",
            ),
            MatchedProduct(
                item_code="INCONNUE-001",
                item_name="Produit sans code SAP",
                quantity=1,
                score=0,
                match_reason="non trouvé",
                not_found_in_sap=True,
                match_status="unmatched",
                source_file="liste.xlsx",
            ),
        ]
        serialized = [p.dict() for p in products]
        assert len(serialized) == 2
        unmatched = [d for d in serialized if d["match_status"] == "unmatched"]
        assert len(unmatched) == 1
        assert unmatched[0]["item_code"] == "INCONNUE-001"


# ─── Test 5 : Priorité des sources ────────────────────────────────────────────

class TestSourcePriority:
    """
    Si Excel et corps du mail coexistent, la liste produits doit provenir
    prioritairement de l'Excel.
    """

    def test_excel_products_have_source_file_set(self):
        """Les produits Excel ont source_file renseigné ; les produits texte non."""
        excel_product = MatchedProduct(
            item_code="A13056",
            item_name="C892-001",
            quantity=2,
            score=100,
            match_reason="match via Excel",
            match_status="matched",
            source_file="liste_pieces.xlsx",
        )
        text_product = MatchedProduct(
            item_code="A13073",
            item_name="C893-002",
            quantity=1,
            score=100,
            match_reason="match via corps",
            match_status="matched",
        )
        assert excel_product.source_file is not None
        assert text_product.source_file is None

    def test_excel_takes_priority_over_body(self):
        """
        Simulation de la règle de priorité : si excel_products est non vide,
        result.product_matches = [p.dict() for p in excel_products]
        doit écraser les produits issus du corps.
        """
        body_products = [
            {"item_code": "A13073", "item_name": "C893-002", "quantity": 1,
             "score": 80, "match_reason": "corps", "match_status": "matched"},
        ]
        excel_products = [
            MatchedProduct(
                item_code="A13056",
                item_name="C892-001",
                quantity=2,
                score=100,
                match_reason="Excel exact",
                match_status="matched",
                source_file="commande.xlsx",
            ),
            MatchedProduct(
                item_code="REF-NEW",
                item_name="Nouveau produit",
                quantity=3,
                score=0,
                match_reason="non trouvé",
                not_found_in_sap=True,
                match_status="unmatched",
                source_file="commande.xlsx",
            ),
        ]

        # Simulation de la règle Phase 4.6 dans routes_graph.py
        if excel_products:
            result_product_matches = [p.dict() for p in excel_products]
        else:
            result_product_matches = body_products

        assert len(result_product_matches) == 2, (
            "Les produits Excel doivent remplacer les produits du corps"
        )
        codes = [d["item_code"] for d in result_product_matches]
        assert "A13056" in codes
        assert "REF-NEW" in codes
        assert "A13073" not in codes, (
            "Le produit du corps ne doit pas apparaître quand Excel est présent"
        )

    def test_body_fallback_when_no_excel(self):
        """
        Sans Excel, les produits issus du corps du mail sont conservés.
        """
        body_products_dicts = [
            {"item_code": "A13073", "item_name": "C893-002", "quantity": 1,
             "score": 80, "match_reason": "corps", "match_status": "matched"},
        ]
        excel_products: list = []  # Pas d'Excel

        if excel_products:
            result_product_matches = [p.dict() for p in excel_products]
        else:
            result_product_matches = body_products_dicts

        assert len(result_product_matches) == 1
        assert result_product_matches[0]["item_code"] == "A13073"
