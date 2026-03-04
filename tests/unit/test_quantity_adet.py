"""
Tests unitaires — Extraction stricte des quantités via le mot-clé 'Adet'.

RÈGLE MÉTIER : Dans les documents de type 'Offer Request Form' (Marmara Cam),
la quantité valide est UNIQUEMENT le nombre immédiatement suivi du mot 'Adet'.

Critères d'acceptation :
  ✔ 0 quantité incorrecte
  ✔ Ordre identique au PDF source (Row No)
  ✔ Aucune valeur technique interprétée comme quantité
  ✔ Test non-régression : 194 ne doit JAMAIS apparaître comme quantité
"""

import os
import pytest
from services.email_matcher import extract_quantity_strict_adet, EmailMatcher
from services.email_analyzer import _extract_offer_request_form_text

# Chemin vers le vrai PDF Sheppee (présent dans le repo)
_SHEPPEE_PDF = os.path.join(os.path.dirname(__file__), '..', '..', 'Sheppee International Ltd_20250701 (1).pdf')
_SHEPPEE_PDF_AVAILABLE = os.path.exists(_SHEPPEE_PDF)


# ---------------------------------------------------------------------------
# Tests de la fonction standalone extract_quantity_strict_adet()
# ---------------------------------------------------------------------------

class TestExtractQuantityStrictAdet:
    """Tests de la fonction extract_quantity_strict_adet()."""

    # --- Cas VALIDES ---

    def test_integer_adet(self):
        assert extract_quantity_strict_adet("50 Adet") == 50.0

    def test_decimal_comma_adet(self):
        assert extract_quantity_strict_adet("50,00 Adet") == 50.0

    def test_decimal_dot_adet(self):
        assert extract_quantity_strict_adet("2.00 Adet") == 2.0

    def test_one_adet(self):
        assert extract_quantity_strict_adet("1,00 Adet") == 1.0

    def test_two_adet(self):
        assert extract_quantity_strict_adet("2 Adet") == 2.0

    def test_adet_case_insensitive(self):
        # 'adet' et 'ADET' doivent aussi matcher
        assert extract_quantity_strict_adet("3 adet") == 3.0
        assert extract_quantity_strict_adet("4 ADET") == 4.0

    def test_adet_in_row_context(self):
        line = "Row 1: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet"
        assert extract_quantity_strict_adet(line) == 50.0

    def test_adet_in_multiline_context(self):
        text = """
Row 1: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
Row 2: C233-50AT10-1940G3 - D5 SHEPPEE STAKER timing belt - 2 Adet
"""
        # Doit retourner le PREMIER match dans le texte
        assert extract_quantity_strict_adet(text) == 50.0

    # --- Cas INVALIDES (ne doivent PAS être détectés comme quantités) ---

    def test_no_adet_keyword_returns_none(self):
        """Un nombre sans 'Adet' ne doit JAMAIS être retourné."""
        assert extract_quantity_strict_adet("DİŞ SAYISI: 194") is None

    def test_technical_spec_194_not_quantity(self):
        """194 est un nombre de dents (technique), pas une quantité."""
        assert extract_quantity_strict_adet("DİŞ SAYISI: 194") is None

    def test_dimension_not_quantity(self):
        assert extract_quantity_strict_adet("1940mm") is None

    def test_product_code_not_quantity(self):
        assert extract_quantity_strict_adet("50AT10") is None

    def test_dimension_lg_not_quantity(self):
        assert extract_quantity_strict_adet("1160 LG") is None

    def test_position_number_not_quantity(self):
        assert extract_quantity_strict_adet("POS.8") is None

    def test_empty_text_returns_none(self):
        assert extract_quantity_strict_adet("") is None

    def test_no_number_at_all_returns_none(self):
        assert extract_quantity_strict_adet("SIZE 3 PUSHER BLADE") is None

    def test_mixed_technical_and_adet_prefers_adet(self):
        """Même si du texte technique contient des nombres, seul 'Adet' compte."""
        text = "DİŞ SAYISI: 194\n50,00 Adet"
        assert extract_quantity_strict_adet(text) == 50.0

    def test_194_never_returned_as_quantity_even_mixed(self):
        """
        Test non-régression critique : 194 ne doit JAMAIS apparaître comme quantité,
        même dans un texte mixte.
        """
        text = "DİŞ SAYISI: 194\nRow 2: C233-50AT10-1940G3 - timing belt - 2 Adet"
        result = extract_quantity_strict_adet(text)
        assert result != 194.0, "RÉGRESSION : 194 (valeur technique) détecté comme quantité !"
        assert result == 2.0


# ---------------------------------------------------------------------------
# Tests de _extract_offer_request_rows() (méthode de classe)
# ---------------------------------------------------------------------------

# Extrait réel du PDF Marmara Cam Form No 26576
MARMARA_PDF_EXTRACT = """
OFFER REQUEST FORM
Marmara Cam Sanayi ve Tic. A.Ş.
Sheppee International Ltd
Email: msezen@marmaracam.com.tr
Date : 1.07.2025
Form No : 26576

Row 1: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
Row 2: C233-50AT10-1940G3 - D5 SHEPPEE STAKER timing belt - 2 Adet
Row 3: C281-RV80 - Z-AXIS GEAR UNIT - 1 Adet
Row 4: C362-M035-SF - FLANGED BEARING UNIT - 2 Adet
Row 5: TRI-037 - LIFT ROLLER STUD - 2 Adet
"""

# Texte avec données techniques trompeuses (cas Sheppee International PDF 26576)
TRICKY_PDF_WITH_TECHNICAL_DATA = """
OFFER REQUEST FORM

Row 1: HST-117-03 - SIZE 3 PUSHER BLADE CARBON - 50 Adet
  DİŞ SAYISI: 194
  Çap: 1940mm
  Belt: 50AT10

Row 2: C233-50AT10-1940G3 - D5 SHEPPEE STAKER timing belt - 2 Adet
  POS.8
  LG: 1160

Row 3: C281-RV80 - Z-AXIS GEAR UNIT - 1 Adet
"""


class TestExtractOfferRequestRows:
    """Tests de EmailMatcher._extract_offer_request_rows()."""

    @pytest.fixture
    def matcher(self):
        """Créer une instance légère (sans cache SAP) pour les tests."""
        m = EmailMatcher.__new__(EmailMatcher)
        m._items_cache = {}
        return m

    def test_basic_rows_extracted(self, matcher):
        rows = matcher._extract_offer_request_rows(MARMARA_PDF_EXTRACT)
        assert len(rows) == 5

    def test_row_no_correct(self, matcher):
        rows = matcher._extract_offer_request_rows(MARMARA_PDF_EXTRACT)
        assert rows[0]['row_no'] == 1
        assert rows[1]['row_no'] == 2
        assert rows[4]['row_no'] == 5

    def test_codes_correct(self, matcher):
        rows = matcher._extract_offer_request_rows(MARMARA_PDF_EXTRACT)
        assert rows[0]['code'] == 'HST-117-03'
        assert rows[1]['code'] == 'C233-50AT10-1940G3'
        assert rows[2]['code'] == 'C281-RV80'

    def test_quantities_strict_adet(self, matcher):
        """
        Vérification critique des quantités depuis l'extrait réel PDF 26576.
        Row 1 → 50, Row 2 → 2, Row 3 → 1
        """
        rows = matcher._extract_offer_request_rows(MARMARA_PDF_EXTRACT)
        assert rows[0]['quantity'] == 50, "Row 1 doit être 50"
        assert rows[1]['quantity'] == 2,  "Row 2 doit être 2"
        assert rows[2]['quantity'] == 1,  "Row 3 doit être 1"

    def test_no_quantity_194(self, matcher):
        """
        Test non-régression ABSOLU : 194 (DİŞ SAYISI) ne doit JAMAIS apparaître
        comme quantité dans aucune ligne.
        """
        rows = matcher._extract_offer_request_rows(TRICKY_PDF_WITH_TECHNICAL_DATA)
        quantities = [r['quantity'] for r in rows]
        assert 194 not in quantities, (
            f"RÉGRESSION CRITIQUE : 194 (valeur technique 'DİŞ SAYISI') "
            f"détecté comme quantité ! Quantités extraites : {quantities}"
        )

    def test_no_technical_values_as_quantity(self, matcher):
        """Aucune valeur technique (194, 1940, 1160) ne doit être une quantité."""
        rows = matcher._extract_offer_request_rows(TRICKY_PDF_WITH_TECHNICAL_DATA)
        quantities = [r['quantity'] for r in rows]
        forbidden = [194, 1940, 1160, 8]
        for val in forbidden:
            assert val not in quantities, (
                f"Valeur technique {val} détectée comme quantité ! "
                f"Quantités extraites : {quantities}"
            )

    def test_quantities_correct_with_technical_data(self, matcher):
        """Même avec données techniques trompeuses, les quantités Adet sont correctes."""
        rows = matcher._extract_offer_request_rows(TRICKY_PDF_WITH_TECHNICAL_DATA)
        assert rows[0]['quantity'] == 50
        assert rows[1]['quantity'] == 2
        assert rows[2]['quantity'] == 1

    def test_sorted_by_row_no(self, matcher):
        """Les lignes doivent être triées par row_no (ordre du document source)."""
        rows = matcher._extract_offer_request_rows(MARMARA_PDF_EXTRACT)
        row_nos = [r['row_no'] for r in rows]
        assert row_nos == sorted(row_nos), f"Lignes non triées : {row_nos}"

    def test_empty_text_returns_empty(self, matcher):
        """Un texte sans 'Row N:' doit retourner une liste vide."""
        rows = matcher._extract_offer_request_rows("Bonjour, veuillez me faire un devis pour 5 pièces.")
        assert rows == []

    def test_regular_email_returns_empty(self, matcher):
        """Un email classique (sans format Offer Request) doit retourner une liste vide."""
        email = """
        Dear Sir,
        Please find attached our request for quotation.
        We need 50 pcs of HST-117-03.
        Best regards.
        """
        rows = matcher._extract_offer_request_rows(email)
        assert rows == []

    def test_decimal_quantity_parsed_as_int(self, matcher):
        """50,00 Adet doit produire quantity = 50 (int), pas 50.0."""
        text = "Row 1: HST-117-03 - PUSHER BLADE - 50,00 Adet"
        rows = matcher._extract_offer_request_rows(text)
        assert rows[0]['quantity'] == 50
        assert isinstance(rows[0]['quantity'], int)


# ---------------------------------------------------------------------------
# Tests sur le vrai PDF Sheppee International Ltd (Form No 26576)
# Ces tests vérifient l'extracteur par coordonnées PDF (_extract_offer_request_form_text)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _SHEPPEE_PDF_AVAILABLE, reason="PDF Sheppee absent du repo")
class TestExtractOfferRequestFormFromRealPDF:
    """
    Tests de non-régression sur le vrai PDF Sheppee International Ltd_20250701.

    Critères absolus :
      ✔ 28 lignes extraites (toutes les lignes du document)
      ✔ Codes corrects pour chaque Row No
      ✔ Quantité 194 (DİŞ SAYISI) JAMAIS extraite comme quantité
      ✔ Quantités Row 1=50, Row 2=2, Row 3=1 correctes
      ✔ Résultat contient les lignes "Row N: CODE - DESC - QTY Adet"
    """

    @pytest.fixture(scope='class')
    def extracted_rows(self):
        """Extraire les lignes structurées du PDF réel (exécuté une fois par classe)."""
        result = _extract_offer_request_form_text(_SHEPPEE_PDF)
        # Parser uniquement les lignes "Row N:" (ignorer le texte brut)
        matcher = EmailMatcher.__new__(EmailMatcher)
        matcher._items_cache = {}
        rows = matcher._extract_offer_request_rows(result)
        return {r['row_no']: r for r in rows}

    def test_total_28_rows(self, extracted_rows):
        """Le PDF contient exactement 28 lignes produit."""
        assert len(extracted_rows) == 28, (
            f"Attendu 28 lignes, obtenu {len(extracted_rows)}. "
            f"Row Nos présents : {sorted(extracted_rows.keys())}"
        )

    def test_all_row_numbers_present(self, extracted_rows):
        """Les Row No 1 à 28 doivent tous être présents."""
        missing = [i for i in range(1, 29) if i not in extracted_rows]
        assert not missing, f"Row Nos manquants : {missing}"

    def test_row1_code_and_quantity(self, extracted_rows):
        """Row 1 : HST-117-03, quantité 50."""
        row = extracted_rows[1]
        assert row['code'] == 'HST-117-03', f"Row 1 code incorrect: {row['code']}"
        assert row['quantity'] == 50, f"Row 1 quantité incorrecte: {row['quantity']}"

    def test_row2_code_and_quantity(self, extracted_rows):
        """Row 2 : C233-50AT10-1940G3, quantité 2. (Le timing belt avec DİŞ SAYISI: 194)"""
        row = extracted_rows[2]
        assert row['code'] == 'C233-50AT10-1940G3', f"Row 2 code incorrect: {row['code']}"
        assert row['quantity'] == 2, f"Row 2 quantité incorrecte: {row['quantity']}"

    def test_row3_code_and_quantity(self, extracted_rows):
        """Row 3 : C281-RV80, quantité 1."""
        row = extracted_rows[3]
        assert row['code'] == 'C281-RV80', f"Row 3 code incorrect: {row['code']}"
        assert row['quantity'] == 1, f"Row 3 quantité incorrecte: {row['quantity']}"

    def test_no_quantity_194_anywhere(self, extracted_rows):
        """
        RÉGRESSION ABSOLUE : 194 (DİŞ SAYISI = nombre de dents de la courroie)
        ne doit JAMAIS apparaître comme quantité dans aucune ligne.
        """
        quantities = {rn: r['quantity'] for rn, r in extracted_rows.items()}
        assert 194 not in quantities.values(), (
            f"RÉGRESSION CRITIQUE : 194 apparaît comme quantité ! "
            f"Quantités extraites : {quantities}"
        )

    def test_no_technical_values_as_quantity(self, extracted_rows):
        """Aucune valeur technique (1940, 1160, 1480) ne doit être une quantité."""
        quantities = set(r['quantity'] for r in extracted_rows.values())
        forbidden = {194, 1940, 1160, 1480}
        found = quantities & forbidden
        assert not found, f"Valeurs techniques détectées comme quantités : {found}"

    def test_row28_code_and_quantity(self, extracted_rows):
        """Row 28 : MRS-0005, quantité 1 (dernière ligne du document)."""
        row = extracted_rows[28]
        assert row['code'] == 'MRS-0005', f"Row 28 code incorrect: {row['code']}"
        assert row['quantity'] == 1, f"Row 28 quantité incorrecte: {row['quantity']}"

    def test_rows_sorted_by_row_no(self, extracted_rows):
        """Les lignes doivent être dans l'ordre Row No du document source."""
        row_nos = sorted(extracted_rows.keys())
        assert row_nos == list(range(1, 29)), f"Ordre incorrect : {row_nos}"

    def test_result_contains_structured_lines(self):
        """Le résultat de _extract_offer_request_form_text() doit contenir les lignes Row N:."""
        result = _extract_offer_request_form_text(_SHEPPEE_PDF)
        assert 'Row 1:' in result
        assert 'Row 28:' in result
        assert 'HST-117-03' in result
        assert 'MRS-0005' in result

    def test_result_also_contains_plain_text(self):
        """Le résultat doit conserver le texte brut (pour le matching client)."""
        result = _extract_offer_request_form_text(_SHEPPEE_PDF)
        # Le texte brut contient l'en-tête du formulaire
        assert 'Marmara Cam' in result or 'OFFER REQUEST' in result
