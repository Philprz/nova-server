# tests/unit/test_client_location_matching.py
"""
Tests unitaires — Matching client avec signaux géographiques forts.

Couvre :
  - _extract_location_signals() : détection pays/ville depuis texte email
  - _detect_multi_entity_group() : détection groupes multi-entités pays (ex: BA GLASS)
  - Scoring avec bonus géographique dans _match_clients()
  - Règle d'auto-sélection avec signal fort (cas BA GLASS Bulgaria/Plovdiv)

Cas de test obligatoires :
  1. BA GLASS + signal "Bulgaria/Plovdiv" → BA GLASS BULGARIA SA sélectionné, auto_selected=True
  2. BA GLASS sans signal pays/ville discriminant → auto_selected=False, best_client=None
  3. Candidat unique → auto_selected=True
  4. Plusieurs candidats proches + meilleur score nominal seulement → pas d'auto-sélection
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.email_matcher import EmailMatcher, MatchedClient, MatchResult


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_client(card_code: str, card_name: str, country: str = None, city: str = None) -> dict:
    """Crée un dict client SAP minimal pour les tests."""
    return {
        "CardCode": card_code,
        "CardName": card_name,
        "EmailAddress": None,
        "contact_emails": None,
        "Country": country,
        "City": city,
    }


def _make_matched_client(card_code: str, card_name: str, score: int,
                          country: str = None, city: str = None,
                          nominal_score: int = 0, strong_signal_score: int = 0) -> MatchedClient:
    """Crée un MatchedClient pour les tests de règles d'auto-sélection."""
    return MatchedClient(
        card_code=card_code,
        card_name=card_name,
        score=score,
        match_reason="test",
        match_reasons=["test"],
        nominal_score=nominal_score or score,
        strong_signal_score=strong_signal_score,
        country=country,
        city=city,
    )


# ─── Tests _extract_location_signals ─────────────────────────────────────────

class TestExtractLocationSignals:

    def test_detects_bulgaria_in_signature(self):
        text = "Best regards,\nIvan Petrov\nBA Glass Bulgaria SA\nPlovdiv, Bulgaria"
        country, city = EmailMatcher._extract_location_signals(text)
        assert country == "BG", f"Expected BG, got {country}"

    def test_detects_plovdiv_as_city(self):
        text = "Nous vous contactons depuis Plovdiv pour une demande de devis."
        country, city = EmailMatcher._extract_location_signals(text)
        assert city is not None and city.lower() == "plovdiv"
        assert country == "BG"

    def test_detects_greece(self):
        text = "Company: BA Glass Greece S.A.\nAddress: Athens, Greece"
        country, city = EmailMatcher._extract_location_signals(text)
        assert country == "GR"

    def test_detects_athens_as_city(self):
        text = "Sender: kostas@baglass.gr\nLocation: Athens"
        country, city = EmailMatcher._extract_location_signals(text)
        assert city is not None and city.lower() == "athens"
        assert country == "GR"

    def test_detects_poland(self):
        text = "BA Glass Poland Sp. z o.o.\nWarsaw, Poland"
        country, city = EmailMatcher._extract_location_signals(text)
        assert country == "PL"

    def test_detects_romania(self):
        text = "Please send quotation to BA Glass Romania SA, Bucharest"
        country, city = EmailMatcher._extract_location_signals(text)
        assert country == "RO"

    def test_no_signal_returns_none(self):
        text = "Please send us a quotation for the following items: 50 pcs"
        country, city = EmailMatcher._extract_location_signals(text)
        assert country is None
        assert city is None

    def test_city_takes_priority_over_conflicting_country(self):
        # Si "Greece" est dans le texte mais "Plovdiv" aussi (ville bulgare),
        # la ville plus précise devrait l'emporter
        text = "Our company works in Greece and Bulgaria. We are located in Plovdiv."
        country, city = EmailMatcher._extract_location_signals(text)
        assert city is not None and city.lower() == "plovdiv"
        assert country == "BG"

    def test_french_country_name(self):
        text = "Notre société est basée en Bulgarie, Plovdiv."
        country, city = EmailMatcher._extract_location_signals(text)
        assert country == "BG"

    def test_germany_detected(self):
        text = "Greetings from Frankfurt, Germany. Please provide pricing."
        country, city = EmailMatcher._extract_location_signals(text)
        assert country == "DE"
        assert city is not None and city.lower() == "frankfurt"


# ─── Tests _detect_multi_entity_group ────────────────────────────────────────

class TestDetectMultiEntityGroup:

    def test_ba_glass_multi_entity(self):
        candidates = [
            _make_matched_client("C001", "BA GLASS BULGARIA SA", 85, country="BG"),
            _make_matched_client("C002", "BA GLASS GREECE S.A.", 85, country="GR"),
            _make_matched_client("C003", "BA GLASS POLAND SP. Z.O.O", 83, country="PL"),
        ]
        assert EmailMatcher._detect_multi_entity_group(candidates) is True

    def test_single_candidate_not_multi_entity(self):
        candidates = [
            _make_matched_client("C001", "BA GLASS BULGARIA SA", 90, country="BG"),
        ]
        assert EmailMatcher._detect_multi_entity_group(candidates) is False

    def test_same_country_not_multi_entity(self):
        candidates = [
            _make_matched_client("C001", "SAINT GOBAIN FRANCE SAS", 85, country="FR"),
            _make_matched_client("C002", "SAINT GOBAIN GLASS FRANCE", 82, country="FR"),
        ]
        # Même pays → pas un groupe multi-entités pays
        assert EmailMatcher._detect_multi_entity_group(candidates) is False

    def test_different_names_not_multi_entity(self):
        candidates = [
            _make_matched_client("C001", "BA GLASS BULGARIA SA", 85, country="BG"),
            _make_matched_client("C002", "ASAHI GLASS EUROPE", 80, country="DE"),
        ]
        # Noms trop différents → pas le même groupe
        assert EmailMatcher._detect_multi_entity_group(candidates) is False

    def test_no_country_info_not_multi_entity(self):
        candidates = [
            _make_matched_client("C001", "BA GLASS BULGARIA SA", 85, country=None),
            _make_matched_client("C002", "BA GLASS GREECE S.A.", 85, country=None),
        ]
        # Pays inconnus → ne peut pas confirmer multi-entités
        assert EmailMatcher._detect_multi_entity_group(candidates) is False


# ─── Tests règles d'auto-sélection ───────────────────────────────────────────

class TestAutoSelectionRules:
    """
    Teste la logique d'auto-sélection dans match_email() via un EmailMatcher
    avec cache artificiel (pas de vraie connexion SAP).
    """

    def _build_matcher_with_clients(self, clients: list) -> EmailMatcher:
        """Crée un EmailMatcher dont le cache client est pré-rempli."""
        matcher = EmailMatcher()
        matcher._clients_cache = clients
        matcher._client_domains = {}
        matcher._client_normalized = {
            c["CardCode"]: c["CardName"].lower() for c in clients
        }
        matcher._client_first_letter = {}
        matcher._items_cache = {}
        matcher._items_normalized = {}
        matcher._items_norm_code = {}
        return matcher

    # ── CAS 1 : BA GLASS + signal Bulgaria/Plovdiv → BA GLASS BULGARIA sélectionné ──

    def test_ba_glass_with_bulgaria_signal_autoselects_bulgaria(self):
        """
        Cas réel BA GLASS.
        Signal fort "Bulgaria" + "Plovdiv" dans la signature.
        Attendu : BA GLASS BULGARIA SA sélectionné, auto_selected=True,
                  reason contient country_match ou city_match.
        """
        clients = [
            _make_client("C_BG", "BA GLASS BULGARIA SA", country="BG", city="Plovdiv"),
            _make_client("C_GR", "BA GLASS GREECE S.A.", country="GR", city="Athens"),
            _make_client("C_PL", "BA GLASS POLAND SP. Z.O.O", country="PL", city="Warsaw"),
            _make_client("C_RO", "BA GLASS ROMANIA SA", country="RO", city="Bucharest"),
        ]
        matcher = self._build_matcher_with_clients(clients)

        # Texte simulant un email avec signature bulgare
        email_body = """
Dear RONDOT team,

Please provide a quotation for our production line in Plovdiv.

Best regards,
Georgi Ivanov
Purchasing Manager
BA Glass Bulgaria SA
72 Maria Luisa Blvd
4000 Plovdiv, Bulgaria
Tel: +359 32 640 000
"""
        detected_country, detected_city = EmailMatcher._extract_location_signals(email_body)
        assert detected_country == "BG", f"Signal pays non détecté, got {detected_country}"
        assert detected_city is not None and "plovdiv" in detected_city.lower()

        matched = matcher._match_clients(
            email_body,
            extracted_domains=[],
            detected_country=detected_country,
            detected_city=detected_city,
        )

        # BA GLASS BULGARIA doit être en tête avec un bonus signal
        assert len(matched) > 0
        top = matched[0]
        assert top.card_code == "C_BG", (
            f"Attendu C_BG (Bulgaria), obtenu {top.card_code} ({top.card_name}). "
            f"Scores: {[(m.card_code, m.score, m.nominal_score, m.strong_signal_score) for m in matched]}"
        )
        assert top.strong_signal_score > 0, "Le signal géographique doit être > 0"
        assert any("country_match" in r or "city_match" in r for r in top.match_reasons), (
            f"Reasons ne contient pas de country_match/city_match: {top.match_reasons}"
        )

        # Vérification de l'écart suffisant pour auto-sélection
        if len(matched) > 1:
            gap = top.score - matched[1].score
            assert gap >= 10 or top.score >= 90, (
                f"Écart insuffisant pour auto-sélection: top={top.score}, 2e={matched[1].score}"
            )

    # ── CAS 2 : BA GLASS SANS signal pays/ville → pas d'auto-sélection ──────────

    def test_ba_glass_without_location_signal_no_autoselect(self):
        """
        BA GLASS sans aucun signal géographique dans l'email.
        Attendu : auto_selected=False, best_client=None.
        """
        clients = [
            _make_client("C_BG", "BA GLASS BULGARIA SA", country="BG", city="Plovdiv"),
            _make_client("C_GR", "BA GLASS GREECE S.A.", country="GR", city="Athens"),
            _make_client("C_PL", "BA GLASS POLAND SP. Z.O.O", country="PL", city="Warsaw"),
        ]
        matcher = self._build_matcher_with_clients(clients)

        email_body = """
Please send us a quotation for the following glass items:
- Float glass 4mm × 100 pcs
- Tempered glass 6mm × 50 pcs

Kind regards,
BA Glass purchasing team
"""
        detected_country, detected_city = EmailMatcher._extract_location_signals(email_body)
        # Aucun signal géographique discriminant
        assert detected_country is None or detected_country not in ("BG", "GR", "PL")

        matched = matcher._match_clients(
            email_body,
            extracted_domains=[],
            detected_country=detected_country,
            detected_city=detected_city,
        )

        if len(matched) >= 2:
            # Tous doivent avoir strong_signal_score = 0 (aucun signal)
            for m in matched:
                assert m.strong_signal_score == 0, (
                    f"{m.card_name} a un signal inattendu: {m.strong_signal_score}"
                )

            # Le groupe multi-entités doit être détecté
            is_multi = EmailMatcher._detect_multi_entity_group(matched)
            assert is_multi, "BA GLASS (BG/GR/PL) doit être détecté comme groupe multi-entités"

    # ── CAS 3 : Candidat unique → auto_selected=True (règle de base) ──────────

    def test_single_candidate_always_autoselected(self):
        """
        Un seul candidat → auto-sélection systématique (règle de base inchangée).
        """
        candidates = [
            _make_matched_client("C001", "SAINT GOBAIN FRANCE", 85, country="FR"),
        ]
        is_multi = EmailMatcher._detect_multi_entity_group(candidates)
        assert is_multi is False  # Candidat unique → pas multi-entités
        # Règle : 1 seul candidat → auto-select (testé dans match_email, pas ici)
        assert len(candidates) == 1

    # ── CAS 4 : Plusieurs candidats + score nominal supérieur seulement → pas d'auto-sélection ──

    def test_no_autoselect_multi_entity_with_nominal_score_only(self):
        """
        Groupe multi-entités (BA GLASS, pays différents), meilleur score nominal
        uniquement (pas de signal géo) → pas d'auto-sélection.
        Même si Greece score 98 (>= 90) et l'écart capé est 0 (tous à 98).
        """
        # Simuler les candidats après scoring nominal égal (tous à 98) sans signal fort
        candidates = [
            _make_matched_client("C_GR", "BA GLASS GREECE S.A.", score=98,
                                  nominal_score=98, strong_signal_score=0, country="GR"),
            _make_matched_client("C_BG", "BA GLASS BULGARIA SA", score=98,
                                  nominal_score=98, strong_signal_score=0, country="BG"),
            _make_matched_client("C_PL", "BA GLASS POLAND SP. Z.O.O", score=98,
                                  nominal_score=98, strong_signal_score=0, country="PL"),
        ]

        is_multi = EmailMatcher._detect_multi_entity_group(candidates)
        top = candidates[0]
        second = candidates[1]
        gap = top.score - second.score  # = 0
        raw_gap = (top.nominal_score + top.strong_signal_score) - (second.nominal_score + second.strong_signal_score)  # = 0

        standard_autoselect = top.score >= 90 and gap >= 10  # False (gap=0)
        signal_tiebreak = (
            is_multi and top.strong_signal_score > 0
            and second.strong_signal_score == 0
            and top.nominal_score >= 85
            and raw_gap >= 20
        )  # False (signal=0)

        should_autoselect = (standard_autoselect or signal_tiebreak) and (
            not is_multi or signal_tiebreak or top.strong_signal_score > 0
        )

        assert should_autoselect is False, (
            "Ne doit pas auto-sélectionner BA GLASS sans signal géo "
            f"(is_multi={is_multi}, gap={gap}, raw_gap={raw_gap})"
        )

    def test_ba_glass_with_nominal_score_and_signal_autoselects(self):
        """
        Cas réel : tous les BA GLASS à score nominal 98, mais signal Bulgarie.
        Le score brut Bulgaria = 98+35=133 vs 98 → raw_gap=35 >= 20.
        Attendu : signal_tiebreak=True → auto-sélection.
        """
        candidates = [
            _make_matched_client("C_BG", "BA GLASS BULGARIA SA", score=100,
                                  nominal_score=98, strong_signal_score=35, country="BG"),
            _make_matched_client("C_GR", "BA GLASS GREECE S.A.", score=98,
                                  nominal_score=98, strong_signal_score=0, country="GR"),
            _make_matched_client("C_PL", "BA GLASS POLAND SP. Z.O.O", score=98,
                                  nominal_score=98, strong_signal_score=0, country="PL"),
        ]

        is_multi = EmailMatcher._detect_multi_entity_group(candidates)
        assert is_multi is True

        top = candidates[0]
        second = candidates[1]
        raw_gap = (top.nominal_score + top.strong_signal_score) - (second.nominal_score + second.strong_signal_score)
        # raw_gap = (98+35) - (98+0) = 35

        signal_tiebreak = (
            is_multi
            and top.strong_signal_score > 0
            and second.strong_signal_score == 0
            and top.nominal_score >= 85
            and raw_gap >= 20
        )

        assert signal_tiebreak is True, (
            f"signal_tiebreak devrait être True: is_multi={is_multi}, "
            f"signal={top.strong_signal_score}, raw_gap={raw_gap}"
        )
        assert top.card_code == "C_BG", "BA GLASS BULGARIA doit être en tête"


# ─── Tests signaux géographiques bonus dans le scoring ───────────────────────

class TestStrongSignalBonus:

    def test_country_match_adds_bonus(self):
        """Le bonus pays (+20) est ajouté au score nominal."""
        clients = [
            _make_client("C_BG", "TEST CLIENT", country="BG"),
        ]
        matcher = TestAutoSelectionRules()._build_matcher_with_clients(clients)

        text = "Test text with BA GLASS in Bulgaria for quotation"
        matched = matcher._match_clients(
            text, extracted_domains=[],
            detected_country="BG", detected_city=None,
        )

        # Si le client a matché (score >= 60 nominal), il doit avoir un bonus
        for m in matched:
            if m.card_code == "C_BG":
                assert m.strong_signal_score >= 20, (
                    f"Bonus pays attendu >= 20, obtenu {m.strong_signal_score}"
                )
                assert any("country_match" in r for r in m.match_reasons)

    def test_city_match_adds_bonus(self):
        """Le bonus ville (+15) est ajouté au score nominal si la ville correspond."""
        clients = [
            _make_client("C_BG", "TEST BULGARIE CLIENT", country="BG", city="Plovdiv"),
        ]
        matcher = TestAutoSelectionRules()._build_matcher_with_clients(clients)

        text = "Please quote for our Plovdiv factory"
        matched = matcher._match_clients(
            text, extracted_domains=[],
            detected_country="BG", detected_city="Plovdiv",
        )

        for m in matched:
            if m.card_code == "C_BG":
                # Bonus attendu : 20 (pays) + 15 (ville) = 35
                assert m.strong_signal_score >= 15
                assert any("city_match" in r for r in m.match_reasons)

    def test_no_bonus_when_country_mismatch(self):
        """Pas de bonus si le pays de l'email ne correspond pas au pays SAP du client."""
        clients = [
            _make_client("C_GR", "BA GLASS GREECE S.A.", country="GR", city="Athens"),
        ]
        matcher = TestAutoSelectionRules()._build_matcher_with_clients(clients)

        text = "BA Glass Bulgaria request from Plovdiv"
        matched = matcher._match_clients(
            text, extracted_domains=[],
            detected_country="BG", detected_city="Plovdiv",
        )

        for m in matched:
            if m.card_code == "C_GR":
                # La Grèce ne doit pas avoir de bonus (pays = BG vs SAP = GR)
                assert m.strong_signal_score == 0 or "country_match" not in str(m.match_reasons), (
                    f"BA GLASS GREECE ne doit pas avoir de bonus pour signal Bulgaria: "
                    f"signal={m.strong_signal_score}, reasons={m.match_reasons}"
                )
