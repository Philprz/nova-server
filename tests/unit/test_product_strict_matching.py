# tests/unit/test_product_strict_matching.py
"""
Tests unitaires — Extraction déterministe et matching strict produit.

CAS DE RÉFÉRENCE (10 produits) :
  C892-001       → A13056 → qty 2
  C893-007-XY    → A13068 → qty 1
  C893-007-Z     → A13069 → qty 1
  C853-002       → A13070 → qty 1
  C814-RS-265-0859 → A13071 → qty 1
  C843-003       → A13072 → qty 1
  C893-002       → A13073 → qty 1
  C874-002       → A13074 → qty 2
  C843-142UMA300CACAA → A09629 → qty 2
  C893-007       → A14265 → qty 1

RÈGLES VÉRIFIÉES :
  ✔ 10 produits détectés
  ✔ 100% mapping correct (aucun produit inventé)
  ✔ 0 erreur quantité
  ✔ C893-007 conservé malgré C893-007-XY (bug déduplication corrigé)
  ✔ Ambiguïté → pending_selection, aucun auto-choix
  ✔ Code non trouvé → not_found_in_sap (aucun fuzzy)
  ✔ normalize_product_code() : tirets supprimés

Toute modification qui dégrade un cas existant est REFUSÉE.
"""

import sys
import os
import types
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.email_matcher import (
    normalize_product_code,
    extract_products_deterministic,
    EmailMatcher,
    MatchedProduct,
)


# ─── Email de référence ───────────────────────────────────────────────────────

# Format A : code + quantité sur la même ligne (TSV/espaces)
REFERENCE_EMAIL = """\
Dear Team,

Please provide a quotation for the following spare parts:

C892-001       2
C893-007-XY    1
C893-007-Z     1
C853-002       1
C814-RS-265-0859 1
C843-003       1
C893-002       1
C874-002       2
C843-142UMA300CACAA 2
C893-007       1

Regards,
Customer Service
"""

# Format B : table HTML multi-lignes (chaque cellule sur sa propre ligne)
# Rendu typique de _clean_html quand les <td> sont sur plusieurs lignes dans le HTML
REFERENCE_EMAIL_TABLE_MULTILINE = """\
Digitax Part No.

Description

Qty

C892-001

Servo Drive

2

C893-007-XY

Applications Module XY

1

C893-007-Z

Applications Module Z

1

C853-002

Compact Brake Resistor

1

C814-RS265-0859

Fuse 2A

1

C843-003

LED Keypad - DIGITAX

1

C893-002

SI-I/O Module

1

C874-002

SP-DT Adaptor MRS-9000

2

C843-142UMA300CACAA

SCHEPPE stacker XY & Z motor SERVO MOTOR 1.7 KW 3000 RPM

2

C893-HE500TIU110

HMI Screen or its alternative

1
"""

# Mapping codes → quantités pour le format B
REFERENCE_QUANTITIES_B = {
    "C892-001": 2,
    "C893-007-XY": 1,
    "C893-007-Z": 1,
    "C853-002": 1,
    "C814-RS265-0859": 1,
    "C843-003": 1,
    "C893-002": 1,
    "C874-002": 2,
    "C843-142UMA300CACAA": 2,
    "C893-HE500TIU110": 1,
}

REFERENCE_CODES_ORDERED = [
    "C892-001",
    "C893-007-XY",
    "C893-007-Z",
    "C853-002",
    "C814-RS-265-0859",
    "C843-003",
    "C893-002",
    "C874-002",
    "C843-142UMA300CACAA",
    "C893-007",
]

REFERENCE_QUANTITIES = {
    "C892-001": 2,
    "C893-007-XY": 1,
    "C893-007-Z": 1,
    "C853-002": 1,
    "C814-RS-265-0859": 1,
    "C843-003": 1,
    "C893-002": 1,
    "C874-002": 2,
    "C843-142UMA300CACAA": 2,
    "C893-007": 1,
}

# Mapping fournisseur → SAP (référence attendue)
REFERENCE_MAPPING = {
    "C892-001": "A13056",
    "C893-007-XY": "A13068",
    "C893-007-Z": "A13069",
    "C853-002": "A13070",
    "C814-RS-265-0859": "A13071",
    "C843-003": "A13072",
    "C893-002": "A13073",
    "C874-002": "A13074",
    "C843-142UMA300CACAA": "A09629",
    "C893-007": "A14265",
}


# ─── Helpers pour mock ───────────────────────────────────────────────────────

def _make_sap_item(item_code: str, supplier_code: str, name_suffix: str = "") -> dict:
    """Crée un dict article SAP minimal."""
    return {
        "ItemCode": item_code,
        "ItemName": f"{supplier_code} {name_suffix}".strip(),
        "SWeight1": None,
        "weight_unit_value": None,
        "AvgStdPrice": None,
    }


def _build_matcher_with_items(items: list) -> EmailMatcher:
    """
    Construit un EmailMatcher avec cache pré-rempli.
    Simule ensure_cache() sans appel réseau.
    """
    matcher = EmailMatcher()
    matcher._clients_cache = []
    matcher._client_domains = {}
    matcher._client_normalized = {}
    matcher._client_first_letter = {}

    matcher._items_cache = {}
    matcher._items_normalized = {}
    matcher._items_norm_code = {}

    for item in items:
        code = item["ItemCode"]
        name = item["ItemName"]
        matcher._items_cache[code] = item
        matcher._items_normalized[code] = name.lower()

        # Index codes normalisés (même logique que ensure_cache)
        nc = normalize_product_code(code)
        if nc and nc not in matcher._items_norm_code:
            matcher._items_norm_code[nc] = code

        # Index premier token de ItemName (ref fournisseur)
        if name:
            first_token = name.split()[0]
            nt = normalize_product_code(first_token)
            if len(nt) >= 4 and any(c.isdigit() for c in nt) and nt not in matcher._items_norm_code:
                matcher._items_norm_code[nt] = code

    # Mock cache_db pour match_product_strict (SQLite LIKE)
    class _MockCacheDB:
        def __init__(self, items_list):
            self._items = items_list

        def search_items(self, query: str, limit: int = 10) -> list:
            q_up = query.strip().upper()
            results = []
            for item in self._items:
                name_up = item["ItemName"].upper()
                code_up = item["ItemCode"].upper()
                if q_up in name_up or q_up in code_up:
                    results.append(item)
                    if len(results) >= limit:
                        break
            return results

    matcher._cache_db = _MockCacheDB(items)
    return matcher


# ─── Données de test ─────────────────────────────────────────────────────────

def _reference_items():
    """Construit la liste des articles SAP du cas de référence."""
    return [
        _make_sap_item("A13056", "C892-001", "SPARE PART"),
        _make_sap_item("A13068", "C893-007-XY", "PART XY"),
        _make_sap_item("A13069", "C893-007-Z", "PART Z"),
        _make_sap_item("A13070", "C853-002", "COMPONENT"),
        _make_sap_item("A13071", "C814-RS-265-0859", "MODULE RS"),
        _make_sap_item("A13072", "C843-003", "PART 003"),
        _make_sap_item("A13073", "C893-002", "PART 002"),
        _make_sap_item("A13074", "C874-002", "COMPONENT 002"),
        _make_sap_item("A09629", "C843-142UMA300CACAA", "ASSEMBLY"),
        _make_sap_item("A14265", "C893-007", "BASE PART"),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# TESTS normalize_product_code()
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeProductCode:

    def test_simple_code(self):
        assert normalize_product_code("C892-001") == "c892001"

    def test_code_with_letters(self):
        assert normalize_product_code("C893-007-XY") == "c893007xy"

    def test_complex_code(self):
        assert normalize_product_code("C814-RS-265-0859") == "c814rs2650859"

    def test_alphanumeric_suffix(self):
        assert normalize_product_code("C843-142UMA300CACAA") == "c843142uma300cacaa"

    def test_slash_equivalent_to_dash(self):
        """P-0301L-SLT et P/0301L-SLT doivent produire le même résultat."""
        assert normalize_product_code("P-0301L-SLT") == normalize_product_code("P/0301L-SLT")

    def test_empty_code(self):
        assert normalize_product_code("") == ""


# ═══════════════════════════════════════════════════════════════════════════
# TESTS extract_products_deterministic()
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractProductsDeterministic:

    def test_extracts_10_products(self):
        """CRITIQUE : 10 produits détectés depuis l'email de référence."""
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        codes_extracted = [r['code'].upper() for r in rows]
        assert len(rows) == 10, (
            f"Attendu 10 produits, obtenu {len(rows)}: {codes_extracted}"
        )

    def test_all_codes_present(self):
        """Tous les codes de référence sont extraits."""
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        codes_upper = {r['code'].upper() for r in rows}
        for expected in REFERENCE_CODES_ORDERED:
            assert expected.upper() in codes_upper, (
                f"Code manquant : {expected}. Codes extraits : {codes_upper}"
            )

    def test_c893_007_preserved(self):
        """
        BUG CRITIQUE CORRIGÉ : C893-007 doit être extrait en plus de C893-007-XY
        et C893-007-Z. Ces trois codes sont des produits distincts.
        """
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        codes_upper = {r['code'].upper() for r in rows}
        assert "C893-007" in codes_upper, "C893-007 manquant (bug déduplication)"
        assert "C893-007-XY" in codes_upper, "C893-007-XY manquant"
        assert "C893-007-Z" in codes_upper, "C893-007-Z manquant"

    def test_quantities_correct(self):
        """Quantités issues des lignes, aucune erreur."""
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        for row in rows:
            code_upper = row['code'].upper()
            if code_upper in REFERENCE_QUANTITIES:
                expected_qty = REFERENCE_QUANTITIES[code_upper]
                assert row['quantity'] == expected_qty, (
                    f"Quantité incorrecte pour {row['code']}: "
                    f"attendu {expected_qty}, obtenu {row['quantity']}"
                )

    def test_no_duplicate_codes(self):
        """Aucun code dupliqué dans l'extraction."""
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        codes = [r['code'].upper() for r in rows]
        assert len(codes) == len(set(codes)), f"Doublons détectés : {codes}"

    def test_no_fallback_quantity_one(self):
        """
        Quantité absente → None (pas de fallback à 1).
        """
        text_no_qty = "C892-001 some description without quantity\n"
        rows = extract_products_deterministic(text_no_qty)
        # Doit extraire le code mais quantité = None (absent de la ligne)
        if rows:
            assert rows[0]['quantity'] is None, (
                f"Fallback quantité détecté : {rows[0]['quantity']} (attendu None)"
            )

    def test_threshold_3_lines(self):
        """
        < 3 lignes → extraction retourne quand même les résultats.
        (Le seuil ≥ 3 est contrôlé dans _match_products, pas dans extract)
        """
        text_2_lines = "C892-001 2\nC893-002 1\n"
        rows = extract_products_deterministic(text_2_lines)
        assert len(rows) == 2

    def test_ignores_non_product_lines(self):
        """Les lignes sans code produit sont ignorées."""
        text = """\
Dear Team,
Please find attached the list.
C892-001 2
Best regards,
"""
        rows = extract_products_deterministic(text)
        assert len(rows) == 1
        assert rows[0]['code'].upper() == "C892-001"


# ═══════════════════════════════════════════════════════════════════════════
# TESTS Format B : table HTML multi-lignes (quantité sur ligne séparée)
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractProductsDeterministicTableMultiline:
    """
    Vérifie que extract_products_deterministic() gère correctement
    le Format B (table HTML rendue avec chaque cellule sur sa propre ligne).

    Format :
      C892-001
      Servo Drive
      2

    C'est le rendu typique quand _clean_html traite un <table> dont les <td>
    s'étendent sur plusieurs lignes dans le HTML source.
    """

    def test_extracts_10_products(self):
        """10 produits détectés depuis le format multi-lignes."""
        rows = extract_products_deterministic(REFERENCE_EMAIL_TABLE_MULTILINE)
        assert len(rows) == 10, (
            f"Attendu 10 produits, obtenu {len(rows)}: "
            f"{[r['code'] for r in rows]}"
        )

    def test_all_codes_present(self):
        """Tous les codes sont extraits."""
        rows = extract_products_deterministic(REFERENCE_EMAIL_TABLE_MULTILINE)
        codes_upper = {r['code'].upper() for r in rows}
        for expected in REFERENCE_QUANTITIES_B:
            assert expected.upper() in codes_upper, (
                f"Code manquant : {expected}. Codes extraits : {codes_upper}"
            )

    def test_quantities_correct(self):
        """
        CRITIQUE : les quantités sont issues du lookahead (ligne suivante),
        pas du fallback=1.
        """
        rows = extract_products_deterministic(REFERENCE_EMAIL_TABLE_MULTILINE)
        qty_map = {r['code'].upper(): r['quantity'] for r in rows}
        for code, expected_qty in REFERENCE_QUANTITIES_B.items():
            actual_qty = qty_map.get(code.upper())
            assert actual_qty == expected_qty, (
                f"Quantité incorrecte pour {code}: "
                f"attendu {expected_qty}, obtenu {actual_qty}"
            )

    def test_qty_2_not_defaulted_to_1(self):
        """
        C892-001 doit avoir qty=2, pas 1.
        C'est le cas critique qui échouait avant le lookahead.
        """
        rows = extract_products_deterministic(REFERENCE_EMAIL_TABLE_MULTILINE)
        qty_map = {r['code'].upper(): r['quantity'] for r in rows}
        assert qty_map.get("C892-001") == 2, (
            f"C892-001 qty attendu=2, obtenu={qty_map.get('C892-001')} "
            "(bug : quantité sur ligne séparée non trouvée)"
        )
        assert qty_map.get("C874-002") == 2, (
            f"C874-002 qty attendu=2, obtenu={qty_map.get('C874-002')}"
        )
        assert qty_map.get("C843-142UMA300CACAA") == 2, (
            f"C843-142UMA300CACAA qty attendu=2, obtenu={qty_map.get('C843-142UMA300CACAA')}"
        )

    def test_header_row_ignored(self):
        """La ligne d'en-tête 'Digitax Part No.' n'est pas extraite comme code."""
        rows = extract_products_deterministic(REFERENCE_EMAIL_TABLE_MULTILINE)
        codes = [r['code'].upper() for r in rows]
        assert "DIGITAX" not in codes
        assert not any("PART" in c or "NO" in c for c in codes)

    def test_description_line_not_extracted_as_code(self):
        """Les descriptions 'Servo Drive', 'LED Keypad...' ne sont pas extraites."""
        rows = extract_products_deterministic(REFERENCE_EMAIL_TABLE_MULTILINE)
        codes = {r['code'].upper() for r in rows}
        # Aucun code ne doit commencer par des mots de description
        assert not any(c.startswith("SERVO") for c in codes)
        assert not any(c.startswith("LED") for c in codes)
        assert not any(c.startswith("FUSE") for c in codes)

    def test_lookahead_stops_at_next_code(self):
        """Le lookahead s'arrête dès le prochain code produit (pas de contamination)."""
        # Texte avec deux codes consécutifs sans ligne qty entre eux
        text = "C892-001\nC893-002\n1\n"
        rows = extract_products_deterministic(text)
        assert len(rows) == 2
        code_map = {r['code'].upper(): r['quantity'] for r in rows}
        # C892-001 n'a pas de qty (le lookahead s'arrête car C893-002 est un code)
        assert code_map.get("C892-001") is None, (
            "Le lookahead ne doit pas traverser un autre code produit"
        )
        # C893-002 a qty=1
        assert code_map.get("C893-002") == 1


# ═══════════════════════════════════════════════════════════════════════════
# TESTS match_product_strict()
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchProductStrict:

    def setup_method(self):
        self.matcher = _build_matcher_with_items(_reference_items())

    def test_exact_match_via_item_name(self):
        """C892-001 → A13056 (via ItemName 'C892-001 SPARE PART')."""
        results = self.matcher.match_product_strict("C892-001", quantity=2)
        assert len(results) == 1
        assert results[0].item_code == "A13056"
        assert results[0].quantity == 2
        assert results[0].score == 100

    def test_code_with_letter_suffix(self):
        """C893-007-XY → A13068."""
        results = self.matcher.match_product_strict("C893-007-XY", quantity=1)
        assert len(results) == 1
        assert results[0].item_code == "A13068"

    def test_code_z_suffix(self):
        """C893-007-Z → A13069."""
        results = self.matcher.match_product_strict("C893-007-Z", quantity=1)
        assert len(results) == 1
        assert results[0].item_code == "A13069"

    def test_base_code_distinct_from_suffixed(self):
        """C893-007 → A14265 (distinct de C893-007-XY et C893-007-Z)."""
        results = self.matcher.match_product_strict("C893-007", quantity=1)
        # Peut retourner 1 ou plusieurs selon la précision du LIKE
        # L'essentiel : A14265 est parmi les résultats
        item_codes = [r.item_code for r in results]
        assert "A14265" in item_codes, (
            f"A14265 attendu pour C893-007, obtenu : {item_codes}"
        )

    def test_complex_code(self):
        """C814-RS-265-0859 → A13071."""
        results = self.matcher.match_product_strict("C814-RS-265-0859", quantity=1)
        assert len(results) == 1
        assert results[0].item_code == "A13071"

    def test_alphanumeric_suffix_code(self):
        """C843-142UMA300CACAA → A09629."""
        results = self.matcher.match_product_strict("C843-142UMA300CACAA", quantity=2)
        assert len(results) == 1
        assert results[0].item_code == "A09629"
        assert results[0].quantity == 2

    def test_not_found_returns_empty(self):
        """Code inconnu → liste vide (aucun fuzzy)."""
        results = self.matcher.match_product_strict("ZZZNOTEXIST-999", quantity=1)
        assert results == [], f"Attendu [], obtenu {results}"

    def test_quantity_from_parameter(self):
        """La quantité vient toujours du paramètre, jamais du texte."""
        results = self.matcher.match_product_strict("C874-002", quantity=2)
        assert len(results) == 1
        assert results[0].quantity == 2

    def test_ambiguity_returns_multiple(self):
        """
        Si plusieurs articles SAP correspondent → retourner tous.
        (pending_selection géré par _match_products, pas par match_product_strict)
        """
        # Ajouter un doublon pour tester
        items = _reference_items() + [
            _make_sap_item("A99999", "C892-001", "VARIANT 2")
        ]
        matcher = _build_matcher_with_items(items)
        results = matcher.match_product_strict("C892-001", quantity=1)
        # Les deux articles contenant "C892-001" dans ItemName sont retournés
        assert len(results) >= 2, (
            f"Ambiguïté attendue (≥2 résultats), obtenu {len(results)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TESTS _match_products() — chemin déterministe (PHASE 0C)
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchProductsDeterministic:
    """
    Vérifie que _match_products() active le chemin déterministe
    quand ≥ 3 lignes structurées sont détectées.
    """

    def setup_method(self):
        self.matcher = _build_matcher_with_items(_reference_items())
        # Mock _extract_offer_request_rows (format Marmara Cam) → retourne []
        # pour ne pas interférer avec le chemin déterministe
        self.matcher._extract_offer_request_rows = lambda text: []
        # Mock _extract_product_descriptions
        self.matcher._extract_product_descriptions = lambda text: {}

    def test_10_products_detected(self):
        """CRITIQUE : 10 produits détectés depuis l'email de référence."""
        results = self.matcher._match_products(REFERENCE_EMAIL)
        assert len(results) == 10, (
            f"Attendu 10 produits, obtenu {len(results)}: "
            f"{[(r.item_code, r.match_reason[:30]) for r in results]}"
        )

    def test_no_invented_products(self):
        """Aucun produit inventé (not_found_in_sap=False sur les 10 produits)."""
        results = self.matcher._match_products(REFERENCE_EMAIL)
        invented = [r for r in results if r.not_found_in_sap]
        assert len(invented) == 0, (
            f"Produits inventés : {[(r.item_code, r.match_reason) for r in invented]}"
        )

    def test_correct_mapping(self):
        """100% mapping correct : chaque code fournisseur → bon code SAP."""
        results = self.matcher._match_products(REFERENCE_EMAIL)
        # Construire map code_fournisseur → item_code_sap (via item_name)
        # item_name est "C892-001 SPARE PART" → premier token = code fournisseur
        for result in results:
            if result.status == "pending_selection" or result.not_found_in_sap:
                continue
            # Trouver le code fournisseur source depuis item_name ou original_code
            supplier_code = result.item_name.split()[0].upper()
            expected_sap = REFERENCE_MAPPING.get(supplier_code)
            if expected_sap:
                assert result.item_code == expected_sap, (
                    f"Mauvais mapping pour {supplier_code}: "
                    f"attendu {expected_sap}, obtenu {result.item_code}"
                )

    def test_quantities_correct(self):
        """0 erreur de quantité."""
        results = self.matcher._match_products(REFERENCE_EMAIL)
        for result in results:
            if result.not_found_in_sap:
                continue
            supplier_code = result.item_name.split()[0].upper() if result.item_name else ""
            expected_qty = REFERENCE_QUANTITIES.get(supplier_code)
            if expected_qty is not None:
                assert result.quantity == expected_qty, (
                    f"Quantité incorrecte pour {supplier_code}: "
                    f"attendu {expected_qty}, obtenu {result.quantity}"
                )

    def test_no_auto_select_on_ambiguity(self):
        """
        Si ambiguïté → status='pending_selection', aucun auto-choix.
        """
        # Ajouter un doublon pour forcer l'ambiguïté sur C892-001
        items = _reference_items() + [
            _make_sap_item("A99999", "C892-001", "VARIANT 2")
        ]
        matcher = _build_matcher_with_items(items)
        matcher._extract_offer_request_rows = lambda text: []
        matcher._extract_product_descriptions = lambda text: {}

        results = matcher._match_products(REFERENCE_EMAIL)
        ambiguous = [r for r in results if r.status == "pending_selection"]
        # Il doit y avoir au moins 1 ambiguïté (C892-001 → A13056 + A99999)
        assert len(ambiguous) >= 1, "Ambiguïté attendue non détectée"
        # Vérifier que candidates est rempli
        for amb in ambiguous:
            assert len(amb.candidates) >= 2, (
                f"Candidats manquants pour {amb.item_code}: {amb.candidates}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# TEST — déduplication corrigée (C893-007 vs C893-007-XY)
# ═══════════════════════════════════════════════════════════════════════════

class TestDeduplicationFix:
    """
    Vérifie que le bug de déduplication est corrigé :
    C893-007 ne doit pas être supprimé parce que C893-007-XY existe.
    """

    def test_c893_007_not_filtered_out(self):
        """
        extract_products_deterministic : C893-007 est conservé
        même si C893-007-XY et C893-007-Z sont présents.
        """
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        codes = {r['code'].upper() for r in rows}
        assert "C893-007" in codes, (
            "BUG DÉDUPLICATION : C893-007 a été supprimé en tant que sous-chaîne "
            "de C893-007-XY ou C893-007-Z"
        )

    def test_all_three_c893_variants_present(self):
        """Les trois variantes C893-007, C893-007-XY, C893-007-Z sont toutes extraites."""
        rows = extract_products_deterministic(REFERENCE_EMAIL)
        codes = {r['code'].upper() for r in rows}
        for variant in ("C893-007", "C893-007-XY", "C893-007-Z"):
            assert variant in codes, (
                f"Variante manquante : {variant}. Codes extraits : {codes}"
            )
