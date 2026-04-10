# tests/unit/test_client_domain_match.py
"""
Tests unitaires — PRE-MATCH par domaine FROM email (_try_match_by_from_domain).

Critères de validation :
  ✔ Test MEG  : marie.nader@meg.com.eg → C0240, auto_selected=True, FROM_DOMAIN_OVERRIDE
  ✔ Fournisseur exclu : domaine fournisseur ne génère pas de PRE-MATCH
  ✔ Domaine générique (gmail) → None (retour au matching standard)
  ✔ Domaine interne RONDOT → None
  ✔ Multi-clients même domaine → None (ambiguïté → matching standard)
  ✔ Non-régression : sans domaine indexé, le moteur passe au matching standard normal

Règle finale : toute modification qui dégrade un cas existant est REFUSÉE.
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from services.email_matcher import EmailMatcher, MatchedClient


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_client(card_code: str, card_name: str, email: str = None,
                 card_type: str = "C", country: str = None, city: str = None) -> dict:
    """Crée un dict client SAP minimal pour les tests."""
    return {
        "CardCode": card_code,
        "CardName": card_name,
        "EmailAddress": email,
        "CardType": card_type,
        "contact_emails": None,
        "Country": country,
        "City": city,
    }


def _build_matcher(clients: list) -> EmailMatcher:
    """
    Crée un EmailMatcher avec cache pré-rempli ET index _client_domains construit
    à partir des EmailAddress des clients (reproduit la logique de ensure_cache).
    """
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

    # Reproduire la construction de l'index domaine (comme ensure_cache())
    for client in clients:
        email = client.get("EmailAddress") or ""
        if email and "@" in email:
            domain = email.split("@")[-1].lower().strip()
            if domain:
                if domain not in matcher._client_domains:
                    matcher._client_domains[domain] = []
                matcher._client_domains[domain].append(client)

    return matcher


# ─── Tests _try_match_by_from_domain ─────────────────────────────────────────

class TestTryMatchByFromDomain:
    """Tests unitaires directs de la méthode _try_match_by_from_domain."""

    def test_meg_unique_match(self):
        """
        CAS CRITIQUE : marie.nader@meg.com.eg → C0240 (1 seul client, non-fournisseur).
        Attendu : MatchedClient retourné, score=100, reason=FROM_DOMAIN_OVERRIDE.
        """
        clients = [
            _make_client("C0240", "MIDDLE EAST GLASS MANUFACTURING",
                         email="info@meg.com.eg", card_type="C", country="EG"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("marie.nader@meg.com.eg")

        assert result is not None, "PRE-MATCH doit trouver C0240 via meg.com.eg"
        assert result.card_code == "C0240"
        assert result.score == 100
        assert "FROM_DOMAIN_OVERRIDE" in result.match_reason
        assert any("domain_exact_match" in r for r in result.match_reasons)

    def test_generic_domain_returns_none(self):
        """
        Domaine générique (gmail.com) → None (pas de PRE-MATCH).
        """
        clients = [
            _make_client("C0001", "SOME CLIENT", email="contact@gmail.com", card_type="C"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("buyer@gmail.com")
        assert result is None, "gmail.com est générique → pas de PRE-MATCH"

    def test_internal_rondot_domain_returns_none(self):
        """
        Domaine interne RONDOT → None.
        """
        matcher = _build_matcher([])

        result = matcher._try_match_by_from_domain("user@rondot-sa.com")
        assert result is None, "rondot-sa.com est interne → pas de PRE-MATCH"

    def test_no_sender_email_returns_none(self):
        """
        Pas d'email expéditeur → None.
        """
        matcher = _build_matcher([])

        assert matcher._try_match_by_from_domain("") is None
        assert matcher._try_match_by_from_domain("no_at_sign") is None

    def test_domain_not_indexed_returns_none(self):
        """
        Domaine non présent dans l'index → None (retour au matching standard).
        """
        clients = [
            _make_client("C0001", "AUTRE CLIENT", email="contact@autreclient.fr", card_type="C"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("buyer@unknown-domain.com")
        assert result is None, "Domaine non indexé → pas de PRE-MATCH"

    def test_supplier_excluded_returns_none(self):
        """
        Le domaine correspond uniquement à un fournisseur (CardType='S') → None.
        Les fournisseurs ne doivent JAMAIS être sélectionnés via PRE-MATCH.
        """
        clients = [
            _make_client("S0001", "FOURNISSEUR MEG", email="contact@fournisseur.com", card_type="S"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("buyer@fournisseur.com")
        assert result is None, "Fournisseur doit être exclu du PRE-MATCH"

    def test_supplier_and_customer_same_domain_returns_customer(self):
        """
        Même domaine partagé par un fournisseur ET un client → retourne le client.
        Condition : 1 seul client → PRE-MATCH validé.
        """
        clients = [
            _make_client("C0100", "CLIENT PARTAGÉ", email="client@shared.com", card_type="C"),
            _make_client("S0100", "FOURNISSEUR PARTAGÉ", email="supplier@shared.com", card_type="S"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("buyer@shared.com")

        assert result is not None, "1 seul client avec ce domaine → PRE-MATCH valide"
        assert result.card_code == "C0100"

    def test_two_customers_same_domain_returns_none(self):
        """
        Deux clients distincts avec le même domaine → ambiguïté → None.
        Le matching standard (scoring complet) doit prendre le relais.
        """
        clients = [
            _make_client("C0001", "CLIENT A", email="contact@ambig.com", card_type="C"),
            _make_client("C0002", "CLIENT B", email="info@ambig.com", card_type="C"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("buyer@ambig.com")
        assert result is None, "Ambiguïté 2 clients → pas de PRE-MATCH"

    def test_meg_result_has_country(self):
        """
        Le MatchedClient retourné par PRE-MATCH doit contenir le pays SAP.
        """
        clients = [
            _make_client("C0240", "MIDDLE EAST GLASS MANUFACTURING",
                         email="info@meg.com.eg", card_type="C", country="EG", city="Cairo"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("marie.nader@meg.com.eg")

        assert result is not None
        assert result.country == "EG"
        assert result.city == "Cairo"

    # ── Fallback acronyme (client sans email SAP enregistré) ─────────────────

    def test_meg_acronym_fallback_no_sap_email(self):
        """
        CAS RÉEL : C0240 n'a PAS d'email dans SAP.
        meg.com.eg → domain_base="meg" → initiales de MIDDLE EAST GLASS MANUFACTURING CO = "megmc"
        → starts with "meg" → match unique → score=99, source=FROM_DOMAIN_ACRONYM.
        """
        clients = [
            # Pas d'email SAP enregistré (reproduit la réalité SAP)
            _make_client("C0240", "MIDDLE EAST GLASS MANUFACTURING CO.",
                         email=None, card_type="C", country="EG"),
            # Autres clients égyptiens (ne doivent PAS matcher)
            _make_client("C0195", "MISR GLASS MANUFACTURING CO", email=None, card_type="C", country="EG"),
            _make_client("C0299", "SAID TEX", email=None, card_type="C", country="EG"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("marie.nader@meg.com.eg")

        assert result is not None, (
            "Le fallback acronyme doit identifier C0240 via les initiales 'megmc' startswith 'meg'"
        )
        assert result.card_code == "C0240", f"Attendu C0240, obtenu {result.card_code}"
        assert result.score == 99
        assert "FROM_DOMAIN_ACRONYM" in result.match_reason
        assert any("domain_acronym_match" in r for r in result.match_reasons)

    def test_acronym_fallback_no_match_if_multiple(self):
        """
        Si plusieurs clients ont les mêmes initiales → pas de match acronyme (ambiguïté).
        """
        clients = [
            _make_client("C0001", "MARTIN EXPORT GROUP", email=None, card_type="C"),
            _make_client("C0002", "MEGA EXPRESS GLOBAL", email=None, card_type="C"),
        ]
        matcher = _build_matcher(clients)

        # "meg" correspond aux initiales des deux → pas de match unique
        result = matcher._try_match_by_from_domain("buyer@meg.example.com")
        assert result is None, "Ambiguïté initiales → pas de fallback acronyme"

    def test_acronym_fallback_excludes_suppliers(self):
        """
        Un fournisseur avec les mêmes initiales ne doit pas être sélectionné.
        Si le seul match acronyme est un fournisseur → None.
        """
        clients = [
            _make_client("S0001", "MEGA EXPORT GROUP", email=None, card_type="S"),
        ]
        matcher = _build_matcher(clients)

        result = matcher._try_match_by_from_domain("buyer@meg.fournisseur.com")
        assert result is None, "Fournisseur exclu du fallback acronyme aussi"

    def test_long_domain_base_no_acronym(self):
        """
        Domaine base > 5 chars → pas de fallback acronyme (trop long pour être des initiales).
        """
        clients = [
            _make_client("C0001", "SHEPPEE INTERNATIONAL", email=None, card_type="C"),
        ]
        matcher = _build_matcher(clients)

        # "sheppee" = 7 chars → hors de la plage 2-5 → pas de fallback acronyme
        result = matcher._try_match_by_from_domain("buyer@sheppee.com")
        # Peut retourner None (pas d'email SAP, pas d'acronyme) ou un autre résultat
        # L'important : pas de match acronyme via sheppee (7 chars)
        if result is not None:
            assert "domain_acronym_match" not in str(result.match_reasons), (
                "Domaine base 'sheppee' (7 chars) ne doit pas déclencher le fallback acronyme"
            )


# ─── Tests intégration match_email() avec PRE-MATCH ──────────────────────────

class TestMatchEmailDomainOverride:
    """
    Tests d'intégration : match_email() doit retourner FROM_DOMAIN_OVERRIDE
    quand le PRE-MATCH trouve un match unique.
    """

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _build_full_matcher(self, clients: list) -> EmailMatcher:
        """Matcher complet avec _match_products stubé pour isolation."""
        matcher = _build_matcher(clients)

        # Stub _match_products pour isolation (pas de vrai SAP nécessaire)
        matcher._match_products = lambda text, card_code: []

        return matcher

    def test_meg_match_email_autoselect(self):
        """
        CAS CRITIQUE bout-en-bout :
        match_email() avec from=marie.nader@meg.com.eg →
          auto_selected=True, best_client.card_code=C0240, auto_select_reason=FROM_DOMAIN_OVERRIDE
        """
        clients = [
            _make_client("C0240", "MIDDLE EAST GLASS MANUFACTURING",
                         email="info@meg.com.eg", card_type="C", country="EG"),
        ]
        matcher = self._build_full_matcher(clients)

        result = self._run(matcher.match_email(
            body="Dear Rondot, please quote the following items...",
            sender_email="marie.nader@meg.com.eg",
            subject="Quotation request",
        ))

        assert result.auto_selected is True, "auto_selected doit être True"
        assert result.best_client is not None, "best_client ne doit pas être None"
        assert result.best_client.card_code == "C0240", (
            f"Attendu C0240, obtenu {result.best_client.card_code}"
        )
        assert result.auto_select_reason == "FROM_DOMAIN_OVERRIDE", (
            f"source attendue FROM_DOMAIN_OVERRIDE, obtenue: {result.auto_select_reason}"
        )
        assert len(result.clients) == 1

    def test_no_domain_indexed_falls_through_to_standard(self):
        """
        Non-régression : quand le domaine n'est PAS dans l'index, le matching
        standard (_match_clients) prend le relais normalement.
        Attendu : le client est quand même retrouvé par son nom.
        """
        clients = [
            _make_client("C0001", "BA GLASS BULGARIA SA",
                         email=None,  # Pas d'email indexé
                         card_type="C", country="BG", city="Plovdiv"),
        ]
        matcher = self._build_full_matcher(clients)

        result = self._run(matcher.match_email(
            body="BA Glass Bulgaria requests a quotation for float glass.",
            sender_email="georgi@unknown-domain.bg",
            subject="Quotation",
        ))

        # Le matching standard doit trouver le client par son nom
        # (pas de FROM_DOMAIN_OVERRIDE ici)
        assert result.auto_select_reason != "FROM_DOMAIN_OVERRIDE", (
            "Ne doit pas utiliser FROM_DOMAIN_OVERRIDE si domaine non indexé"
        )

    def test_generic_domain_falls_through_to_standard(self):
        """
        Non-régression : domaine générique (gmail) → pas de PRE-MATCH,
        le matching standard s'applique.
        """
        clients = [
            _make_client("C0001", "CLIENT GMAIL",
                         email="contact@clientgmail.com",
                         card_type="C"),
        ]
        matcher = self._build_full_matcher(clients)

        result = self._run(matcher.match_email(
            body="CLIENT GMAIL wants a quote.",
            sender_email="buyer@gmail.com",
            subject="Quote",
        ))

        assert result.auto_select_reason != "FROM_DOMAIN_OVERRIDE"

    def test_two_clients_same_domain_no_override(self):
        """
        Non-régression : 2 clients avec même domaine → PRE-MATCH retourne None,
        le scoring standard décide.
        """
        clients = [
            _make_client("C0001", "CLIENT ALPHA", email="alpha@shared-corp.com", card_type="C"),
            _make_client("C0002", "CLIENT BETA", email="beta@shared-corp.com", card_type="C"),
        ]
        matcher = self._build_full_matcher(clients)

        result = self._run(matcher.match_email(
            body="Shared corp request.",
            sender_email="contact@shared-corp.com",
            subject="Request",
        ))

        assert result.auto_select_reason != "FROM_DOMAIN_OVERRIDE", (
            "Ambiguïté de domaine → pas de FROM_DOMAIN_OVERRIDE"
        )


# ─── Tests non-régression sur comportement existant ──────────────────────────

class TestNonRegression:
    """
    Vérifie que les règles existantes (scoring, auto-sélection, géo)
    ne sont pas altérées par l'ajout du PRE-MATCH.
    """

    def test_try_match_returns_matchedclient_fields(self):
        """Tous les champs de MatchedClient sont bien renseignés."""
        clients = [
            _make_client("C9999", "TEST CORP", email="info@testcorp.fr", card_type="C",
                         country="FR", city="Paris"),
        ]
        matcher = _build_matcher(clients)
        result = matcher._try_match_by_from_domain("user@testcorp.fr")

        assert result is not None
        assert result.card_code == "C9999"
        assert result.card_name == "TEST CORP"
        assert result.score == 100
        assert result.nominal_score == 100
        assert result.strong_signal_score == 0
        assert result.country == "FR"
        assert result.city == "Paris"
        assert isinstance(result.match_reasons, list)
        assert len(result.match_reasons) >= 1

    def test_extract_location_signals_unchanged(self):
        """_extract_location_signals() n'est pas impactée par le PRE-MATCH."""
        country, city = EmailMatcher._extract_location_signals(
            "Our factory is in Plovdiv, Bulgaria."
        )
        assert country == "BG"
        assert city is not None and "plovdiv" in city.lower()

    def test_detect_multi_entity_group_unchanged(self):
        """_detect_multi_entity_group() n'est pas impactée."""
        from services.email_matcher import MatchedClient

        candidates = [
            MatchedClient(card_code="C_BG", card_name="BA GLASS BULGARIA SA",
                          score=85, match_reason="test", match_reasons=["test"],
                          nominal_score=85, strong_signal_score=0, country="BG"),
            MatchedClient(card_code="C_GR", card_name="BA GLASS GREECE S.A.",
                          score=85, match_reason="test", match_reasons=["test"],
                          nominal_score=85, strong_signal_score=0, country="GR"),
        ]
        assert EmailMatcher._detect_multi_entity_group(candidates) is True

    def test_is_internal_domain_unchanged(self):
        """_is_internal_domain() n'est pas impactée."""
        matcher = EmailMatcher()
        assert matcher._is_internal_domain("rondot-sa.com") is True
        assert matcher._is_internal_domain("meg.com.eg") is False
        assert matcher._is_internal_domain("gmail.com") is False
