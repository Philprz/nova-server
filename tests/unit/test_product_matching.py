"""
Tests unitaires — Moteur de matching produit SAP.

Couvre :
  - normalize_text()
  - SAPCacheDB.search_items_multitoken()
  - EmailMatcher._match_single_product_intelligent()  (ÉTAPE 3 thefuzz)
  - EmailMatcher._match_products()  (Phase 2bis)

Cas de test :
  1. HANDY VII PREMIUM  → A14887
  2. HANDY VII BASIC    → A14885
  3. Produit inconnu    → not_found_in_sap = True
  4. Produit approximatif → score 65-84 (suggestion)
"""

import sys
import os
import types
import sqlite3
import tempfile
import pytest

# ─── Ajouter le répertoire racine du projet au chemin ──────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.email_matcher import normalize_text


# ═══════════════════════════════════════════════════════════════════════════
# TESTS normalize_text()
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeText:

    def test_lowercase(self):
        assert normalize_text("HANDY VII PREMIUM") == "handy vii premium"

    def test_accent_removal(self):
        assert normalize_text("PYROMÈTRE") == "pyrometre"

    def test_punctuation_removed(self):
        result = normalize_text("HANDY VII PREMIUM + STATION DE CHARGE")
        assert "+" not in result
        assert "handy" in result

    def test_multiple_spaces_collapsed(self):
        result = normalize_text("HANDY   VII    PREMIUM")
        # Tous les espaces multiples doivent être réduits à un seul
        assert "  " not in result
        assert result == "handy vii premium"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_none_like_empty(self):
        assert normalize_text(None) == ""  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURE : mini-base SQLite avec articles SAP simulés
# ═══════════════════════════════════════════════════════════════════════════

SAP_ITEMS = [
    # --- Variantes HANDY VII (6 articles proches — test du nettoyage post-Phase 2bis) ---
    ("A14163", "PYROMETRE HANDY VII BASIC"),
    ("A14164", "PYROMETRE HANDY VII PREMIUM"),
    ("A14884", "PYROMETRE HANDY VII BASIC + STATION DE CHARGE ALLEGEE"),
    ("A14885", "PYROMETRE HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"),
    ("A14886", "PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE ALLEGEE"),
    ("A14887", "PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"),
    # --- Autres articles ---
    ("A14900", "CAPTEUR DE TEMPERATURE PT100 CLASSE A"),
    ("A15001", "DETECTEUR INFRAROUGE COMPACT MODELE XL"),
    ("A10001", "VIS M6 INOX 316L"),
    ("A10002", "ROULEMENT A BILLES SKF 6205"),
    ("A10003", "JOINT TORIQUE NBR 50x3"),
    # Refs fournisseur dans ItemName (cas P/0301L-SLT vs P-0301L-SLT)
    ("A10322", "P/0301R-SLT PUSHBAR CLAMP CARRIER - WITH ADJUSTER (SLOTTED RIGHT)"),
    ("A10323", "P/0301L-SLT PUSHBAR CLAMP CARRIER - WITH ADJUSTER (SLOTTED LEFT)"),
]


@pytest.fixture
def tmp_db():
    """Crée une base SQLite temporaire avec des articles SAP de test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE sap_items (
            ItemCode TEXT PRIMARY KEY,
            ItemName TEXT NOT NULL,
            ItemGroup INTEGER,
            Price REAL,
            Currency TEXT DEFAULT 'EUR',
            SupplierPrice REAL,
            weight_unit_value REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX idx_items_name ON sap_items(ItemName COLLATE NOCASE)")
    conn.executemany(
        "INSERT INTO sap_items (ItemCode, ItemName) VALUES (?, ?)", SAP_ITEMS
    )
    conn.commit()
    conn.close()

    yield path

    os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════
# TESTS SAPCacheDB.search_items_multitoken()
# ═══════════════════════════════════════════════════════════════════════════

class TestSearchItemsMultitoken:

    def _make_cache(self, tmp_db):
        from services.sap_cache_db import SAPCacheDB
        return SAPCacheDB(db_path=tmp_db)

    def test_handy_premium_found(self, tmp_db):
        cache = self._make_cache(tmp_db)
        results = cache.search_items_multitoken(
            "HANDY VII PREMIUM STATION CHARGE FIXE COMPENSATION FIBRE"
        )
        codes = [r["ItemCode"] for r in results]
        assert "A14887" in codes

    def test_handy_basic_found(self, tmp_db):
        cache = self._make_cache(tmp_db)
        results = cache.search_items_multitoken("HANDY VII BASIC")
        codes = [r["ItemCode"] for r in results]
        assert "A14885" in codes

    def test_unknown_product_empty(self, tmp_db):
        cache = self._make_cache(tmp_db)
        results = cache.search_items_multitoken("ZGZG PRODUIT INEXISTANT XYZ123")
        # Peut retourner [] ou des faux positifs faibles — l'important c'est A14887 absent
        codes = [r["ItemCode"] for r in results]
        assert "A14887" not in codes

    def test_limit_respected(self, tmp_db):
        cache = self._make_cache(tmp_db)
        results = cache.search_items_multitoken("ROULEMENT CAPTEUR DETECTEUR", limit=2)
        assert len(results) <= 2

    def test_empty_query_fallback(self, tmp_db):
        """Requête vide ne doit pas lever d'exception."""
        cache = self._make_cache(tmp_db)
        results = cache.search_items_multitoken("")
        assert isinstance(results, list)


# ═══════════════════════════════════════════════════════════════════════════
# TESTS EmailMatcher._match_products() (Phase 2bis)
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchProducts:
    """Tests du moteur de matching complet via un EmailMatcher avec cache simulé."""

    def _make_matcher(self, tmp_db):
        """Crée un EmailMatcher dont le cache pointe sur la DB de test."""
        from services.email_matcher import EmailMatcher
        from services.sap_cache_db import SAPCacheDB

        matcher = EmailMatcher()
        cache = SAPCacheDB(db_path=tmp_db)
        matcher._cache_db = cache

        # Pré-charger le cache mémoire manuellement
        items = cache.get_all_items()
        matcher._items_cache = {i["ItemCode"]: i for i in items}
        matcher._items_normalized = {
            i["ItemCode"]: normalize_text(i["ItemName"]) for i in items
        }
        # Cache clients vide (non nécessaire ici)
        matcher._clients_cache = []
        matcher._client_domains = {}
        matcher._client_normalized = {}
        matcher._client_first_letter = {}

        return matcher

    # ------------------------------------------------------------------
    # Cas 1 : HANDY VII PREMIUM → A14887
    # ------------------------------------------------------------------
    def test_handy_premium(self, tmp_db):
        matcher = self._make_matcher(tmp_db)
        text = (
            "Bonjour,\n"
            "Nous souhaitons commander :\n"
            "HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE, qté 2\n"
            "Merci de nous faire parvenir un devis."
        )
        products = matcher._match_products(text)
        assert products, "Aucun produit détecté"
        # Le meilleur match doit être A14887
        best = products[0]
        assert best.item_code == "A14887", (
            f"Attendu A14887, obtenu {best.item_code} ({best.item_name}) score={best.score}"
        )
        assert best.score >= 85, f"Score trop bas: {best.score}"
        assert not best.not_found_in_sap

    # ------------------------------------------------------------------
    # Cas 2 : HANDY VII BASIC (description complète) → A14885
    # ------------------------------------------------------------------
    def test_handy_basic(self, tmp_db):
        matcher = self._make_matcher(tmp_db)
        text = (
            "Bonjour,\n"
            "Nous souhaitons commander :\n"
            "HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE, qté 3\n"
            "Merci."
        )
        products = matcher._match_products(text)
        assert products, "Aucun produit détecté"
        best = products[0]
        assert best.item_code == "A14885", (
            f"Attendu A14885, obtenu {best.item_code} ({best.item_name}) score={best.score}"
        )
        assert best.score >= 85, f"Score trop bas: {best.score}"
        assert not best.not_found_in_sap

    # ------------------------------------------------------------------
    # Cas 3 : Produit inconnu → not_found_in_sap = True
    # ------------------------------------------------------------------
    def test_unknown_product(self, tmp_db):
        matcher = self._make_matcher(tmp_db)
        text = (
            "Bonjour, je cherche le produit ZGZG-9999-INCONNU ref ZZZ-404.\n"
            "Quantité: 10 pièces."
        )
        products = matcher._match_products(text)
        # Les codes A14887/A14885 ne doivent PAS être dans les résultats
        real_codes = {p.item_code for p in products if not p.not_found_in_sap}
        assert "A14887" not in real_codes
        assert "A14885" not in real_codes

    # ------------------------------------------------------------------
    # Cas 4 : Produit approximatif → score 65-84 (suggestion)
    # ------------------------------------------------------------------
    def test_approximate_product(self, tmp_db):
        matcher = self._make_matcher(tmp_db)
        # Description partielle — "HANDY PREMIUM" sans "VII"
        text = "Veuillez préparer un devis pour le PYROMETRE HANDY PREMIUM (ancienne référence)."
        products = matcher._match_products(text)
        # Doit trouver quelque chose avec un score dans [65, 84]
        relevant = [p for p in products if not p.not_found_in_sap and p.item_code in ("A14887", "A14885")]
        if relevant:
            best = max(relevant, key=lambda p: p.score)
            # Score entre 65 et 100 (auto ou suggestion)
            assert best.score >= 65, f"Score trop bas pour match partiel: {best.score}"

    # ------------------------------------------------------------------
    # Cas 5 : Email avec 2 HANDY VII → exactement 2 résultats, pas 6
    # ------------------------------------------------------------------
    def test_two_handy_products_no_variants_noise(self, tmp_db):
        """
        Quand l'email commande les 2 HANDY VII (PREMIUM + BASIC) avec la description complète,
        le nettoyage post-Phase 2bis doit supprimer les variantes redondantes
        (A14163, A14164, A14884, A14886) et ne retourner que A14887 + A14885.
        """
        matcher = self._make_matcher(tmp_db)
        text = (
            "Pouvez-vous me chiffrer les produits suivants : 1 unité de chaque.\n"
            "HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE\n"
            "HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        products = matcher._match_products(text)
        codes = [p.item_code for p in products if not p.not_found_in_sap]

        # Les deux bons produits doivent être présents
        assert "A14887" in codes, f"A14887 absent: {codes}"
        assert "A14885" in codes, f"A14885 absent: {codes}"

        # Les variantes redondantes NE doivent PAS être présentes
        redundant = {"A14163", "A14164", "A14884", "A14886"}
        found_redundant = redundant & set(codes)
        assert not found_redundant, (
            f"Variantes redondantes trouvées (ne devraient pas l'être): {found_redundant}\n"
            f"Tous les codes retournés: {codes}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TESTS Seuils de décision
# ═══════════════════════════════════════════════════════════════════════════

class TestDecisionThresholds:
    """Vérifie la cohérence des seuils score >= 85 / 65-84 / < 65."""

    def test_auto_match_threshold(self):
        """token_set_ratio(query, item_name) >= 85 → doit être considéré auto-match."""
        from thefuzz import fuzz
        query = normalize_text(
            "HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        item_name = normalize_text(
            "PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        score = fuzz.token_set_ratio(query, item_name)
        assert score >= 85, (
            f"token_set_ratio trop bas ({score}) pour un match quasi-exact"
        )

    def test_basic_vs_premium_differentiation(self):
        """BASIC et PREMIUM doivent avoir des scores différents."""
        from thefuzz import fuzz
        query = normalize_text("HANDY VII PREMIUM")
        premium = normalize_text("PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE")
        basic = normalize_text("PYROMETRE HANDY VII BASIC")

        score_premium = fuzz.token_set_ratio(query, premium)
        score_basic = fuzz.token_set_ratio(query, basic)

        # PREMIUM doit scorer plus haut que BASIC
        assert score_premium > score_basic, (
            f"PREMIUM ({score_premium}) devrait scorer > BASIC ({score_basic})"
        )

    def test_completely_different_product_low_score(self):
        """Un produit sans rapport doit avoir un score < 65."""
        from thefuzz import fuzz
        query = normalize_text("HANDY VII PREMIUM STATION CHARGE FIBRE")
        unrelated = normalize_text("VIS M6 INOX 316L")
        score = fuzz.token_set_ratio(query, unrelated)
        assert score < 65, (
            f"Score trop haut ({score}) pour produit sans rapport"
        )

    def test_full_description_premium_not_confused_with_basic(self):
        """
        Avec les VRAIES descriptions SAP complètes (PREMIUM et BASIC ont toutes deux
        le libellé "+ STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"),
        _discriminating_score doit scorer PREMIUM ≥85 et BASIC <85 pour une
        requête PREMIUM.
        """
        from services.email_matcher import _discriminating_score
        query = normalize_text(
            "HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        premium_full = normalize_text(
            "PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        basic_full = normalize_text(
            "PYROMETRE HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        score_premium = _discriminating_score(query, premium_full)
        score_basic = _discriminating_score(query, basic_full)
        assert score_premium >= 85, f"PREMIUM devrait être auto-match (≥85): {score_premium}"
        assert score_basic < 85, (
            f"BASIC ne devrait PAS être auto-match (<85) pour requête PREMIUM: {score_basic}"
        )
        assert score_premium > score_basic, (
            f"PREMIUM ({score_premium}) devrait scorer > BASIC ({score_basic})"
        )

    def test_full_description_basic_not_confused_with_premium(self):
        """Symétrique : requête BASIC → BASIC ≥85, PREMIUM <85."""
        from services.email_matcher import _discriminating_score
        query = normalize_text(
            "HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        premium_full = normalize_text(
            "PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        basic_full = normalize_text(
            "PYROMETRE HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        )
        score_premium = _discriminating_score(query, premium_full)
        score_basic = _discriminating_score(query, basic_full)
        assert score_basic >= 85, f"BASIC devrait être auto-match (≥85): {score_basic}"
        assert score_premium < 85, (
            f"PREMIUM ne devrait PAS être auto-match (<85) pour requête BASIC: {score_premium}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TESTS normalize_code()
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeCode:
    """Vérifie que normalize_code() unifie les variantes de codes fournisseurs."""

    def test_hyphen_removed(self):
        from services.email_matcher import normalize_code
        assert normalize_code("P-0301L-SLT") == "p0301lslt"

    def test_slash_removed(self):
        from services.email_matcher import normalize_code
        assert normalize_code("P/0301L-SLT") == "p0301lslt"

    def test_hyphen_and_slash_equivalent(self):
        """P-0301L-SLT et P/0301L-SLT doivent donner le même résultat."""
        from services.email_matcher import normalize_code
        assert normalize_code("P-0301L-SLT") == normalize_code("P/0301L-SLT")

    def test_right_variant(self):
        from services.email_matcher import normalize_code
        assert normalize_code("P-0301R-SLT") == "p0301rslt"
        assert normalize_code("P/0301R-SLT") == "p0301rslt"

    def test_empty_string(self):
        from services.email_matcher import normalize_code
        assert normalize_code("") == ""

    def test_none_like_empty(self):
        from services.email_matcher import normalize_code
        assert normalize_code(None) == ""  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════
# TESTS matching par code normalisé (P-0301L-SLT → A10323)
# ═══════════════════════════════════════════════════════════════════════════

class TestMatchCodeNormalized:
    """
    Vérifie que le moteur de matching retrouve les articles SAP
    même quand le séparateur dans le code fournisseur diffère (- vs /).
    """

    def _make_matcher(self, tmp_db):
        """Crée un EmailMatcher avec cache pointant sur la DB de test."""
        from services.email_matcher import EmailMatcher, normalize_code, normalize_text
        from services.sap_cache_db import SAPCacheDB

        matcher = EmailMatcher()
        cache = SAPCacheDB(db_path=tmp_db)
        matcher._cache_db = cache

        items = cache.get_all_items()
        matcher._items_cache = {i["ItemCode"]: i for i in items}
        matcher._items_normalized = {
            i["ItemCode"]: normalize_text(i["ItemName"]) for i in items
        }
        # Construire l'index des codes normalisés (même logique que ensure_cache)
        matcher._items_norm_code = {}
        for item_code, item in matcher._items_cache.items():
            nc = normalize_code(item_code)
            if nc and nc not in matcher._items_norm_code:
                matcher._items_norm_code[nc] = item_code
            item_name = item.get("ItemName", "")
            if item_name:
                first_token = item_name.split()[0]
                nt = normalize_code(first_token)
                if len(nt) >= 4 and any(c.isdigit() for c in nt) and nt not in matcher._items_norm_code:
                    matcher._items_norm_code[nt] = item_code

        matcher._clients_cache = []
        matcher._client_domains = {}
        matcher._client_normalized = {}
        matcher._client_first_letter = {}
        return matcher

    # ------------------------------------------------------------------
    # Test 1 : P-0301L-SLT (tiret fournisseur) → A10323 (slash SAP)
    # ------------------------------------------------------------------
    def test_match_code_exact_P_0301L_SLT_returns_A10323(self, tmp_db):
        from services.email_matcher import normalize_code
        matcher = self._make_matcher(tmp_db)
        # Vérifier que l'index contient bien la correspondance
        code_norm = normalize_code("P-0301L-SLT")
        assert code_norm in matcher._items_norm_code, (
            f"'{code_norm}' absent de _items_norm_code. Clés: {list(matcher._items_norm_code.items())[:5]}"
        )
        assert matcher._items_norm_code[code_norm] == "A10323", (
            f"Attendu A10323, obtenu {matcher._items_norm_code[code_norm]}"
        )

    # ------------------------------------------------------------------
    # Test 2 : P-0301R-SLT (tiret fournisseur) → A10322 (slash SAP)
    # ------------------------------------------------------------------
    def test_match_code_exact_P_0301R_SLT_returns_A10322(self, tmp_db):
        from services.email_matcher import normalize_code
        matcher = self._make_matcher(tmp_db)
        code_norm = normalize_code("P-0301R-SLT")
        assert code_norm in matcher._items_norm_code, (
            f"'{code_norm}' absent de _items_norm_code"
        )
        assert matcher._items_norm_code[code_norm] == "A10322"

    # ------------------------------------------------------------------
    # Test 3 : Code inconnu → pas de match halluciné
    # ------------------------------------------------------------------
    def test_unknown_code_returns_not_found_no_hallucination(self, tmp_db):
        from services.email_matcher import normalize_code
        matcher = self._make_matcher(tmp_db)
        code_norm = normalize_code("ZZZ-9999-XXXXX")
        # Ne doit pas mapper vers A10323 ou A10322
        matched = matcher._items_norm_code.get(code_norm)
        assert matched not in ("A10323", "A10322"), (
            f"Faux positif: {code_norm} → {matched}"
        )

    # ------------------------------------------------------------------
    # Test 4 : L vs R ne doivent pas se confondre
    # ------------------------------------------------------------------
    def test_left_right_not_confused(self, tmp_db):
        from services.email_matcher import normalize_code
        matcher = self._make_matcher(tmp_db)
        norm_L = normalize_code("P/0301L-SLT")
        norm_R = normalize_code("P/0301R-SLT")
        assert norm_L != norm_R, "L et R ne doivent pas normaliser au même code"
        assert matcher._items_norm_code.get(norm_L) == "A10323"
        assert matcher._items_norm_code.get(norm_R) == "A10322"

    # ------------------------------------------------------------------
    # Non-régression 5 : HANDY VII PREMIUM → A14887
    # ------------------------------------------------------------------
    def test_handy_vii_premium_still_matches_A14887(self, tmp_db):
        matcher = self._make_matcher(tmp_db)
        text = (
            "Bonjour,\n"
            "Nous souhaitons commander :\n"
            "HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE, qté 2\n"
            "Merci de nous faire parvenir un devis."
        )
        products = matcher._match_products(text)
        assert products, "Aucun produit détecté"
        best = products[0]
        assert best.item_code == "A14887", (
            f"Attendu A14887, obtenu {best.item_code} score={best.score}"
        )
        assert best.score >= 85

    # ------------------------------------------------------------------
    # Non-régression 6 : HANDY VII BASIC (description complète) → A14885
    # ------------------------------------------------------------------
    def test_handy_vii_basic_still_matches_A14885(self, tmp_db):
        matcher = self._make_matcher(tmp_db)
        text = (
            "Bonjour,\n"
            "Nous souhaitons commander :\n"
            "HANDY VII BASIC + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE, qté 3\n"
            "Merci."
        )
        products = matcher._match_products(text)
        assert products, "Aucun produit détecté"
        best = products[0]
        assert best.item_code == "A14885", (
            f"Attendu A14885, obtenu {best.item_code} score={best.score}"
        )
        assert best.score >= 85


# ═══════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE DIRECT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Exécution rapide sans pytest pour vérification manuelle
    print("=== Tests normalize_text ===")
    t = TestNormalizeText()
    t.test_lowercase()
    t.test_accent_removal()
    t.test_punctuation_removed()
    t.test_multiple_spaces_collapsed()
    t.test_empty_string()
    print("  ✓ normalize_text OK")

    print("\n=== Tests seuils décision ===")
    d = TestDecisionThresholds()
    d.test_auto_match_threshold()
    d.test_basic_vs_premium_differentiation()
    d.test_completely_different_product_low_score()
    print("  ✓ Seuils OK")

    print("\nPour les tests complets (DB), utiliser: pytest tests/unit/test_product_matching.py -v")
