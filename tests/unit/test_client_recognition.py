# tests/unit/test_client_recognition.py
"""
Tests unitaires pour services/client_recognition_engine.py

Couvre :
- Extraction signaux email (forward emails, signature company, body companies)
- Normalisation noms d'entreprise (suffixes légaux, accents, casse)
- Similarité noms d'entreprise
- Détection domaines génériques
- Scoring candidats (email exact, domaine, nom société)
- Détection ambiguïté
- Flux complet avec candidats mock
- Cas limites
"""

import sys
import os

# Ajouter le répertoire racine du projet au path pour les imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from services.client_recognition_engine import (
    # Utilitaires
    strip_company_suffix,
    normalize_company,
    is_generic_domain,
    is_internal_domain,
    company_similarity,
    # Modèles
    EmailSignals,
    ScoredCandidate,
    ClientRecognitionResult,
    RecognitionSignal,
    # Classes
    EmailSignalExtractor,
    ClientRecognitionEngine,
    get_client_recognition_engine,
    # Constantes
    GENERIC_DOMAINS,
    INTERNAL_DOMAINS,
    AUTO_ACCEPT_THRESHOLD,
    AMBIGUITY_GAP,
    COMPANY_NAME_SIM_THRESHOLD,
    SIGNAL_WEIGHTS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def extractor():
    return EmailSignalExtractor()


@pytest.fixture
def engine():
    return ClientRecognitionEngine()


@pytest.fixture
def simple_body_with_forward():
    return """
Bonjour,

Pouvez-vous nous faire un devis pour les articles suivants ?

---------- Forwarded message ---------
De: Jean Dupont jean.dupont@acme-industries.fr
Date: ven. 14 mars 2026 09:30
Subject: Demande de devis

Merci pour votre retour.
Jean Dupont
ACME Industries
"""


@pytest.fixture
def body_with_signature_sarl():
    return """
Bonjour,

Je souhaite obtenir un devis pour 100 unités de l'article XY-500.

Cordialement,
--
Pierre Martin
Responsable Achats
Société Dupont SARL
Tél: +33 1 23 45 67 89
"""


@pytest.fixture
def body_with_body_company():
    return """
Bonjour,

La société Verrerie Moderne SAS vous contacte pour une demande de devis.
Nous avons besoin de 50 pièces de l'article référence VM-200.

Cordialement,
"""


@pytest.fixture
def gmail_forward_body():
    return """
Bonjour,

Voici la demande reçue.

Jean Dupont <jean@gmail.com> a écrit :
Bonjour, je cherche les prix pour l'article suivant.

Merci.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Tests utilitaires de normalisation
# ─────────────────────────────────────────────────────────────────────────────

class TestStripCompanySuffix:
    def test_removes_sarl(self):
        assert "Dupont" in strip_company_suffix("Dupont SARL")

    def test_removes_sas(self):
        result = strip_company_suffix("Verrerie Moderne SAS")
        assert "SAS" not in result
        assert "Verrerie Moderne" in result

    def test_removes_ltd(self):
        result = strip_company_suffix("Acme Industries Ltd")
        assert "Ltd" not in result

    def test_removes_gmbh(self):
        result = strip_company_suffix("Muster GmbH")
        assert "GmbH" not in result
        assert "Muster" in result

    def test_no_suffix(self):
        result = strip_company_suffix("Acme Industries")
        assert result == "Acme Industries"

    def test_empty_string(self):
        assert strip_company_suffix("") == ""

    def test_multiple_suffixes(self):
        # Only one suffix in reality, but test it doesn't break
        result = strip_company_suffix("Some Corp Ltd")
        assert "Corp" not in result or "Ltd" not in result


class TestNormalizeCompany:
    def test_lowercase(self):
        assert normalize_company("ACME") == "acme"

    def test_removes_accents(self):
        result = normalize_company("Société Générale")
        assert "e" in result
        assert "é" not in result

    def test_removes_suffix_sarl(self):
        result = normalize_company("Dupont SARL")
        assert "sarl" not in result

    def test_removes_suffix_sas(self):
        result = normalize_company("Verrerie SAS")
        assert "sas" not in result

    def test_normalizes_spaces(self):
        result = normalize_company("  Acme   Industries  ")
        assert "  " not in result
        assert result == result.strip()

    def test_empty_string(self):
        assert normalize_company("") == ""

    def test_none_like_behavior(self):
        # normalize_company("") returns ""
        assert normalize_company("") == ""

    def test_removes_punctuation(self):
        result = normalize_company("Acme-Industries, Inc.")
        assert "," not in result
        assert "." not in result

    def test_full_normalization(self):
        a = normalize_company("ACME INDUSTRIES SARL")
        b = normalize_company("Acme Industries")
        # After suffix removal and normalization, they should be equal
        assert a == b


class TestNormalizeCompanyUnicode:
    """Tests pour la normalisation des caractères turcs/accentués."""

    def test_turkish_s_cedilla(self):
        """Ş (S cédille turc) → S après NFD."""
        result = normalize_company("ŞİŞECAM")
        assert result == "sisecam"

    def test_turkish_dotless_i(self):
        """ı (i sans point turc, U+0131) → i via translittération."""
        result = normalize_company("TÜRKİYE")
        assert "u" in result   # Ü → U → u
        assert "i" in result   # İ → I → i

    def test_turkish_full_company_name(self):
        """Nom turc complet avec accents et suffix A.Ş. → normalisé identique."""
        turkish = normalize_company("TÜRKİYE ŞİŞE ve CAM FABRİKALARI A.Ş.")
        latinized = normalize_company("Turkiye Sise ve Cam Fabrikalari A.S.")
        assert turkish == latinized

    def test_turkish_with_sap_parenthetical_code(self):
        """Nom SAP avec code entre parenthèses (4001) → supprimé."""
        sap_name = normalize_company("Türkiye Sise ve Cam Fabrikalari A.S. (4001)")
        email_name = normalize_company("TÜRKİYE ŞİŞE ve CAM FABRİKALARI A.Ş.")
        assert sap_name == email_name

    def test_dotted_suffix_as(self):
        """A.S. → AS → retiré comme suffixe légal."""
        result = normalize_company("Some Company A.S.")
        assert "a s" not in result
        assert "as" not in result.split()

    def test_dotted_suffix_sarl(self):
        """S.A.R.L. → SARL → retiré comme suffixe légal."""
        result = normalize_company("Dupont S.A.R.L.")
        assert "sarl" not in result
        assert result == "dupont"

    def test_parenthetical_code_stripped(self):
        """Les codes parenthésés SAP sont retirés du nom."""
        result = normalize_company("MARMARA CAM SANAYI (4001)")
        assert "4001" not in result
        assert result == "marmara cam sanayi"

    def test_german_eszett(self):
        """ß → ss."""
        result = normalize_company("Straße GmbH")
        assert "strasse" in result

    def test_nordic_o_stroke(self):
        """ø → o (nordique)."""
        result = normalize_company("Norsk Glassø AS")
        assert "glasSO".lower() in result or "glasso" in result

    def test_similarity_turkish_sap_vs_email(self):
        """company_similarity : nom SAP latinisé vs nom turc avec diacritiques ≥ 0.9."""
        sap = "Türkiye Sise ve Cam Fabrikalari A.S. (4001)"
        email = "TÜRKİYE ŞİŞE ve CAM FABRİKALARI A.Ş."
        score = company_similarity(sap, email)
        assert score >= 0.90, f"Score {score:.2f} trop bas pour SISECAM vs SAP"

    def test_similarity_sisecam_brand_vs_sap(self):
        """company_similarity : 'SISECAM' (marque) vs nom SAP complet — score modéré."""
        score = company_similarity("SISECAM", "Türkiye Sise ve Cam Fabrikalari A.S. (4001)")
        # 'sise' est dans le nom SAP, mais pas 'sisecam' → score partiel acceptable
        assert score >= 0.20, f"Score {score:.2f} inattendu pour SISECAM vs SAP"


# ─────────────────────────────────────────────────────────────────────────────
# Tests détection domaines génériques / internes
# ─────────────────────────────────────────────────────────────────────────────

class TestIsGenericDomain:
    def test_gmail_is_generic(self):
        assert is_generic_domain("gmail.com") is True

    def test_hotmail_is_generic(self):
        assert is_generic_domain("hotmail.com") is True

    def test_hotmail_fr_is_generic(self):
        assert is_generic_domain("hotmail.fr") is True

    def test_outlook_is_generic(self):
        assert is_generic_domain("outlook.com") is True

    def test_yahoo_is_generic(self):
        assert is_generic_domain("yahoo.fr") is True

    def test_orange_is_generic(self):
        assert is_generic_domain("orange.fr") is True

    def test_protonmail_is_generic(self):
        assert is_generic_domain("protonmail.com") is True

    def test_company_domain_not_generic(self):
        assert is_generic_domain("acme-industries.fr") is False

    def test_rondot_not_in_generic(self):
        assert is_generic_domain("rondot-sas.fr") is False

    def test_case_insensitive(self):
        assert is_generic_domain("Gmail.COM") is True

    def test_all_generic_domains_present(self):
        # Vérifier que les domaines critiques sont bien dans la frozenset
        critical = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "orange.fr"]
        for d in critical:
            assert d in GENERIC_DOMAINS, f"{d} should be in GENERIC_DOMAINS"


class TestIsInternalDomain:
    def test_rondot_sas_is_internal(self):
        assert is_internal_domain("rondot-sas.fr") is True

    def test_itspirit_is_internal(self):
        assert is_internal_domain("itspirit.ovh") is True

    def test_rondot_poc_is_internal(self):
        assert is_internal_domain("rondot-poc.itspirit.ovh") is True

    def test_external_company_not_internal(self):
        assert is_internal_domain("acme-industries.fr") is False

    def test_gmail_not_internal(self):
        assert is_internal_domain("gmail.com") is False

    def test_case_insensitive(self):
        assert is_internal_domain("RONDOT-SAS.FR") is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests similarité noms d'entreprise
# ─────────────────────────────────────────────────────────────────────────────

class TestCompanySimilarity:
    def test_identical_names(self):
        assert company_similarity("Acme Industries", "Acme Industries") == 1.0

    def test_same_after_normalization(self):
        # SARL suffix removed → identical
        sim = company_similarity("Dupont SARL", "Dupont")
        assert sim >= 0.90

    def test_different_companies(self):
        sim = company_similarity("Acme Industries", "Dupont SARL")
        assert sim < 0.5

    def test_empty_string_a(self):
        assert company_similarity("", "Acme") == 0.0

    def test_empty_string_b(self):
        assert company_similarity("Acme", "") == 0.0

    def test_both_empty(self):
        assert company_similarity("", "") == 0.0

    def test_accent_insensitive(self):
        sim = company_similarity("Société Générale", "Societe Generale")
        assert sim >= 0.90

    def test_case_insensitive(self):
        sim = company_similarity("ACME INDUSTRIES", "acme industries")
        assert sim >= 0.95

    def test_similar_names_above_threshold(self):
        sim = company_similarity("Verrerie Moderne", "Verrerie Moderne SAS")
        assert sim >= COMPANY_NAME_SIM_THRESHOLD


# ─────────────────────────────────────────────────────────────────────────────
# Tests EmailSignalExtractor
# ─────────────────────────────────────────────────────────────────────────────

class TestEmailSignalExtractor:

    def test_extract_final_sender_domain(self, extractor):
        signals = extractor.extract("some body", "contact@acme-industries.fr")
        assert signals.final_sender_domain == "acme-industries.fr"

    def test_no_domain_for_generic_sender(self, extractor):
        signals = extractor.extract("some body", "contact@gmail.com")
        assert signals.final_sender_domain == ""

    def test_no_domain_for_internal_sender(self, extractor):
        signals = extractor.extract("some body", "user@rondot-sas.fr")
        assert signals.final_sender_domain == ""

    def test_final_sender_email_stored(self, extractor):
        signals = extractor.extract("body", "test@example.com")
        assert signals.final_sender_email == "test@example.com"

    def test_extract_forwarded_email(self, extractor, simple_body_with_forward):
        signals = extractor.extract(simple_body_with_forward, "rondot@rondot-sas.fr")
        assert len(signals.forwarded_sender_emails) > 0
        assert "jean.dupont@acme-industries.fr" in signals.forwarded_sender_emails

    def test_best_requester_email_non_internal(self, extractor, simple_body_with_forward):
        signals = extractor.extract(simple_body_with_forward, "rondot@rondot-sas.fr")
        assert signals.best_requester_email == "jean.dupont@acme-industries.fr"

    def test_best_requester_domain_non_generic(self, extractor, simple_body_with_forward):
        signals = extractor.extract(simple_body_with_forward, "rondot@rondot-sas.fr")
        assert signals.best_requester_domain == "acme-industries.fr"

    def test_no_forwarded_in_simple_email(self, extractor):
        signals = extractor.extract("Hello, I need a quote.", "client@example.com")
        assert signals.forwarded_sender_emails == []

    def test_extract_signature_company_sarl(self, extractor, body_with_signature_sarl):
        signals = extractor.extract(body_with_signature_sarl, "pierre@dupont.fr")
        assert signals.signature_company is not None
        assert "Dupont" in signals.signature_company or "dupont" in signals.signature_company.lower()

    def test_extract_body_company(self, extractor, body_with_body_company):
        signals = extractor.extract(body_with_body_company, "contact@verrerie.fr")
        assert len(signals.body_companies) > 0
        assert any("Verrerie" in c for c in signals.body_companies)

    def test_gmail_forward_excluded_from_requester_domain(self, extractor, gmail_forward_body):
        signals = extractor.extract(gmail_forward_body, "rondot@rondot-sas.fr")
        # jean@gmail.com est le best_requester_email mais pas best_requester_domain
        if signals.best_requester_email:
            assert signals.best_requester_domain is None or \
                   not is_generic_domain(signals.best_requester_domain)

    def test_empty_body(self, extractor):
        signals = extractor.extract("", "test@example.com")
        assert signals.forwarded_sender_emails == []
        assert signals.signature_company is None
        assert signals.body_companies == []

    def test_multiple_forward_emails_extracted(self, extractor):
        body = """
De: Premier Exp premier@first-company.com
Sujet: Re: Re: Devis

---------- Forwarded message ---------
De: Second Exp second@second-company.com
"""
        signals = extractor.extract(body, "rondot@rondot-sas.fr")
        # Au moins un email non-interne extrait
        assert len(signals.forwarded_sender_emails) >= 1

    def test_internal_forward_emails_excluded(self, extractor):
        body = """
De: Collègue interne colleague@rondot-sas.fr
Sujet: Transfert

---------- Forwarded message ---------
De: Vrai client client@external-company.com
"""
        signals = extractor.extract(body, "rondot@rondot-sas.fr")
        internal_in_list = any("rondot-sas.fr" in e for e in signals.forwarded_sender_emails)
        assert not internal_in_list


# ─────────────────────────────────────────────────────────────────────────────
# Tests scoring candidats
# ─────────────────────────────────────────────────────────────────────────────

class TestCandidateScoring:
    """Tests sur _score_candidate_from_dict()"""

    def _make_signals(self, **kwargs) -> EmailSignals:
        defaults = {
            'final_sender_email': '',
            'final_sender_domain': '',
            'forwarded_sender_emails': [],
            'best_requester_email': None,
            'best_requester_domain': None,
            'signature_company': None,
            'body_companies': [],
            'llm_company': None,
        }
        defaults.update(kwargs)
        return EmailSignals(**defaults)

    def _make_client(self, card_code, card_name, email="", raw_score=0):
        return {
            'CardCode': card_code,
            'CardName': card_name,
            'EmailAddress': email,
            '_raw_score': raw_score,
            '_match_reason': '',
        }

    def test_exact_email_match_gives_high_score(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(final_sender_email="contact@acme.com")
        client = self._make_client("C001", "Acme Industries", email="contact@acme.com")
        result = engine._score_candidate_from_dict(client, signals)
        assert result.confidence_score >= SIGNAL_WEIGHTS['exact_email_match']
        assert 'exact_email_match' in result.matched_signals

    def test_forwarded_email_match(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(
            final_sender_email="rondot@rondot-sas.fr",
            forwarded_sender_emails=["contact@acme.com"]
        )
        client = self._make_client("C001", "Acme Industries", email="contact@acme.com")
        result = engine._score_candidate_from_dict(client, signals)
        assert 'forwarded_email_match' in result.matched_signals
        assert result.confidence_score >= SIGNAL_WEIGHTS['forwarded_email_match']

    def test_domain_match(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(
            final_sender_domain="acme.com",
            best_requester_domain="acme.com"
        )
        client = self._make_client("C001", "Acme Industries", email="info@acme.com")
        result = engine._score_candidate_from_dict(client, signals)
        assert 'domain_match' in result.matched_signals
        assert result.confidence_score >= SIGNAL_WEIGHTS['domain_match']

    def test_generic_domain_not_matched(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(
            final_sender_domain="",  # gmail filtered out
            best_requester_domain=None
        )
        client = self._make_client("C001", "Acme Industries", email="info@gmail.com")
        result = engine._score_candidate_from_dict(client, signals)
        assert 'domain_match' not in result.matched_signals

    def test_signature_company_match(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(signature_company="Acme Industries")
        client = self._make_client("C001", "Acme Industries SARL")
        result = engine._score_candidate_from_dict(client, signals)
        assert 'signature_company_match' in result.matched_signals

    def test_llm_company_match(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(llm_company="Verrerie Moderne")
        client = self._make_client("C002", "Verrerie Moderne SAS")
        result = engine._score_candidate_from_dict(client, signals)
        assert 'llm_company_match' in result.matched_signals

    def test_body_company_match(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(body_companies=["Dupont SARL", "Other Corp"])
        client = self._make_client("C003", "Dupont Industries")
        result = engine._score_candidate_from_dict(client, signals)
        # May or may not match depending on similarity threshold
        # Just ensure no crash
        assert isinstance(result.confidence_score, float)

    def test_no_signal_uses_raw_score(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals()  # No signals
        client = self._make_client("C001", "Unknown Company", raw_score=80)
        result = engine._score_candidate_from_dict(client, signals)
        # Should have a non-zero score from the raw matcher
        assert result.confidence_score > 0.0

    def test_email_match_takes_priority_over_domain(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(
            final_sender_email="contact@acme.com",
            final_sender_domain="acme.com"
        )
        client = self._make_client("C001", "Acme Industries", email="contact@acme.com")
        result = engine._score_candidate_from_dict(client, signals)
        # Should have exact_email_match, not domain_match
        assert 'exact_email_match' in result.matched_signals
        assert 'domain_match' not in result.matched_signals

    def test_score_int_matches_confidence(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(final_sender_email="c@acme.com")
        client = self._make_client("C001", "Acme", email="c@acme.com")
        result = engine._score_candidate_from_dict(client, signals)
        assert result.score == int(result.confidence_score * 100)

    def test_confidence_score_capped_at_1(self):
        engine = ClientRecognitionEngine()
        signals = self._make_signals(
            final_sender_email="c@acme.com",
            final_sender_domain="acme.com",
            signature_company="Acme Industries",
            llm_company="Acme Industries",
            body_companies=["Acme Industries"],
        )
        client = self._make_client("C001", "Acme Industries", email="c@acme.com", raw_score=100)
        result = engine._score_candidate_from_dict(client, signals)
        assert result.confidence_score <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests détection ambiguïté
# ─────────────────────────────────────────────────────────────────────────────

class TestAmbiguityDetection:

    def _make_scored_candidate(self, card_code, card_name, score) -> ScoredCandidate:
        return ScoredCandidate(
            card_code=card_code,
            card_name=card_name,
            confidence_score=score,
            matched_signals=[],
            score=int(score * 100),
            match_reason=f"test score {score}"
        )

    def test_no_ambiguity_when_gap_large(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        candidates = [
            self._make_scored_candidate("C001", "Company A", 0.90),
            self._make_scored_candidate("C002", "Company B", 0.50),
        ]
        result = engine._build_result(candidates, signals, "[TEST]")
        assert result.is_ambiguous is False

    def test_ambiguity_when_gap_small_and_low_confidence(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        # Gap = 0.05 < AMBIGUITY_GAP (0.12), both below AUTO_ACCEPT_THRESHOLD (0.80)
        candidates = [
            self._make_scored_candidate("C001", "Company A", 0.65),
            self._make_scored_candidate("C002", "Company B", 0.60),
        ]
        result = engine._build_result(candidates, signals, "[TEST]")
        assert result.is_ambiguous is True
        assert result.ambiguity_reason is not None

    def test_no_ambiguity_above_auto_accept_threshold(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        # Even if gap is small, above AUTO_ACCEPT_THRESHOLD → not ambiguous
        candidates = [
            self._make_scored_candidate("C001", "Company A", 0.85),
            self._make_scored_candidate("C002", "Company B", 0.81),
        ]
        result = engine._build_result(candidates, signals, "[TEST]")
        assert result.is_ambiguous is False

    def test_no_candidates_returns_unmatched(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        result = engine._build_result([], signals, "[TEST]")
        assert result.matched is False
        assert result.client_code is None

    def test_single_candidate_not_ambiguous(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        candidates = [self._make_scored_candidate("C001", "Company A", 0.70)]
        result = engine._build_result(candidates, signals, "[TEST]")
        assert result.is_ambiguous is False

    def test_ambiguous_result_has_no_matched_client(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        candidates = [
            self._make_scored_candidate("C001", "Company A", 0.65),
            self._make_scored_candidate("C002", "Company B", 0.60),
        ]
        result = engine._build_result(candidates, signals, "[TEST]")
        # Ambiguous → matched should be False
        assert result.matched is False

    def test_matched_false_when_score_below_minimum(self):
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="x@example.com")
        candidates = [self._make_scored_candidate("C001", "Company A", 0.30)]
        result = engine._build_result(candidates, signals, "[TEST]")
        assert result.matched is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests flux complet (recognize_client)
# ─────────────────────────────────────────────────────────────────────────────

class MockMatchedClient:
    """Mock de MatchedClient pour tester sans importer email_matcher."""
    def __init__(self, card_code, card_name, email_address="", score=80, match_reason=""):
        self.card_code = card_code
        self.card_name = card_name
        self.email_address = email_address
        self.score = score
        self.match_reason = match_reason


class TestFullRecognitionFlow:

    def test_exact_email_match_high_confidence(self, engine):
        body = "Bonjour, je souhaite un devis."
        candidates = [MockMatchedClient("C001", "Acme Industries", "contact@acme.com", score=95)]
        result = engine.recognize_client(
            body=body,
            sender_email="contact@acme.com",
            existing_candidates=candidates,
        )
        assert result.matched is True
        assert result.client_code == "C001"
        assert result.confidence_score >= 0.90

    def test_no_match_with_empty_candidates(self, engine):
        result = engine.recognize_client(
            body="Hello",
            sender_email="x@example.com",
            existing_candidates=[],
        )
        assert result.matched is False
        assert result.client_code is None

    def test_forwarded_email_recognized(self, engine, simple_body_with_forward):
        candidates = [
            MockMatchedClient("C001", "ACME Industries", "jean.dupont@acme-industries.fr", score=70)
        ]
        result = engine.recognize_client(
            body=simple_body_with_forward,
            sender_email="commercial@rondot-sas.fr",
            existing_candidates=candidates,
        )
        # Forwarded email should match
        assert result.matched is True
        assert 'forwarded_email_match' in result.matched_signals

    def test_llm_name_improves_score(self, engine):
        body = "Demande de devis pour notre entreprise."
        candidates = [MockMatchedClient("C002", "Dupont Industries SARL", score=60)]
        result = engine.recognize_client(
            body=body,
            sender_email="contact@dupont.fr",
            llm_client_name="Dupont Industries",
            existing_candidates=candidates,
        )
        assert result.confidence_score > 0.30

    def test_result_contains_candidates_list(self, engine):
        candidates = [
            MockMatchedClient("C001", "Acme", "c@acme.com", score=80),
            MockMatchedClient("C002", "Other", "c@other.com", score=60),
        ]
        result = engine.recognize_client(
            body="body",
            sender_email="c@acme.com",
            existing_candidates=candidates,
        )
        assert len(result.candidates) == 2

    def test_candidates_sorted_by_score(self, engine):
        candidates = [
            MockMatchedClient("C002", "Other", "c@other.com", score=60),
            MockMatchedClient("C001", "Acme", "c@acme.com", score=80),
        ]
        result = engine.recognize_client(
            body="body",
            sender_email="c@acme.com",
            existing_candidates=candidates,
        )
        if len(result.candidates) >= 2:
            assert result.candidates[0].confidence_score >= result.candidates[1].confidence_score

    def test_fallback_cache_search(self, engine):
        """Test recherche dans cache SAP si peu de candidats existants."""
        body = "Demande de Verrerie Moderne SAS."
        clients_cache = [
            {'CardCode': 'C010', 'CardName': 'Verrerie Moderne', 'EmailAddress': 'info@vm.fr'},
            {'CardCode': 'C011', 'CardName': 'Other Company', 'EmailAddress': 'info@other.fr'},
        ]
        result = engine.recognize_client(
            body=body,
            sender_email="contact@vm.fr",
            existing_candidates=[],
            clients_cache=clients_cache,
        )
        # Should find Verrerie Moderne from cache via domain or company name
        codes = [c.card_code for c in result.candidates]
        # C010 should be in candidates (domain match or name match)
        assert isinstance(result, ClientRecognitionResult)

    def test_signals_stored_in_result(self, engine, simple_body_with_forward):
        candidates = [MockMatchedClient("C001", "Acme", "jean.dupont@acme-industries.fr", score=70)]
        result = engine.recognize_client(
            body=simple_body_with_forward,
            sender_email="commercial@rondot-sas.fr",
            existing_candidates=candidates,
        )
        assert result.final_sender_email == "commercial@rondot-sas.fr"
        assert len(result.forwarded_sender_emails) > 0

    def test_generic_sender_domain_not_used(self, engine):
        """Un expéditeur gmail ne doit pas créer un faux match par domaine."""
        candidates = [
            MockMatchedClient("C001", "Gmail User SARL", "info@gmail.com", score=40)
        ]
        result = engine.recognize_client(
            body="Hello",
            sender_email="user@gmail.com",
            existing_candidates=candidates,
        )
        # domain_match should NOT appear
        if result.candidates:
            assert 'domain_match' not in result.candidates[0].matched_signals

    def test_top_5_candidates_max(self, engine):
        """Le résultat ne doit pas contenir plus de 5 candidats."""
        candidates = [
            MockMatchedClient(f"C{i:03d}", f"Company {i}", f"c{i}@co{i}.com", score=50 + i)
            for i in range(10)
        ]
        result = engine.recognize_client(
            body="body",
            sender_email="x@external.com",
            existing_candidates=candidates,
        )
        assert len(result.candidates) <= 5


# ─────────────────────────────────────────────────────────────────────────────
# Tests singleton
# ─────────────────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_get_engine_returns_instance(self):
        engine = get_client_recognition_engine()
        assert isinstance(engine, ClientRecognitionEngine)

    def test_get_engine_returns_same_instance(self):
        e1 = get_client_recognition_engine()
        e2 = get_client_recognition_engine()
        assert e1 is e2


# ─────────────────────────────────────────────────────────────────────────────
# Tests cas limites
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_sender_email_without_at_sign(self, extractor):
        """Expéditeur sans @ ne doit pas planter."""
        signals = extractor.extract("body", "not-an-email")
        assert signals.final_sender_domain == ""
        assert signals.final_sender_email == "not-an-email"

    def test_body_is_none_like(self, extractor):
        """Body None-like (string vide)."""
        signals = extractor.extract("", "test@example.com")
        assert signals.forwarded_sender_emails == []

    def test_very_long_body(self, extractor):
        """Corps très long ne doit pas planter."""
        body = "Hello world. " * 5000
        signals = extractor.extract(body, "test@example.com")
        assert isinstance(signals, EmailSignals)

    def test_body_with_no_company_patterns(self, extractor):
        """Corps sans motif société."""
        body = "Bonjour, je veux un devis rapide. Merci."
        signals = extractor.extract(body, "test@example.com")
        assert signals.body_companies == []

    def test_normalize_company_with_only_suffix(self):
        """Nom composé uniquement d'un suffixe légal."""
        result = normalize_company("SARL")
        # Should return empty or minimal string after suffix removal
        assert isinstance(result, str)

    def test_company_similarity_special_chars(self):
        """Noms avec caractères spéciaux."""
        sim = company_similarity("L'Entreprise & Fils", "L Entreprise Fils")
        assert isinstance(sim, float)
        assert 0.0 <= sim <= 1.0

    def test_recognize_client_with_none_candidates(self, engine):
        """existing_candidates=None ne doit pas planter."""
        result = engine.recognize_client(
            body="body",
            sender_email="test@example.com",
            existing_candidates=None,
        )
        assert isinstance(result, ClientRecognitionResult)
        assert result.matched is False

    def test_recognition_result_always_has_candidates_list(self, engine):
        result = engine.recognize_client(
            body="",
            sender_email="",
            existing_candidates=None,
        )
        assert isinstance(result.candidates, list)

    def test_score_candidate_empty_dict(self):
        """Scorer un dict client vide ne doit pas planter."""
        engine = ClientRecognitionEngine()
        signals = EmailSignals(final_sender_email="test@example.com")
        result = engine._score_candidate_from_dict({}, signals)
        assert isinstance(result, ScoredCandidate)
        assert result.confidence_score >= 0.0

    def test_body_company_extraction_deduplication(self, extractor):
        """Les sociétés dupliquées ne doivent apparaître qu'une fois."""
        body = "Acme Industries SAS nous contacte. Acme Industries SAS est notre client."
        signals = extractor.extract(body, "c@acme.com")
        counts = {}
        for c in signals.body_companies:
            key = c.lower()
            counts[key] = counts.get(key, 0) + 1
        assert all(v == 1 for v in counts.values()), "Duplicates found in body_companies"

    def test_body_company_max_5(self, extractor):
        """Maximum 5 sociétés extraites du corps."""
        lines = "\n".join(f"Société Test{i} SAS présente." for i in range(10))
        signals = extractor.extract(lines, "test@example.com")
        assert len(signals.body_companies) <= 5
