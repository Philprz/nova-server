# services/email_matcher.py
"""
Service de matching email vs données SAP.
Charge les clients et produits SAP, puis compare avec le contenu des emails
pour identifier les correspondances (clients, articles, quantités).
Utilise du fuzzy matching pour éviter la non-reconnaissance.
"""

import re
import logging
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --- Modèles de résultat ---

class MatchedClient(BaseModel):
    card_code: str
    card_name: str
    email_address: Optional[str] = None
    score: int  # 0-100
    match_reason: str


class MatchedProduct(BaseModel):
    item_code: str
    item_name: str
    quantity: int = 1
    score: int  # 0-100
    match_reason: str


class MatchResult(BaseModel):
    clients: List[MatchedClient] = []
    products: List[MatchedProduct] = []
    best_client: Optional[MatchedClient] = None
    extracted_domains: List[str] = []


# --- Service principal ---

class EmailMatcher:
    """Compare le contenu d'un email avec les données réelles SAP."""

    def __init__(self):
        self._clients_cache: List[Dict[str, Any]] = []
        self._items_cache: Dict[str, Dict[str, Any]] = {}  # ItemCode → item data
        self._client_domains: Dict[str, List[Dict[str, Any]]] = {}  # domain → [clients]
        self._cache_loaded_at: Optional[datetime] = None
        self._sap_service = None
        self.CACHE_TTL = timedelta(hours=2)

    def _get_sap_service(self):
        """Lazy init du service SAP."""
        if self._sap_service is None:
            from services.sap_business_service import SAPBusinessService
            self._sap_service = SAPBusinessService()
        return self._sap_service

    async def ensure_cache(self):
        """S'assure que le cache est chargé et valide."""
        if (self._cache_loaded_at is None or
                datetime.now() - self._cache_loaded_at > self.CACHE_TTL):
            await self._load_reference_data()

    async def _load_reference_data(self):
        """Charge les clients et produits depuis SAP."""
        sap = self._get_sap_service()

        try:
            # --- Charger les clients ---
            logger.info("Chargement des clients SAP...")
            clients_data = await sap._call_sap("/BusinessPartners", params={
                "$filter": "CardType eq 'cCustomer'",
                "$select": "CardCode,CardName,EmailAddress,Phone1",
                "$top": 5000,
                "$orderby": "CardName"
            })

            self._clients_cache = clients_data.get("value", [])

            # Construire l'index par domaine email
            self._client_domains = {}
            for client in self._clients_cache:
                email = client.get("EmailAddress", "") or ""
                if "@" in email:
                    domain = email.split("@")[-1].lower().strip()
                    if domain:
                        if domain not in self._client_domains:
                            self._client_domains[domain] = []
                        self._client_domains[domain].append(client)

            logger.info(f"Clients SAP charges: {len(self._clients_cache)} "
                        f"({len(self._client_domains)} domaines indexes)")

            # --- Charger les produits ---
            logger.info("Chargement des produits SAP...")
            items_data = await sap._call_sap("/Items", params={
                "$select": "ItemCode,ItemName",
                "$top": 10000,
                "$orderby": "ItemCode"
            })

            self._items_cache = {}
            for item in items_data.get("value", []):
                code = item.get("ItemCode", "")
                if code:
                    self._items_cache[code] = item

            logger.info(f"Produits SAP charges: {len(self._items_cache)}")

            self._cache_loaded_at = datetime.now()

        except Exception as e:
            logger.error(f"Erreur chargement donnees SAP: {e}")
            # Ne pas écraser le cache existant si erreur
            if not self._clients_cache:
                self._clients_cache = []
            if not self._items_cache:
                self._items_cache = {}

    # --- Matching principal ---

    async def match_email(
        self,
        body: str,
        sender_email: str = "",
        subject: str = ""
    ) -> MatchResult:
        """Point d'entrée : analyse un email et retourne les matchs SAP."""
        await self.ensure_cache()

        full_text = f"{subject} {body}"

        # 1. Extraire les domaines email du texte
        extracted_domains = self._extract_email_domains(full_text, sender_email)

        # 2. Matcher les clients
        matched_clients = self._match_clients(full_text, extracted_domains)

        # 3. Matcher les produits
        matched_products = self._match_products(full_text)

        # Meilleur client
        best_client = matched_clients[0] if matched_clients else None

        return MatchResult(
            clients=matched_clients,
            products=matched_products,
            best_client=best_client,
            extracted_domains=extracted_domains
        )

    # --- Extraction des domaines email ---

    def _extract_email_domains(self, text: str, sender_email: str = "") -> List[str]:
        """Extrait tous les domaines email uniques du texte."""
        domains = set()

        # Domaine de l'expéditeur
        if "@" in sender_email:
            domain = sender_email.split("@")[-1].lower().strip()
            # Ignorer les domaines internes RONDOT
            if not self._is_internal_domain(domain):
                domains.add(domain)

        # Chercher tous les emails dans le texte (y compris dans les headers De:/From:)
        email_patterns = [
            r'[\w._%+-]+@([\w.-]+\.\w{2,})',  # email@domain.com
            r'mailto:([\w._%+-]+@([\w.-]+\.\w{2,}))',  # mailto:
        ]

        for pattern in email_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Le groupe capture le domaine ou l'email complet
                groups = match.groups()
                for g in groups:
                    if g and "." in g:
                        domain = g.lower().strip()
                        if "@" in domain:
                            domain = domain.split("@")[-1]
                        if not self._is_internal_domain(domain):
                            domains.add(domain)

        return list(domains)

    def _is_internal_domain(self, domain: str) -> bool:
        """Vérifie si un domaine est interne (RONDOT)."""
        internal = [
            'rondot-sas.fr', 'rondot-poc.itspirit.ovh',
            'itspirit.ovh', 'rondot.fr', 'rondot-sas.com'
        ]
        return domain in internal

    # --- Matching clients ---

    def _match_clients(
        self,
        text: str,
        extracted_domains: List[str]
    ) -> List[MatchedClient]:
        """Trouve les clients SAP qui matchent le texte de l'email."""
        matches: List[MatchedClient] = []
        text_normalized = self._normalize(text)

        for client in self._clients_cache:
            card_code = client.get("CardCode", "")
            card_name = client.get("CardName", "")
            email = client.get("EmailAddress", "") or ""

            if not card_name:
                continue

            best_score = 0
            best_reason = ""

            # --- Stratégie 1 : Match par domaine email (score 95) ---
            if email and "@" in email:
                client_domain = email.split("@")[-1].lower().strip()
                if client_domain in extracted_domains:
                    best_score = 95
                    best_reason = f"Domaine email: {client_domain}"

            # --- Stratégie 2 : CardName exact dans le texte (score 90) ---
            if best_score < 90:
                name_normalized = self._normalize(card_name)
                if len(name_normalized) >= 3 and name_normalized in text_normalized:
                    if best_score < 90:
                        best_score = 90
                        best_reason = f"Nom exact dans le texte: {card_name}"

            # --- Stratégie 3 : Fuzzy match CardName (score 70-85) ---
            if best_score < 70:
                # Extraire les mots significatifs du texte (>= 4 chars)
                words = set(re.findall(r'\b\w{4,}\b', text_normalized))
                name_normalized = self._normalize(card_name)

                # Comparer chaque mot du texte avec le nom du client
                for word in words:
                    ratio = SequenceMatcher(None, word, name_normalized).ratio()
                    if ratio > 0.75:
                        score = int(70 + (ratio - 0.75) * 60)  # 70-85
                        if score > best_score:
                            best_score = min(score, 85)
                            best_reason = f"Fuzzy match: '{word}' ~ '{card_name}' ({ratio:.0%})"

                # Aussi comparer des groupes de 2 mots
                name_parts = name_normalized.split()
                if len(name_parts) >= 1:
                    first_part = name_parts[0]
                    if len(first_part) >= 4:
                        for word in words:
                            ratio = SequenceMatcher(None, word, first_part).ratio()
                            if ratio > 0.8:
                                score = int(70 + (ratio - 0.75) * 60)
                                if score > best_score:
                                    best_score = min(score, 82)
                                    best_reason = f"Fuzzy partiel: '{word}' ~ '{first_part}' ({ratio:.0%})"

            # --- Stratégie 4 : Domaine email dans le nom du client (score 80) ---
            if best_score < 80:
                for domain in extracted_domains:
                    domain_name = domain.split(".")[0].lower()
                    if len(domain_name) >= 4:
                        name_lower = card_name.lower()
                        if domain_name in name_lower:
                            best_score = 80
                            best_reason = f"Domaine '{domain_name}' dans le nom client"
                            break
                        # Fuzzy domaine vs nom
                        ratio = SequenceMatcher(None, domain_name,
                                                self._normalize(card_name)).ratio()
                        if ratio > 0.7:
                            score = int(65 + (ratio - 0.7) * 50)
                            if score > best_score:
                                best_score = min(score, 78)
                                best_reason = f"Fuzzy domaine: '{domain_name}' ~ '{card_name}' ({ratio:.0%})"

            # Ajouter si score suffisant
            if best_score >= 60:
                matches.append(MatchedClient(
                    card_code=card_code,
                    card_name=card_name,
                    email_address=email or None,
                    score=best_score,
                    match_reason=best_reason
                ))

        # Trier par score décroissant
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:5]  # Top 5 max

    # --- Matching produits ---

    def _match_products(self, text: str) -> List[MatchedProduct]:
        """Trouve les produits SAP dont le code apparaît dans le texte."""
        matches: List[MatchedProduct] = []
        matched_codes = set()

        # Extraire tous les tokens potentiels (codes produits)
        # Codes numériques (6+ chiffres)
        potential_codes = set(re.findall(r'\b(\d{6,})\b', text))
        # Codes alphanumériques (ex: MOT-5KW-001, AB12345)
        potential_codes |= set(re.findall(r'\b([A-Z][A-Z0-9-]{4,}[A-Z0-9])\b', text))
        potential_codes |= set(re.findall(r'\b([A-Z]{2,}\d{3,})\b', text, re.IGNORECASE))

        for code in potential_codes:
            code_upper = code.upper()

            # --- Match exact ---
            if code_upper in self._items_cache:
                if code_upper not in matched_codes:
                    item = self._items_cache[code_upper]
                    qty = self._extract_quantity_near(text, code)
                    matches.append(MatchedProduct(
                        item_code=item.get("ItemCode", code_upper),
                        item_name=item.get("ItemName", ""),
                        quantity=qty,
                        score=100,
                        match_reason=f"Code exact: {code_upper}"
                    ))
                    matched_codes.add(code_upper)
                continue

            # --- Match par code original (sans upper) ---
            if code in self._items_cache:
                if code not in matched_codes:
                    item = self._items_cache[code]
                    qty = self._extract_quantity_near(text, code)
                    matches.append(MatchedProduct(
                        item_code=item.get("ItemCode", code),
                        item_name=item.get("ItemName", ""),
                        quantity=qty,
                        score=100,
                        match_reason=f"Code exact: {code}"
                    ))
                    matched_codes.add(code)
                continue

            # --- Match partiel (startswith) ---
            if len(code) >= 6:
                for item_code, item in self._items_cache.items():
                    if item_code.startswith(code_upper) or code_upper.startswith(item_code):
                        if item_code not in matched_codes:
                            qty = self._extract_quantity_near(text, code)
                            matches.append(MatchedProduct(
                                item_code=item_code,
                                item_name=item.get("ItemName", ""),
                                quantity=qty,
                                score=80,
                                match_reason=f"Code partiel: {code} ~ {item_code}"
                            ))
                            matched_codes.add(item_code)
                        break  # Premier match partiel suffit

        # Trier par score décroissant
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    # --- Extraction de quantité contextuelle ---

    def _extract_quantity_near(self, text: str, code: str, radius: int = 80) -> int:
        """Extrait la quantité mentionnée près d'un code produit."""
        # Trouver la position du code dans le texte
        idx = text.find(code)
        if idx == -1:
            idx = text.lower().find(code.lower())
        if idx == -1:
            return 1  # Défaut

        # Extraire le contexte autour du code
        start = max(0, idx - radius)
        end = min(len(text), idx + len(code) + radius)
        context = text[start:end]

        # Patterns de quantité
        qty_patterns = [
            r'qt[eéy]\s*[:\s]*(\d+)',
            r'quantit[eé]\s*[:\s]*(\d+)',
            r'(\d+)\s*(?:pcs|pi[eè]ces?|unit[eé]s?)',
            r'x\s*(\d+)',
            r':\s*(\d+)\b',
        ]

        for pattern in qty_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                try:
                    qty = int(match.group(1))
                    if 0 < qty < 100000:  # Sanity check
                        return qty
                except (ValueError, IndexError):
                    pass

        return 1  # Défaut

    # --- Utilitaires ---

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalise un texte pour la comparaison fuzzy."""
        if not text:
            return ""
        # Supprimer les accents
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        # Lowercase
        text = text.lower()
        # Supprimer la ponctuation sauf tirets
        text = re.sub(r'[^\w\s-]', ' ', text)
        # Espaces multiples
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# --- Singleton ---

_email_matcher: Optional[EmailMatcher] = None


def get_email_matcher() -> EmailMatcher:
    """Factory pattern pour obtenir l'instance du matcher."""
    global _email_matcher
    if _email_matcher is None:
        _email_matcher = EmailMatcher()
        logger.info("EmailMatcher instance created")
    return _email_matcher
