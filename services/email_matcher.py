# services/email_matcher.py
"""
Service de matching email vs données SAP.
Utilise une base SQLite locale pour un matching ultra-rapide.
Utilise du fuzzy matching pour éviter la non-reconnaissance.
"""

import re
import logging
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel
from functools import lru_cache
from thefuzz import fuzz as _fuzz

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalisation texte (module-level, partagée entre méthodes)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Normalise un texte pour la comparaison fuzzy.

    Étapes :
    1. Minuscules
    2. Suppression des accents (NFD)
    3. Suppression de la ponctuation (garde lettres/chiffres/espaces)
    4. Suppression des espaces multiples
    """
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _discriminating_score(query_norm: str, item_norm: str) -> int:
    """
    Score de similarité amélioré pour différencier des variantes quasi-identiques.

    Problème de token_set_ratio pur : quand deux articles partagent un très long
    libellé avec UN seul mot différent (ex: PREMIUM vs BASIC + même station de charge),
    les deux scorent 100 car l'intersection de tokens communs vaut 100 par rapport
    à elle-même.

    Solution : pénaliser les mots présents dans l'ARTICLE mais absents de la REQUÊTE
    (≥4 chars). Ces mots indiquent que l'article est une variante différente.

    Exemples :
      query="handy vii premium station de charge..."
        → vs item "...premium..." : extra={pyrometre} → penalty=5  → 100-5=95  ✓
        → vs item "...basic..."   : extra={basic,pyrometre} → penalty=10 → 93-10=83 < 85 ✓
    """
    base = _fuzz.token_set_ratio(query_norm, item_norm)
    q_words = set(query_norm.split())
    i_words = set(item_norm.split())
    # Mots DANS l'article mais PAS dans la requête (≥4 chars) = mots discriminants potentiels
    extra = {w for w in i_words - q_words if len(w) >= 4}
    if extra:
        penalty = min(15, len(extra) * 6)
        base = max(0, base - penalty)
    return base


def normalize_code(code: str) -> str:
    """
    Normalise un code produit fournisseur pour la comparaison.

    Supprime TOUS les caractères non-alphanumériques (tirets, slashes, espaces, points…)
    et met en minuscules.

    Exemples :
      P-0301L-SLT  →  p0301lslt
      P/0301L-SLT  →  p0301lslt   (même résultat → match!)
      C391-15-LM   →  c39115lm
    """
    if not code:
        return ""
    return re.sub(r'[^a-z0-9]', '', code.lower())

# --- Regex pré-compilés pour performance ---
WORD_PATTERN_4PLUS = re.compile(r'\b\w{4,}\b')  # Mots 4+ caractères
WORD_PATTERN_6PLUS = re.compile(r'\b\w{6,}\b')  # Mots 6+ caractères
EMAIL_PATTERN = re.compile(r'[\w._%+-]+@([\w.-]+\.\w{2,})', re.IGNORECASE)
MAILTO_PATTERN = re.compile(r'mailto:([\w._%+-]+@([\w.-]+\.\w{2,}))', re.IGNORECASE)

# Pattern strict Adet — utilisé par extract_quantity_strict_adet() et _extract_offer_request_rows()
_ADET_STRICT_PATTERN = re.compile(r'\b(\d+(?:[.,]\d+)?)\s*Adet\b', re.IGNORECASE)

# Patterns pour détecter une référence de commande client (PO, Form No, etc.)
_CUSTOMER_REF_PATTERNS = [
    re.compile(r'Form\s+No\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    re.compile(r'PO\s+(?:No|Number|N°|Num)\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
    re.compile(r'Order\s+(?:No|Number|N°|Ref)\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
    re.compile(r'Commande\s+(?:N°|No|Ref|Numéro)\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
    re.compile(r'Bon\s+de\s+commande\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
    re.compile(r'Ref(?:erence|érence)?\s+(?:client|commande|achat)\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
    re.compile(r'Notre\s+(?:référence|commande|BC)\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
    re.compile(r'(?:Your\s+)?(?:RFQ|RFP|Inquiry)\s+(?:No|Ref|#)\s*[:\-]?\s*([\w\-\/]+)', re.IGNORECASE),
]


def extract_customer_reference(text: str) -> Optional[str]:
    """
    Extrait la référence de commande/demande client depuis un texte email ou PDF.

    Détecte : Form No, PO No/Number, Order No, Commande N°, Bon de commande,
              Référence client, Notre référence, RFQ/RFP Ref, etc.

    Retourne None si aucune référence trouvée.
    """
    if not text:
        return None
    for pattern in _CUSTOMER_REF_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    return None


def extract_quantity_strict_adet(text: str) -> Optional[float]:
    """
    Extrait UNIQUEMENT les quantités sous la forme : nombre + 'Adet'.

    RÈGLE MÉTIER ABSOLUE (documents type 'Offer Request Form' Marmara Cam) :
    La quantité valide est UNIQUEMENT le nombre immédiatement suivi du mot 'Adet'.

    Exemples VALIDES   : '50,00 Adet', '2 Adet', '1,00 Adet', '2,00 Adet'
    Exemples INVALIDES : 'DİŞ SAYISI: 194', '1940mm', '50AT10', '1160 LG', 'POS.8'

    INTERDIT :
      - Fallback sur le premier entier trouvé
      - Inférer depuis texte technique
      - Toute autre heuristique numérique

    Retourne None si aucune correspondance — JAMAIS de valeur par défaut.
    """
    match = _ADET_STRICT_PATTERN.search(text)
    if match:
        qty_str = match.group(1).replace(',', '.')
        return float(qty_str)
    return None


# --- Modèles de résultat ---

class MatchedClient(BaseModel):
    card_code: str
    card_name: str
    email_address: Optional[str] = None
    score: int  # 0-100
    match_reason: str


class MatchedProduct(BaseModel):
    # Champs existants
    item_code: str
    item_name: str
    quantity: int = 1
    score: int  # 0-100
    match_reason: str
    not_found_in_sap: bool = False  # True si le produit n'existe pas dans SAP

    # ✨ NOUVEAUX CHAMPS PRICING (Phase 5 - Automatisation complète)
    unit_price: Optional[float] = None  # Prix unitaire calculé
    line_total: Optional[float] = None  # Prix total ligne (unit_price × quantity)
    pricing_case: Optional[str] = None  # CAS_1_HC | CAS_2_HCM | CAS_3_HA | CAS_4_NP
    pricing_justification: Optional[str] = None  # Explication détaillée
    requires_validation: bool = False  # True si CAS 2 ou 4
    validation_reason: Optional[str] = None  # Raison validation
    supplier_price: Optional[float] = None  # Prix fournisseur (coût)
    margin_applied: Optional[float] = None  # Marge appliquée (%)
    confidence_score: float = 1.0  # 0.0 à 1.0
    alerts: List[str] = []  # Liste d'alertes (ex: variation prix)

    # ✨ CHAMPS TRAÇABILITÉ (nécessaires pour PriceEditor frontend)
    decision_id: Optional[str] = None  # ID décision pricing (pour mise à jour manuelle)
    historical_sales: List[Any] = []  # 3 dernières ventes (pour affichage frontend)
    sap_avg_price: Optional[float] = None  # Prix moyen SAP (AvgStdPrice)
    last_sale_price: Optional[float] = None  # Dernier prix vente (CAS 1/2)

    # ✨ CHAMP ORDRE SOURCE (Offer Request Form)
    row_no: Optional[int] = None  # Numéro de ligne dans le document source (Row No du PDF)
    last_sale_date: Optional[str] = None  # Date dernière vente
    average_price_others: Optional[float] = None  # Prix moyen autres clients (CAS 3)

    # ✨ CHAMPS POIDS (depuis SWeight1 SAP B1)
    weight_unit_value: Optional[float] = None  # Poids unitaire en kg (SWeight1)
    weight_unit: str = 'kg'                    # Unité de poids (SAP B1 stocke en kg)
    weight_total: Optional[float] = None       # Poids total = weight_unit_value × quantity

    # TODO: volume — champ SAP non identifié pour ce projet.
    # Candidat probable : SVolume1 (à valider avec équipe SAP Rondot avant implémentation).


class MatchResult(BaseModel):
    clients: List[MatchedClient] = []
    products: List[MatchedProduct] = []
    best_client: Optional[MatchedClient] = None
    extracted_domains: List[str] = []
    customer_reference: Optional[str] = None  # Référence commande client (Form No, PO No, etc.)


# --- Service principal ---

class EmailMatcher:
    """
    Compare le contenu d'un email avec les données réelles SAP.
    Utilise une base SQLite locale pour un accès ultra-rapide.
    """

    def __init__(self):
        self._cache_db = None
        self._client_domains_cache: Dict[str, List[Dict[str, Any]]] = {}  # Cache léger pour les domaines
        self._mapping_db = None  # Product mapping DB (lazy init)

    def _get_cache_db(self):
        """Lazy init du cache DB."""
        if self._cache_db is None:
            from services.sap_cache_db import get_sap_cache_db
            self._cache_db = get_sap_cache_db()
        return self._cache_db

    def _get_mapping_db(self):
        """Lazy init du mapping DB."""
        if self._mapping_db is None:
            from services.product_mapping_db import get_product_mapping_db
            self._mapping_db = get_product_mapping_db()
        return self._mapping_db

    async def ensure_cache(self):
        """Charge les clients et produits depuis le cache SQLite local."""
        if hasattr(self, '_clients_cache') and self._clients_cache:
            # Cache déjà chargé
            return

        cache_db = self._get_cache_db()

        try:
            logger.info("Chargement des clients depuis cache SQLite...")
            self._clients_cache = cache_db.get_all_clients()

            # Construire les index pour fuzzy matching optimisé
            self._client_domains = {}
            self._client_normalized = {}  # Cache normalized names
            self._client_first_letter = {}  # Index by first letter

            for client in self._clients_cache:
                card_code = client.get("CardCode", "")
                card_name = client.get("CardName", "")
                email = client.get("EmailAddress", "") or ""

                # Index par domaine email
                if email and "@" in email:
                    domain = email.split("@")[-1].lower().strip()
                    if domain:
                        if domain not in self._client_domains:
                            self._client_domains[domain] = []
                        self._client_domains[domain].append(client)

                # Pré-normaliser le nom (cache)
                if card_name:
                    normalized = self._normalize(card_name)
                    self._client_normalized[card_code] = normalized

                    # Index par première lettre (accélère fuzzy search)
                    first_letter = normalized[0] if normalized else ''
                    if first_letter:
                        if first_letter not in self._client_first_letter:
                            self._client_first_letter[first_letter] = []
                        self._client_first_letter[first_letter].append(client)

            logger.info(f"[OK] Clients charges: {len(self._clients_cache)} "
                        f"({len(self._client_domains)} domaines, "
                        f"{len(self._client_normalized)} noms normalisés, "
                        f"{len(self._client_first_letter)} index lettres)")

            # Charger les produits
            logger.info("Chargement des produits depuis cache SQLite...")
            items_list = cache_db.get_all_items()
            self._items_cache = {}
            self._items_normalized = {}  # Cache normalized item names

            for item in items_list:
                code = item.get("ItemCode", "")
                if code:
                    self._items_cache[code] = item
                    # Pré-normaliser le nom du produit
                    item_name = item.get("ItemName", "")
                    if item_name:
                        self._items_normalized[code] = self._normalize(item_name)

            # Pré-construire l'index des codes normalisés (refs fournisseurs)
            # Permet P-0301L-SLT == P/0301L-SLT via normalize_code()
            self._items_norm_code: Dict[str, str] = {}
            for item_code, item in self._items_cache.items():
                # 1. Indexer le code SAP normalisé (ex: "a10323" → "A10323")
                nc = normalize_code(item_code)
                if nc and nc not in self._items_norm_code:
                    self._items_norm_code[nc] = item_code
                # 2. Indexer le premier token de ItemName si ça ressemble à une ref fournisseur
                #    (contient au moins un chiffre et >= 4 chars après normalisation)
                item_name = item.get("ItemName", "")
                if item_name:
                    first_token = item_name.split()[0]
                    nt = normalize_code(first_token)
                    if len(nt) >= 4 and any(c.isdigit() for c in nt) and nt not in self._items_norm_code:
                        self._items_norm_code[nt] = item_code

            logger.info(f"[OK] Produits charges: {len(self._items_cache)} "
                        f"({len(self._items_normalized)} noms normalisés, "
                        f"{len(self._items_norm_code)} codes normalisés indexés)")

        except Exception as e:
            logger.error(f"Erreur chargement cache SQLite: {e}")
            # Fallback: initialiser avec des listes vides
            self._clients_cache = []
            self._items_cache = {}
            self._client_domains = {}
            self._items_norm_code = {}

    async def _load_reference_data(self):
        """Charge les clients et produits depuis SAP (avec pagination)."""
        sap = self._get_sap_service()

        try:
            # --- Charger les clients (avec pagination, limite SAP = 20/requête) ---
            logger.info("Chargement des clients SAP...")
            self._clients_cache = []
            batch_size = 20  # Limite SAP
            skip = 0
            max_clients = 1000  # Limite pour éviter trop de requêtes

            while len(self._clients_cache) < max_clients:
                clients_batch = await sap._call_sap("/BusinessPartners", params={
                    "$filter": "CardType eq 'cCustomer'",
                    "$select": "CardCode,CardName,EmailAddress,Phone1",
                    "$top": batch_size,
                    "$skip": skip,
                    "$orderby": "CardName"
                })

                batch = clients_batch.get("value", [])
                if not batch:
                    break  # Plus de résultats

                self._clients_cache.extend(batch)
                skip += batch_size

                if len(batch) < batch_size:
                    break  # Dernière page

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

            # --- Charger les produits (avec pagination optimisée) ---
            logger.info("Chargement des produits SAP...")
            self._items_cache = {}
            skip = 0
            max_items = 5000  # Limite augmentée
            items_batch_size = 100  # Batch plus grand pour items (plus rapide)

            while len(self._items_cache) < max_items:
                items_batch = await sap._call_sap("/Items", params={
                    "$select": "ItemCode,ItemName",
                    "$top": items_batch_size,
                    "$skip": skip,
                    "$orderby": "ItemCode"
                })

                batch = items_batch.get("value", [])
                if not batch:
                    break

                for item in batch:
                    code = item.get("ItemCode", "")
                    if code:
                        self._items_cache[code] = item

                skip += items_batch_size

                if len(batch) < items_batch_size:
                    break

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

        # Domaine de l'expéditeur (prioritaire sur les domaines des destinataires)
        sender_domain = sender_email.split("@")[-1].lower().strip() if "@" in sender_email else ""
        if self._is_internal_domain(sender_domain):
            sender_domain = ""

        # 2. Matcher les clients
        matched_clients = self._match_clients(full_text, extracted_domains, sender_domain=sender_domain)

        # Meilleur client (pour apprentissage produits)
        best_client = matched_clients[0] if matched_clients else None
        supplier_card_code = best_client.card_code if best_client else None

        # 3. Matcher les produits (avec apprentissage si supplier connu)
        matched_products = self._match_products(full_text, supplier_card_code)

        # 4. Extraire la référence commande client (Form No, PO, etc.)
        customer_ref = extract_customer_reference(full_text)

        return MatchResult(
            clients=matched_clients,
            products=matched_products,
            best_client=best_client,
            extracted_domains=extracted_domains,
            customer_reference=customer_ref,
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

    # Mots communs à ignorer dans le fuzzy matching (faux positifs)
    _BLACKLIST_WORDS = {
        'devis', 'prix', 'price', 'quote', 'demande', 'request', 'offre',
        'bonjour', 'hello', 'merci', 'thanks', 'cordialement', 'regards',
        'urgent', 'rapide', 'quick', 'fast', 'client', 'customer', 'fournisseur',
        'supplier', 'article', 'produit', 'product', 'quantite', 'quantity'
    }

    def _match_clients(
        self,
        text: str,
        extracted_domains: List[str],
        sender_domain: str = ""
    ) -> List[MatchedClient]:
        """Trouve les clients SAP qui matchent le texte de l'email (optimisé avec caches)."""
        matches: List[MatchedClient] = []
        text_normalized = self._normalize(text)

        # Pré-extraire les mots du texte UNE SEULE FOIS (performance)
        text_words_6plus = WORD_PATTERN_6PLUS.findall(text_normalized)
        text_words_4plus = WORD_PATTERN_4PLUS.findall(text_normalized)

        for client in self._clients_cache:
            card_code = client.get("CardCode", "")
            card_name = client.get("CardName", "")
            email = client.get("EmailAddress", "") or ""

            if not card_name:
                continue

            # Récupérer le nom normalisé depuis le cache (au lieu de re-normaliser)
            name_normalized = self._client_normalized.get(card_code, "")

            best_score = 0
            best_reason = ""
            has_domain_match = False
            has_name_match = False

            # --- Stratégie 1 : Match par domaine email (score 95/97) ---
            # Score 97 si le domaine matche l'expéditeur, 95 si destinataire
            if email and "@" in email:
                client_domain = email.split("@")[-1].lower().strip()
                if client_domain in extracted_domains:
                    has_domain_match = True
                    dom_score = 97 if (sender_domain and client_domain == sender_domain) else 95
                    best_score = dom_score
                    best_reason = f"Domaine email {'expéditeur' if dom_score == 97 else 'destinataire'}: {client_domain}"

            # --- Stratégie 1b : Match domaine extrait vs nom client (score 97) ---
            # Si un domaine dans le texte ressemble au nom du client (ex: marmaracam.com.tr vs MARMARA CAM)
            if not has_domain_match and extracted_domains:
                logger.debug(f"[Stratégie 1b] Test pour {card_code} avec domaines: {extracted_domains}")
                name_parts = name_normalized.split()  # Utilise cache au lieu de re-normaliser

                for domain in extracted_domains:
                    # Extraire le nom de l'entreprise du domaine (avant le .com, .fr, etc.)
                    domain_base = domain.split('.')[0]  # marmaracam.com.tr → marmaracam
                    # Domaine expéditeur = prioritaire, domaine destinataire = score réduit
                    is_sender = (sender_domain and domain == sender_domain)

                    # --- Stratégie 1b-acronyme : domaine court = initiales du nom client ---
                    # Ex: meg.com.eg → MEG = M(iddle) E(ast) G(lass) Manufacturing...
                    if 2 <= len(domain_base) <= 5:
                        initials = ''.join(p[0] for p in name_parts if p)
                        # Match exact ou début des initiales (ex: "meg" matche "megm" = MIDDLE EAST GLASS MANUFACTURING)
                        if len(domain_base) >= 2 and (domain_base == initials or initials.startswith(domain_base)):
                            # Score plus élevé si le domaine est celui de l'expéditeur (96 > 95 pour non-sender)
                            acro_score = 96 if is_sender else 72
                            logger.info(f"[Strategie 1b-acronyme] MATCH! {card_code}: initiales '{initials}' starts with '{domain_base}' ({card_name}) sender={is_sender} score={acro_score}")
                            has_domain_match = True
                            best_score = acro_score
                            best_reason = f"Domaine {'expéditeur' if is_sender else 'destinataire'} = initiales client: {domain} ≈ {card_name}"
                            break
                        continue  # Domaine trop court pour matching textuel standard

                    if len(domain_base) < 6:
                        continue

                    # Tester toutes les combinaisons de 1 à 3 mots du nom
                    # Ex: "MARMARA CAM SANAYI" → teste "marmara", "marmaracam", "marmaracamsanayi"
                    for num_words in range(1, min(4, len(name_parts) + 1)):
                        compact_name = ''.join(name_parts[:num_words])

                        # Match exact compact — score réduit si le domaine vient d'un destinataire (pas expéditeur)
                        if compact_name == domain_base:
                            compact_score = 97 if is_sender else 75
                            logger.info(f"[Strategie 1b] MATCH! {card_code}: '{compact_name}' = '{domain_base}' sender={is_sender} -> score {compact_score}")
                            has_domain_match = True
                            best_score = compact_score
                            best_reason = f"Domaine {'expéditeur' if is_sender else 'destinataire'} match nom: {domain} = {' '.join(name_parts[:num_words])}"
                            break

                        # Fuzzy match domaine vs nom compact
                        if len(compact_name) >= 6:
                            ratio = SequenceMatcher(None, domain_base, compact_name).ratio()
                            if ratio > 0.90:  # Seuil plus strict pour éviter faux positifs
                                score = int(92 + (ratio - 0.90) * 50)  # 92-97
                                if not is_sender:
                                    score = min(score, 73)  # Plafonner si non-expéditeur
                                if score > best_score:
                                    has_domain_match = True
                                    best_score = min(score, 97)
                                    best_reason = f"Domaine {'expéditeur' if is_sender else 'destinataire'} match nom fuzzy: {domain} ~ {' '.join(name_parts[:num_words])} ({ratio:.0%})"

                    if has_domain_match and best_score >= 97:
                        break

            # --- Stratégie 2 : CardName exact dans le texte (score 90) ---
            # name_normalized déjà récupéré depuis le cache ci-dessus
            if len(name_normalized) >= 3 and name_normalized in text_normalized:
                has_name_match = True
                if best_score < 90:
                    best_score = 90
                    best_reason = f"Nom exact dans le texte: {card_name}"

            # --- Stratégie 2b : Match version compacte (sans espaces) pour gérer "MarmaraCam" vs "MARMARA CAM" ---
            if best_score < 90:
                name_parts = name_normalized.split()
                words = text_words_6plus  # Utilise mots pré-extraits

                # Créer toutes les combinaisons de 2-4 mots consécutifs du nom client
                # Ex: "MARMARA CAM SANAYI VE" → ["marmaracam", "marmaracamsanayi", "marmaracamsanayive"]
                compact_segments = []
                for start in range(len(name_parts)):
                    for length in range(2, min(5, len(name_parts) - start + 1)):
                        segment = ''.join(name_parts[start:start+length])
                        if len(segment) >= 6:
                            compact_segments.append((segment, ' '.join(name_parts[start:start+length])))

                # Comparer les mots du texte avec les segments compacts
                for word in words:
                    for compact, original in compact_segments:
                        if word == compact:
                            best_score = 88
                            best_reason = f"Match compact exact: '{word}' = '{original}' (sans espaces)"
                            has_name_match = True
                            break
                        # Fuzzy sur segments compacts
                        ratio = SequenceMatcher(None, word, compact).ratio()
                        if ratio > 0.85:
                            score = int(70 + (ratio - 0.85) * 120)  # 70-88
                            if score > best_score:
                                best_score = min(score, 88)
                                best_reason = f"Match compact fuzzy: '{word}' ~ '{original}' ({ratio:.0%})"
                                has_name_match = True
                    if best_score == 88:
                        break

            # --- Bonus combo : Domaine + Nom = 98 (prioritaire) ---
            if has_domain_match and has_name_match:
                best_score = 98
                best_reason = f"Domaine + Nom dans texte: {card_name}"

            # --- Stratégie 3 : Fuzzy match CardName (score 70-85) ---
            if best_score < 70:
                # Utiliser mots pré-extraits et filtrer la blacklist
                words = {w for w in text_words_4plus if w not in self._BLACKLIST_WORDS}
                # name_normalized déjà récupéré depuis le cache ci-dessus

                # Comparer chaque mot du texte avec le nom du client
                for word in words:
                    ratio = SequenceMatcher(None, word, name_normalized).ratio()
                    if ratio > 0.75:
                        score = int(70 + (ratio - 0.75) * 60)  # 70-85
                        if score > best_score:
                            best_score = min(score, 85)
                            best_reason = f"Fuzzy match: '{word}' ~ '{card_name}' ({ratio:.0%})"

                # Aussi comparer avec la première partie du nom (plus permissif)
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

    def _create_matched_product_from_sap(
        self,
        item: Dict[str, Any],
        quantity: int,
        score: int,
        match_reason: str,
        not_found_in_sap: bool = False
    ) -> MatchedProduct:
        """
        Crée un MatchedProduct depuis un item SAP avec tous les champs incluant prix.

        Args:
            item: Dictionnaire item SAP depuis cache
            quantity: Quantité détectée
            score: Score de matching (0-100)
            match_reason: Raison du match
            not_found_in_sap: True si produit non trouvé dans SAP

        Returns:
            MatchedProduct avec prix SAP inclus
        """
        weight_unit_value = item.get("weight_unit_value")
        weight_total = (
            round(weight_unit_value * quantity, 4)
            if weight_unit_value and quantity
            else None
        )

        return MatchedProduct(
            item_code=item.get("ItemCode", ""),
            item_name=item.get("ItemName", ""),
            quantity=quantity,
            score=score,
            match_reason=match_reason,
            not_found_in_sap=not_found_in_sap,
            # Prix depuis SAP (sera utilisé par pricing engine si disponible)
            unit_price=item.get("Price"),  # Prix SAP de base
            supplier_price=item.get("SupplierPrice"),  # Prix fournisseur si disponible
            # Poids depuis cache SAP (SWeight1)
            weight_unit_value=weight_unit_value,
            weight_unit='kg',
            weight_total=weight_total,
        )

    def _match_single_product_intelligent(
        self,
        code: str,
        description: str,
        text: str,
        supplier_card_code: Optional[str] = None
    ) -> Optional[MatchedProduct]:
        """
        Matching intelligent d'un produit avec stratégie en cascade:
        1. Match exact par ItemCode dans SAP
        2. Recherche dans product_mapping_db (apprentissage)
        3. Fuzzy match sur ItemName
        4. Enregistrement comme PENDING si non trouvé

        Args:
            code: Code produit externe (ex: "HST-117-03")
            description: Description du produit (ex: "SIZE 3 PUSHER BLADE")
            text: Texte complet pour extraction quantité
            supplier_card_code: CardCode du fournisseur pour apprentissage

        Returns:
            MatchedProduct ou None
        """
        code_upper = code.upper()
        qty = self._extract_quantity_near(text, code)
        print(f"      🔎 Analyse: {code} (supplier: {supplier_card_code})", flush=True)
        logger.debug(f"[MATCH] Matching code: {code} (supplier: {supplier_card_code})")

        # --- ÉTAPE 1: Match exact par ItemCode ---
        # 1a. Chercher dans le cache mémoire (rapide, 5000 premiers produits)
        if code_upper in self._items_cache:
            item = self._items_cache[code_upper]
            return self._create_matched_product_from_sap(
                item=item,
                quantity=qty,
                score=100,
                match_reason="Code exact SAP (cache)"
            )

        if code in self._items_cache:
            item = self._items_cache[code]
            return self._create_matched_product_from_sap(
                item=item,
                quantity=qty,
                score=100,
                match_reason="Code exact SAP (cache)"
            )

        # --- ÉTAPE 1d: Match par code normalisé (suppression de TOUTE ponctuation) ---
        # Permet P-0301L-SLT == P/0301L-SLT (slash et tiret distincts chez fournisseurs)
        # L'index _items_norm_code est pré-construit dans ensure_cache() sur le 1er token de ItemName
        # IMPORTANT: Doit être testé AVANT le SQLite LIKE (étape 1b) car LIKE '%HST-117-01%'
        # retourne aussi les variantes SSB/TN dans un ordre aléatoire.
        code_norm = normalize_code(code)
        logger.debug("[EXTRACTED_CODE_NORMALIZED] %s → %s", code, code_norm)
        if code_norm and len(code_norm) >= 4 and hasattr(self, '_items_norm_code'):
            matched_sap_code = self._items_norm_code.get(code_norm)
            if matched_sap_code and matched_sap_code in self._items_cache:
                item = self._items_cache[matched_sap_code]
                print(f"         ✅ Code normalisé: {code} → {matched_sap_code} | {item.get('ItemName', '')[:40]}", flush=True)
                logger.info("[FINAL_DECISION] code_exact_normalized: %s → %s (norm=%s)", code, matched_sap_code, code_norm)
                return self._create_matched_product_from_sap(
                    item=item,
                    quantity=qty,
                    score=100,
                    match_reason=f"Code normalisé: {code} → {matched_sap_code}"
                )

        # 1b. Fallback: Chercher dans le cache SQLite (TOUS les produits SAP)
        # Prioritise les articles dont le ItemName COMMENCE par le code (pas juste contient)
        try:
            # D'abord chercher les articles dont le nom commence par le code (plus précis)
            sap_cache_items_prefix = self._cache_db.search_items(code + " ", limit=3)
            sap_cache_items_all = self._cache_db.search_items(code, limit=5)
            # Préférer un match avec espace après le code (ex: "HST-117-01 PUSHER" vs "HST-117-01-SSB")
            sap_cache_items = sap_cache_items_prefix or sap_cache_items_all
            if sap_cache_items:
                # Trier : préférer les items dont le ItemName commence par le code exact
                code_upper_space = (code + " ").upper()
                sap_cache_items.sort(
                    key=lambda i: (0 if i.get("ItemName", "").upper().startswith(code_upper_space) else 1)
                )
                item = sap_cache_items[0]
                print(f"         ✅ Trouvé dans cache SQLite: {code} → {item['ItemName'][:40]}", flush=True)
                logger.debug(f"   [OK] Found in SQLite cache: {code}")
                return self._create_matched_product_from_sap(
                    item=item,
                    quantity=qty,
                    score=100,
                    match_reason="Code exact SAP (base locale)"
                )
        except Exception as e:
            logger.debug(f"   [SQLite fallback] Error: {e}")

        # 1c. Fallback normalisé : chercher sans tirets/espaces (ex: C391-15-LM → C391-15LM-SPARE)
        # Note: ItemCode SAP est une ref interne (A13044), la ref fournisseur est dans ItemName
        try:
            code_normalized = code.replace('-', '').replace(' ', '').upper()
            if code_normalized != code.replace(' ', '').upper():  # Seulement si le code avait des tirets
                sap_cache_items = self._cache_db.search_items_normalized(code, limit=5)
                if sap_cache_items:
                    # Comparer contre ItemName normalisé (la ref fournisseur y est stockée)
                    def _score_item(item):
                        name_norm = item["ItemName"].replace('-', '').replace(' ', '').upper()
                        # Match exact : code normalisé est sous-chaîne du ItemName normalisé
                        # Préférer le nom le plus court (plus spécifique au code)
                        if code_normalized in name_norm:
                            return 1.0 + (1.0 / max(len(name_norm), 1))
                        # Sinon fuzzy
                        return SequenceMatcher(None, code_normalized, name_norm).ratio()

                    best = max(sap_cache_items, key=_score_item)
                    name_norm = best["ItemName"].replace('-', '').replace(' ', '').upper()
                    ic_norm = best["ItemCode"].replace('-', '').replace(' ', '').upper()

                    # Validé si code normalisé est sous-chaîne du nom ou du code
                    if code_normalized in name_norm or code_normalized in ic_norm:
                        score = int(90 * len(code_normalized) / max(len(name_norm), 1))
                        score = max(score, 75)  # Minimum 75 pour un match sous-chaîne confirmé
                        print(f"         ✅ Trouvé (normalisé): {code} → {best['ItemCode']} | {best['ItemName'][:40]}", flush=True)
                        return self._create_matched_product_from_sap(
                            item=best,
                            quantity=qty,
                            score=score,
                            match_reason=f"Ref fournisseur dans ItemName: {code} ~ {best['ItemName'][:40]}"
                        )
        except Exception as e:
            logger.debug(f"   [SQLite normalized fallback] Error: {e}")

        # --- ÉTAPE 2: Recherche dans product_mapping_db (apprentissage) ---
        # Chercher mapping avec supplier_card_code (si fourni) ou GLOBAL
        mapping_db = self._get_mapping_db()
        mapping = mapping_db.get_mapping(code, supplier_card_code)
        print(f"         📋 Mapping trouvé: {mapping.get('matched_item_code') if mapping else 'AUCUN'}", flush=True)
        logger.debug(f"   [MAPPING] Lookup result: {mapping}")

        if mapping and mapping.get("matched_item_code"):
            matched_code = mapping["matched_item_code"]
            print(f"         ✅ Mapping: {code} → {matched_code}", flush=True)
            logger.debug(f"   [OK] Found mapping: {code} -> {matched_code}")

            # Chercher d'abord dans cache mémoire
            if matched_code in self._items_cache:
                item = self._items_cache[matched_code]
                print(f"         ✅ Article en cache: {matched_code}", flush=True)
                logger.debug(f"   [OK] Item found in cache: {matched_code}")
                return self._create_matched_product_from_sap(
                    item=item,
                    quantity=qty,
                    score=95,
                    match_reason=f"Mapping appris ({mapping.get('match_method')})"
                )

            # Fallback: Chercher dans cache SQLite
            try:
                sap_cache_items = self._cache_db.search_items(matched_code, limit=1)
                if sap_cache_items:
                    item = sap_cache_items[0]  # Full dict avec weight_unit_value inclus
                    print(f"         ✅ Article trouvé dans base locale: {matched_code}", flush=True)
                    logger.debug(f"   [OK] Mapped item found in SQLite: {matched_code}")
                    return self._create_matched_product_from_sap(
                        item=item,
                        quantity=qty,
                        score=95,
                        match_reason=f"Mapping appris ({mapping.get('match_method')}) + base locale"
                    )
            except Exception as e:
                logger.debug(f"   [SQLite fallback] Error for mapped item: {e}")

            print(f"         ⚠️ Mapping trouvé MAIS article {matched_code} introuvable!", flush=True)
            logger.warning(f"   [WARNING] Mapping found but item {matched_code} NOT found anywhere!")

        # --- ÉTAPE 3: Fuzzy match sur ItemName avec description ---
        # Stratégie en 2 passes :
        #   3a. SQL multi-token (pré-filtre rapide, ≤50 candidats)
        #   3b. Scoring token_set_ratio (thefuzz) sur les candidats SQL
        #   3c. Fallback sur l'itération mémoire si SQL retourne rien
        if description and len(description) >= 4:
            desc_normalized = normalize_text(description)
            desc_words = set(WORD_PATTERN_4PLUS.findall(desc_normalized))

            best_match = None
            best_score = 0

            logger.info("[SEARCH_QUERY] Étape 3 description='%s'", description[:80])

            # 3a. SQL multi-token : pré-filtre par mots-clés
            cache_db = self._get_cache_db()
            sql_candidates = cache_db.search_items_multitoken(description, limit=50)
            logger.info("[SQL_RESULTS] %d candidats SQL pour description='%s'",
                        len(sql_candidates), description[:60])

            # 3b. Scoring thefuzz token_set_ratio sur candidats SQL
            fuzzy_scores = []
            for candidate in sql_candidates:
                item_name = candidate.get("ItemName", "")
                name_norm = normalize_text(item_name)
                if not name_norm:
                    continue

                # _discriminating_score : token_set_ratio - pénalité mots discriminants
                # (évite PREMIUM == BASIC quand libellés quasi-identiques)
                tsr = _discriminating_score(desc_normalized, name_norm)

                # Bonus substring : si la description est entièrement dans le nom SAP
                if desc_normalized in name_norm or name_norm in desc_normalized:
                    tsr = max(tsr, 85)

                fuzzy_scores.append((tsr, candidate))
                if tsr > best_score:
                    best_score = tsr
                    best_match = (candidate.get("ItemCode", ""), candidate,
                                  f"Token-set ratio SQL ({tsr}%)")

            if fuzzy_scores:
                top3 = sorted(fuzzy_scores, key=lambda x: x[0], reverse=True)[:3]
                logger.info("[FUZZY_SCORES] Top-3: %s",
                            [(s, r.get("ItemCode"), r.get("ItemName", "")[:40])
                             for s, r in top3])

            # 3c. Fallback mémoire si SQL n'a rien retourné
            if not sql_candidates:
                for item_code, item in self._items_cache.items():
                    name_normalized = self._items_normalized.get(item_code, "")
                    if not name_normalized:
                        continue

                    # Substring
                    if desc_normalized in name_normalized or name_normalized in desc_normalized:
                        score = 85
                        if score > best_score:
                            best_score = score
                            best_match = (item_code, item, "Nom similaire (substring)")

                    # SequenceMatcher (fallback)
                    ratio = SequenceMatcher(None, desc_normalized, name_normalized).ratio()
                    if ratio > 0.7:
                        score = int(60 + ratio * 30)
                        if score > best_score:
                            best_score = score
                            best_match = (item_code, item, f"Fuzzy nom ({ratio:.0%})")

                    # Mots communs
                    name_words = set(WORD_PATTERN_4PLUS.findall(name_normalized))
                    common_words = desc_words & name_words
                    if len(common_words) >= 2:
                        match_ratio = len(common_words) / max(len(desc_words), 1)
                        if match_ratio > 0.5:
                            score = int(60 + match_ratio * 20)
                            if score > best_score:
                                best_score = score
                                best_match = (item_code, item,
                                              f"Mots communs: {', '.join(list(common_words)[:2])}")

            logger.info("[FINAL_SELECTION] Étape 3: best_score=%d item=%s",
                        best_score, best_match[0] if best_match else None)

            # Si bon match trouvé (seuil augmenté à 90 pour éviter faux positifs), enregistrer dans mapping_db
            if best_match and best_score >= 90 and supplier_card_code:
                item_code, item, reason = best_match
                mapping_db = self._get_mapping_db()
                mapping_db.save_mapping(
                    external_code=code,
                    external_description=description,
                    supplier_card_code=supplier_card_code,
                    matched_item_code=item_code,
                    match_method="FUZZY_NAME",
                    confidence_score=best_score,
                    status="VALIDATED"  # Score >= 90 → auto-validé
                )

                return self._create_matched_product_from_sap(
                    item=item,
                    quantity=qty,
                    score=best_score,
                    match_reason=reason
                )

        # --- ÉTAPE 4: Non trouvé - Enregistrer comme PENDING ---
        if supplier_card_code:
            mapping_db = self._get_mapping_db()
            mapping_db.save_mapping(
                external_code=code,
                external_description=description or "",
                supplier_card_code=supplier_card_code,
                matched_item_code=None,
                match_method="PENDING",
                confidence_score=0.0,
                status="PENDING"
            )

        # Retourner le code externe avec flag not_found_in_sap
        return MatchedProduct(
            item_code=code,
            item_name=description or f"Produit externe {code}",
            quantity=qty,
            score=0,
            match_reason="Non trouvé SAP - À valider",
            not_found_in_sap=True
        )

    def _extract_product_descriptions(self, text: str) -> Dict[str, str]:
        """
        Extrait les descriptions associées aux codes produits.
        Cherche des patterns comme:
        - "SHEPPEE CODE: HST-117-03 - SIZE 3 PUSHER BLADE"
        - "Row 1: HST-117-03 - SIZE 3 PUSHER BLADE - 50 Adet"
        - "Material Name: SIZE 3 PUSHER BLADE   Material Detail: CODE HST-117-03"

        Returns:
            Dict {code: description}
        """
        descriptions = {}

        # Pattern 1: "SHEPPEE CODE: XXX - DESCRIPTION" (format PDF Marmara Cam)
        pattern1 = re.findall(
            r'(?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]{3,})\s*[-–]\s*([^-\n]+?)(?:\s*[-–]|\n|SHEPPEE|DRAWING)',
            text,
            re.IGNORECASE
        )
        for code, desc in pattern1:
            code = code.strip()
            desc = desc.strip()
            if code and desc and len(desc) > 3:
                descriptions[code] = desc[:200]

        # Pattern 2: "Row X: CODE - DESCRIPTION" (format tableau)
        pattern2 = re.findall(
            r'Row\s+\d+:\s*([A-Z0-9-]{3,})\s*[-–]\s*([^-\n]+?)(?:\s*[-–]|SHEPPEE|$)',
            text,
            re.IGNORECASE
        )
        for code, desc in pattern2:
            code = code.strip()
            desc = desc.strip()
            if code and desc and len(desc) > 3:
                descriptions[code] = desc[:200]

        # Pattern 3: "Material Name: DESC   Material Detail: CODE XXX"
        pattern3 = re.findall(
            r'Material\s+Name:\s*([^\n]+?)\s+Material\s+Detail:\s*.*?([A-Z0-9-]{3,})',
            text,
            re.IGNORECASE
        )
        for desc, code in pattern3:
            code = code.strip()
            desc = desc.strip()
            if code and desc and len(desc) > 3:
                descriptions[code] = desc[:200]

        logger.info(f"Extracted {len(descriptions)} product descriptions")
        for code, desc in list(descriptions.items())[:5]:
            logger.info(f"  {code}: {desc[:60]}")

        return descriptions

    def _is_phone_number(self, code: str) -> bool:
        """Détecte si un code ressemble à un numéro de téléphone ou fax."""
        # Numéros français : 10 chiffres commençant par 0, ou 9 chiffres commençant par 1-9
        if len(code) == 10 and code[0] == '0':
            return True
        if len(code) == 9 and code[0] in '123456789':
            return True

        # Numéros internationaux : 11-15 chiffres avec préfixe pays (33, 44, 1, 90, etc.)
        if 11 <= len(code) <= 15:
            # Format français international : 33 suivi de 9 chiffres
            if code.startswith('33') and len(code) == 11:
                return True
            # Autres préfixes courants (ajout Turquie 90, USA/Canada 1)
            if code.startswith(('44', '41', '49', '39', '34', '351', '352', '1', '90')):
                return True

        # Patterns téléphone : répétitions de paires (ex: 334446...)
        if len(code) >= 10:
            # Détecter les patterns de numéros (groupes de 2 chiffres similaires)
            pairs = [code[i:i+2] for i in range(0, len(code)-1, 2)]
            # Si plus de 3 paires et certaines se répètent, probablement un téléphone
            if len(pairs) >= 4:
                unique_pairs = set(pairs)
                if len(unique_pairs) <= len(pairs) * 0.6:  # 60% de répétition
                    return True

        # NOUVEAU: Numéros très longs (>= 11 chiffres purement numériques) sont probablement des téléphones/fax
        # Les vrais codes produits ont rarement plus de 10 chiffres purement numériques
        if code.isdigit() and len(code) >= 11:
            return True

        return False

    def _match_products(self, text: str, supplier_card_code: Optional[str] = None) -> List[MatchedProduct]:
        """
        Trouve les produits SAP par code OU par nom (intelligent matching).
        Stratégie en cascade : code exact → apprentissage → fuzzy nom → enregistrement.

        Args:
            text: Texte complet (email + PDF)
            supplier_card_code: CardCode du fournisseur pour apprentissage
        """
        print(f"\n{'='*80}\n🔍 _MATCH_PRODUCTS APPELÉ - supplier_card_code: {supplier_card_code}\n{'='*80}\n", flush=True)
        matches: List[MatchedProduct] = []
        matched_codes = set()
        text_normalized = self._normalize(text)

        # ===== PHASE 0 : EXTRACTION DESCRIPTIONS (pour apprentissage) =====
        product_descriptions = self._extract_product_descriptions(text)
        logger.info(f"Extracted {len(product_descriptions)} product descriptions from text")

        # ===== PHASE 0B : CHEMIN OFFER REQUEST FORM (Row N + Adet strict) =====
        # Si le document est un "Offer Request Form" (format Marmara Cam 26576), on utilise
        # une extraction structurée : quantité UNIQUEMENT via pattern "nombre Adet" (strict).
        # Aucune valeur technique (ex: DİŞ SAYISI: 194) ne peut être confondue avec une quantité.
        offer_rows = self._extract_offer_request_rows(text)
        if offer_rows:
            print(f"📋 FORMAT OFFER REQUEST FORM DÉTECTÉ — {len(offer_rows)} lignes Row+Adet", flush=True)
            logger.info(f"[OFFER REQUEST] Chemin structuré activé ({len(offer_rows)} lignes)")
            offer_matches: List[MatchedProduct] = []
            offer_matched_codes: set = set()
            for row in offer_rows:  # déjà triés par row_no
                code = row['code']
                if code.upper() in offer_matched_codes:
                    continue
                product = self._match_single_product_intelligent(
                    code=code,
                    description=row['description'],
                    text=text,
                    supplier_card_code=supplier_card_code,
                )
                if product is None:
                    # Non trouvé dans SAP : créer entrée pending avec quantité Adet
                    product = MatchedProduct(
                        item_code=code,
                        item_name=row['description'] or f"Produit externe {code}",
                        quantity=row['quantity'],
                        score=50,
                        match_reason="Référence détectée (Offer Request Form) — non trouvée dans SAP",
                        not_found_in_sap=True,
                        row_no=row['row_no'],
                    )
                else:
                    # Forcer la quantité Adet (prioritaire sur _extract_quantity_near)
                    product = product.model_copy(update={
                        'quantity': row['quantity'],
                        'row_no': row['row_no'],
                    })
                offer_matches.append(product)
                offer_matched_codes.add(code.upper())

            # Tri final par row_no (ordre du document source)
            offer_matches.sort(key=lambda m: (m.row_no or 0))
            print(f"✅ OFFER REQUEST: {len(offer_matches)} produits, triés par Row No", flush=True)
            return offer_matches

        # ===== PHASE 1 : MATCHING PAR CODE (ItemCode) avec apprentissage =====

        # Extraire tous les tokens potentiels (codes produits)
        # Pattern 1: Codes numériques longs (6+ chiffres)
        potential_codes = set(re.findall(r'\b(\d{6,})\b', text))

        # Pattern 2: Codes alphanumériques avec tirets (ex: HST-117-03, TRI-037, C315-6305RS)
        potential_codes |= set(re.findall(r'\b([A-Z]{1,4}-[A-Z0-9-]+)\b', text, re.IGNORECASE))

        # Pattern 3: Codes alphanumériques sans tirets (ex: C0249, ABC123)
        potential_codes |= set(re.findall(r'\b([A-Z]{1,4}\d{3,}[A-Z0-9]*)\b', text, re.IGNORECASE))

        # Pattern 4: SHEPPEE CODE: XXX ou CODE: XXX
        potential_codes |= set(re.findall(r'(?:SHEPPEE\s+)?CODE:\s*([A-Z0-9-]+)', text, re.IGNORECASE))

        # Filtrer les numéros de téléphone et mots génériques
        excluded_words = {
            # Mots génériques existants
            'SHEPPEE', 'CODE', 'DRAWING', 'PUSHER', 'BEARING', 'ROLLER', 'CARBON', 'BLADE',
            # Termes machines (anglais)
            'X-AXIS', 'Y-AXIS', 'Z-AXIS', 'XAXIS', 'YAXIS', 'ZAXIS',
            'A-AXIS', 'B-AXIS', 'C-AXIS', 'AAXIS', 'BAXIS', 'CAXIS',
            # Termes machines (turc) - IMPORTANT: Inclure les 2 variantes du caractère İ (I avec point)
            'X-EKSENI', 'Y-EKSENI', 'Z-EKSENI', 'XEKSENI', 'YEKSENI', 'ZEKSENI', 'EKSENI',
            'X-EKSENİ', 'Y-EKSENİ', 'Z-EKSENİ', 'XEKSENİ', 'YEKSENİ', 'ZEKSENİ', 'EKSENİ',  # Variante avec İ turc
            # Mots courants français
            'CI-JOINT', 'CIJOINT', 'CI-JOINTS', 'CIJOINTS',
            'EN-PIECE', 'ENPIECE', 'EN-PIECES', 'ENPIECES',
            # Mots courants anglais
            'ATTACHED', 'ATTACHMENT', 'SKETCH', 'SKETCHES',
            # Termes génériques
            'PIECE', 'PIECES', 'PART', 'PARTS', 'ITEM', 'ITEMS', 'REF', 'REFERENCE',
            # Artifacts de mise en forme email (évite faux positifs comme "E-mail" → CREMAILLERE)
            'E-MAIL', 'E-COMMERCE', 'WI-FI', 'E-LEARNING', 'E-SHOP',
            'T-SHIRT', 'T-SHIRTS', 'V-NECK',
        }
        potential_codes = {
            code for code in potential_codes
            if not self._is_phone_number(code) and code.upper() not in excluded_words
        }

        # Filtrer les doublons en gardant la version la plus longue
        # Ex: si "C315" et "C315-6305RS" existent, garder "C315-6305RS"
        filtered_codes = set()
        for code in sorted(potential_codes, key=len, reverse=True):
            # Vérifier si ce code n'est pas un préfixe d'un code déjà ajouté
            if not any(code in longer_code and code != longer_code for longer_code in filtered_codes):
                filtered_codes.add(code)

        potential_codes = filtered_codes
        print(f"📦 CODES EXTRAITS ({len(potential_codes)}): {list(potential_codes)[:20]}\n", flush=True)
        logger.info(f"Extracted {len(potential_codes)} potential product codes: {list(potential_codes)[:10]}")

        # Utiliser matching intelligent pour chaque code
        for code in potential_codes:
            if code in matched_codes or code.upper() in matched_codes:
                continue

            description = product_descriptions.get(code, "")
            matched_product = self._match_single_product_intelligent(
                code=code,
                description=description,
                text=text,
                supplier_card_code=supplier_card_code
            )

            if matched_product:
                print(f"   ✅ MATCH TROUVÉ: {code} → {matched_product.item_code} (score: {matched_product.score})\n", flush=True)
                matches.append(matched_product)
                matched_codes.add(code)
                matched_codes.add(code.upper())
                if matched_product.score >= 100:
                    # Match exact, pas besoin de chercher les variantes
                    continue
            else:
                print(f"   ❌ PAS DE MATCH: {code}\n", flush=True)

        # Si des produits ont été trouvés via matching intelligent, on retourne
        if matches:
            # Trier par score décroissant
            matches.sort(key=lambda m: m.score, reverse=True)
            return matches

        # ===== FALLBACK : MATCHING CLASSIQUE (si aucun code avec description) =====

        for code in potential_codes:
            if code in matched_codes or code.upper() in matched_codes:
                continue

            code_upper = code.upper()

            # --- Stratégie 1 : ItemCode exact (score 100) ---
            if code_upper in self._items_cache:
                if code_upper not in matched_codes:
                    item = self._items_cache[code_upper]
                    qty = self._extract_quantity_near(text, code)
                    matches.append(self._create_matched_product_from_sap(
                        item=item,
                        quantity=qty,
                        score=100,
                        match_reason=f"Code exact: {code_upper}"
                    ))
                    matched_codes.add(code_upper)
                continue

            # --- Stratégie 2 : ItemCode exact (case-sensitive) ---
            if code in self._items_cache:
                if code not in matched_codes:
                    item = self._items_cache[code]
                    qty = self._extract_quantity_near(text, code)
                    matches.append(self._create_matched_product_from_sap(
                        item=item,
                        quantity=qty,
                        score=100,
                        match_reason=f"Code exact: {code}"
                    ))
                    matched_codes.add(code)
                continue

            # --- Stratégie 2bis : code normalisé (P-0301L-SLT == P/0301L-SLT) ---
            code_norm = normalize_code(code)
            if code_norm and len(code_norm) >= 4 and hasattr(self, '_items_norm_code'):
                matched_sap_code = self._items_norm_code.get(code_norm)
                if matched_sap_code and matched_sap_code not in matched_codes:
                    item = self._items_cache[matched_sap_code]
                    qty = self._extract_quantity_near(text, code)
                    matches.append(self._create_matched_product_from_sap(
                        item=item,
                        quantity=qty,
                        score=100,
                        match_reason=f"Code normalisé: {code} → {matched_sap_code}"
                    ))
                    matched_codes.add(matched_sap_code)
                    continue

            # --- Stratégie 3 : ItemCode partiel (score 80) ---
            if len(code) >= 6:
                for item_code, item in self._items_cache.items():
                    if item_code.startswith(code_upper) or code_upper.startswith(item_code):
                        if item_code not in matched_codes:
                            qty = self._extract_quantity_near(text, code)
                            matches.append(self._create_matched_product_from_sap(
                                item=item,
                                quantity=qty,
                                score=80,
                                match_reason=f"Code partiel: {code} ~ {item_code}"
                            ))
                            matched_codes.add(item_code)
                        break

        # ===== PHASE 2 : MATCHING PAR NOM (ItemName) =====

        for item_code, item in self._items_cache.items():
            if item_code in matched_codes:
                continue  # Déjà trouvé par code

            item_name = item.get("ItemName", "")
            if not item_name or len(item_name) < 3:
                continue

            best_score = 0
            best_reason = ""

            # --- Stratégie 4 : ItemName exact dans le texte (score 90) ---
            name_normalized = self._normalize(item_name)
            if len(name_normalized) >= 4 and name_normalized in text_normalized:
                best_score = 90
                best_reason = f"Nom exact: {item_name}"

            # --- Stratégie 5 : Fuzzy match sur ItemName (score 70-85) ---
            if best_score < 70:
                # Extraire les mots significatifs du texte (>= 4 chars)
                words = set(re.findall(r'\b\w{4,}\b', text_normalized))

                # Comparer avec le nom du produit
                for word in words:
                    ratio = SequenceMatcher(None, word, name_normalized).ratio()
                    if ratio > 0.75:
                        score = int(70 + (ratio - 0.75) * 60)  # 70-85
                        if score > best_score:
                            best_score = min(score, 85)
                            best_reason = f"Fuzzy nom: '{word}' ~ '{item_name}' ({ratio:.0%})"

                # Comparer aussi les mots du nom de produit vs texte
                name_words = set(re.findall(r'\b\w{4,}\b', name_normalized))
                for name_word in name_words:
                    for text_word in words:
                        ratio = SequenceMatcher(None, name_word, text_word).ratio()
                        if ratio > 0.80:
                            score = int(68 + (ratio - 0.80) * 50)  # 68-78
                            if score > best_score:
                                best_score = min(score, 78)
                                best_reason = f"Fuzzy mot: '{text_word}' ~ '{name_word}' ({ratio:.0%})"

            # --- Stratégie 6 : Keywords match (score 65-75) ---
            if best_score < 65:
                # Mots-clés importants du nom de produit (>= 5 chars)
                keywords = set(re.findall(r'\b\w{5,}\b', name_normalized))
                words_in_text = set(re.findall(r'\b\w{4,}\b', text_normalized))

                common_words = keywords & words_in_text
                if common_words:
                    # Score proportionnel au nombre de mots communs
                    match_ratio = len(common_words) / max(len(keywords), 1)
                    if match_ratio > 0.5:
                        score = int(65 + match_ratio * 10)  # 65-75
                        best_score = min(score, 75)
                        best_reason = f"Mots-clés: {', '.join(list(common_words)[:3])}"

            # Ajouter si score suffisant
            if best_score >= 65:
                qty = self._extract_quantity_near(text, item_name)
                if qty == 1:  # Pas de qté trouvée par nom, chercher globalement
                    qty = self._extract_quantity_global(text)

                matches.append(self._create_matched_product_from_sap(
                    item=item,
                    quantity=qty,
                    score=best_score,
                    match_reason=best_reason
                ))
                matched_codes.add(item_code)

        # ===== PHASE 2bis : MATCHING PAR DESCRIPTION LONGUE (SQL multi-token + thefuzz) =====
        #
        # Objectif : matcher "HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        # contre "PYROMETRE HANDY VII PREMIUM + STATION DE CHARGE FIXE AVEC COMPENSATION DE FIBRE"
        # même si aucun code produit n'a été extrait.
        #
        # Stratégie :
        #   1. Extraire les séquences de mots significatifs (3+ mots de 3+ chars) du texte
        #   2. Pour chaque séquence, lancer un SQL multi-token (pré-filtre)
        #   3. Scorer avec token_set_ratio (thefuzz) — insensible à l'ordre et aux préfixes
        #   4. Seuils : >= 85 = auto, 65-84 = suggestion
        #
        # Seule condition d'activation : au moins une séquence longue extraite du texte.

        cache_db = self._get_cache_db()

        # Extraire des séquences de mots pertinentes du texte
        # Pattern : séquence d'au moins 3 mots de 3+ chars (pour éviter les faux positifs)
        long_sequences = re.findall(
            r'(?:(?:\b\w{3,}\b\s+){2,}\b\w{3,}\b)',
            text_normalized
        )
        # Dédupliquer et garder les séquences longues (>= 15 chars)
        seen_seqs: set = set()
        unique_seqs = []
        for seq in long_sequences:
            seq = seq.strip()
            if len(seq) >= 15 and seq not in seen_seqs:
                seen_seqs.add(seq)
                unique_seqs.append(seq)
        # Limiter à 5 séquences les plus longues (performance)
        unique_seqs.sort(key=len, reverse=True)
        unique_seqs = unique_seqs[:5]

        if unique_seqs:
            logger.info("[SEARCH_QUERY] Phase 2bis: %d séquences, ex: '%s'",
                        len(unique_seqs), unique_seqs[0][:60])

        # item_code → (score, item, reason) — inclut les items DÉJÀ dans matches
        # (pour permettre la mise à jour de score si Phase 2bis trouve mieux)
        phase2bis_best: Dict[str, Any] = {}

        for seq in unique_seqs:
            sql_candidates = cache_db.search_items_multitoken(seq, limit=50)
            logger.debug("[SQL_RESULTS] Phase 2bis seq='%s' → %d candidats",
                         seq[:40], len(sql_candidates))

            for candidate in sql_candidates:
                item_code = candidate.get("ItemCode", "")
                if not item_code:
                    continue

                item_name = candidate.get("ItemName", "")
                name_norm = normalize_text(item_name)

                tsr = _discriminating_score(seq, name_norm)

                # Bonus substring
                if seq in name_norm or name_norm in seq:
                    tsr = max(tsr, 88)

                prev = phase2bis_best.get(item_code, (0, None, ""))
                if tsr > prev[0]:
                    phase2bis_best[item_code] = (tsr, candidate, f"Token-set ratio ({tsr}%)")

        # Trier par score et appliquer les seuils
        sorted_phase2bis = sorted(phase2bis_best.items(),
                                  key=lambda kv: kv[1][0], reverse=True)

        logger.info("[FUZZY_SCORES] Phase 2bis top-5: %s",
                    [(code, sc, r.get("ItemName", "")[:40])
                     for code, (sc, r, _) in sorted_phase2bis[:5]])

        added_2bis = 0
        for item_code, (score, item, reason) in sorted_phase2bis:
            if score < 65:
                break  # Liste triée, on peut s'arrêter

            # Vérifier si cet item est déjà dans matches (Phase 2 l'a peut-être trouvé avec un score plus bas)
            existing_idx = next(
                (i for i, m in enumerate(matches) if m.item_code == item_code), None
            )
            if existing_idx is not None:
                # Mettre à jour le score si Phase 2bis a trouvé mieux
                if score > matches[existing_idx].score:
                    decision_reason = (f"Auto-match description ({score}%)"
                                       if score >= 85
                                       else f"Suggestion description ({score}%)")
                    matches[existing_idx] = matches[existing_idx].model_copy(
                        update={"score": score, "match_reason": decision_reason}
                    )
                    logger.info("[FINAL_SELECTION] Phase 2bis: UPDATE %s score %d→%d",
                                item_code, matches[existing_idx].score, score)
                continue  # Ne pas ajouter en doublon

            if item_code in matched_codes:
                continue

            qty = self._extract_quantity_global(text)

            # Décision selon seuil
            if score >= 85:
                decision_reason = f"Auto-match description ({score}%)"
            else:
                decision_reason = f"Suggestion description ({score}%)"

            matches.append(self._create_matched_product_from_sap(
                item=item,
                quantity=qty,
                score=score,
                match_reason=decision_reason,
            ))
            matched_codes.add(item_code)
            added_2bis += 1

            logger.info("[FINAL_SELECTION] Phase 2bis: %s '%s' score=%d",
                        item_code, item.get("ItemName", "")[:50], score)

            if added_2bis >= 5:
                break  # Limiter à 5 résultats par phase 2bis

        # ===== REVALIDATION DES AUTO-MATCHES POST-PHASE 2bis =====
        # Problème : le bonus substring (tsr = max(tsr, 88)) peut promouvoir à tort
        # des variantes concurrentes en auto-match via une séquence GÉNÉRIQUE
        # (ex: "charge fixe avec compensation" présent dans TOUTES les variantes HANDY VII).
        # Solution : re-valider chaque auto-match avec _discriminating_score sur le TEXTE
        # COMPLET de l'email. Si le score de revalidation est < 85, on déclasse en suggestion.
        text_full_norm = normalize_text(text)
        for i, m in enumerate(matches):
            if m.score >= 85:
                full_disc = _discriminating_score(text_full_norm, normalize_text(m.item_name or ""))
                if full_disc < 85:
                    logger.info(
                        "[REVALIDATION] %s '%s' déclassé: score_phase2bis=%d → disc_full=%d",
                        m.item_code, (m.item_name or "")[:40], m.score, full_disc
                    )
                    matches[i] = m.model_copy(update={
                        "score": full_disc,
                        "match_reason": f"Suggestion (revalidation disc: {full_disc}%)"
                    })

        # ===== NETTOYAGE POST-PHASE 2bis =====
        # Problème : Phase 2 (mot-à-mot) génère de nombreuses suggestions via des mots
        # génériques communs (ex: "avec", "pour") qui apparaissent à la fois dans le texte
        # de l'email ET dans de nombreux libellés SAP. Ces suggestions sont du bruit.
        #
        # Solution : si des auto-matches (≥85) existent après revalidation, supprimer
        # TOUTES les suggestions (<85). Les vrais produits demandés sont trouvés en
        # auto-match par Phase 2bis ; les suggestions restantes sont de faux positifs.
        auto_matches = [m for m in matches if m.score >= 85]
        if auto_matches:
            suggestions_suppressed = len([m for m in matches if m.score < 85])
            if suggestions_suppressed > 0:
                logger.info(
                    "[CLEANUP] %d auto-match(s) trouvé(s) → suppression de %d suggestion(s) (bruit Phase 2)",
                    len(auto_matches), suggestions_suppressed
                )
            matches = auto_matches

        # ===== PHASE 3 : CODES NON TROUVÉS DANS SAP =====
        # Ajouter les codes détectés mais absents de SAP
        for code in potential_codes:
            code_upper = code.upper()
            if code_upper not in matched_codes and code not in matched_codes:
                # Extraire la quantité même si le produit n'existe pas
                qty = self._extract_quantity_near(text, code)
                matches.append(MatchedProduct(
                    item_code=code,
                    item_name=f"[NON TROUVÉ DANS SAP]",
                    quantity=qty,
                    score=50,  # Score bas pour indiquer qu'il faut vérifier
                    match_reason="Référence détectée mais non trouvée dans SAP",
                    not_found_in_sap=True
                ))
                matched_codes.add(code)

        # Trier par score décroissant
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:10]  # Top 10 maximum

    # --- Extraction structurée Offer Request Form ---

    # Pattern interne pour matcher une ligne "Row N: CODE - DESC - QTY Adet"
    _OFFER_ROW_PATTERN = re.compile(
        r'Row\s+(\d+)\s*:\s*'                  # Row N:
        r'([A-Z0-9][A-Z0-9\-\.]+)\s*'          # CODE (ex: HST-117-03, C233-50AT10-1940G3)
        r'[-–]\s*'                              # séparateur
        r'(.+?)\s*'                             # DESCRIPTION (non-greedy)
        r'\b(\d+(?:[.,]\d+)?)\s*Adet\b',       # QTY Adet (STRICT — pas de fallback)
        re.IGNORECASE,
    )

    def _extract_offer_request_rows(self, text: str) -> List[Dict[str, Any]]:
        """
        Extrait les lignes structurées d'un document 'Offer Request Form'.

        Format attendu : 'Row <N>: <CODE> - <DESCRIPTION> - <QTY> Adet'

        RÈGLE MÉTIER : La quantité est détectée UNIQUEMENT via le pattern strict
        'nombre Adet'. Aucun fallback sur d'autres valeurs numériques du texte.

        Garde-fou : quantité > 50 sur une ligne autre que Row 1 → warning + vérification.

        Returns:
            Liste triée par row_no : [{'row_no': int, 'code': str, 'description': str, 'quantity': int}]
            Liste vide si le texte n'est pas au format Offer Request Form.
        """
        # Pré-condition : le texte doit contenir au moins une ligne "Row N:"
        if not re.search(r'Row\s+\d+\s*:', text, re.IGNORECASE):
            return []

        rows = []
        for m in self._OFFER_ROW_PATTERN.finditer(text):
            row_no = int(m.group(1))
            code = m.group(2).strip()
            description = m.group(3).strip().rstrip('-–').strip()
            qty_str = m.group(4).replace(',', '.')
            quantity = int(float(qty_str))

            # Garde-fou : quantité suspecte sur ligne non-première
            if quantity > 50 and row_no != 1:
                logger.warning(
                    f"[ADET GUARD] Row {row_no}: quantité suspicieusement élevée ({quantity}) "
                    f"pour code {code} — mot 'Adet' confirmé dans le contexte, ligne acceptée."
                )

            rows.append({
                'row_no': row_no,
                'code': code,
                'description': description,
                'quantity': quantity,
            })

        rows.sort(key=lambda r: r['row_no'])
        logger.info(f"[OFFER REQUEST] {len(rows)} lignes extraites (quantités strictes Adet)")
        return rows

    # --- Extraction de quantité contextuelle ---

    # Mots-clés précédant un deux-points qui indiquent un n° de dessin/référence (pas une quantité)
    _DRAWING_KEYWORDS = {
        'drawing', 'dwg', 'plan', 'dessin', 'ref', 'reference', 'fig', 'figure',
        'folio', 'item no', 'item number', 'part no', 'part number', 'no', 'n°',
        'revision', 'rev', 'sheet', 'page', 'pos', 'position', 'index', 'serie',
        'serial', 'numéro', 'numero',
    }

    def _extract_quantity_near(self, text: str, code: str, radius: int = 200) -> int:
        """Extrait la quantité mentionnée près d'un code produit."""
        # Trouver la première occurrence du code dans le texte
        idx = text.find(code)
        if idx == -1:
            idx = text.lower().find(code.lower())
        if idx == -1:
            return 1  # Défaut

        # --- Stratégie 0 : nombre sur la MÊME LIGNE que le code (format tableau) ---
        # Ex: "HST-117-01\tSize 01 Pusher Pad\t48\n" → 48
        line_start = text.rfind('\n', 0, idx) + 1  # Début de la ligne
        line_end = text.find('\n', idx)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        # Portion de la ligne APRÈS le code (évite les chiffres dans le code lui-même)
        code_pos_in_line = line.find(code)
        if code_pos_in_line == -1:
            code_pos_in_line = line.lower().find(code.lower())
        after_code = line[code_pos_in_line + len(code):] if code_pos_in_line >= 0 else ""

        def _is_valid_qty(n: int) -> bool:
            """Vérifie que n est une quantité plausible (pas une année, pas trop grand)."""
            return 0 < n < 10000 and not (1990 <= n <= 2050)

        # 0a. Priorité : nombre précédé d'un \t (colonne QTY dans un tableau tab-séparé)
        tab_qty = re.search(r'\t(\d+)\s*$', after_code.rstrip())
        if tab_qty:
            try:
                qty = int(tab_qty.group(1))
                if _is_valid_qty(qty):
                    return qty
            except (ValueError, IndexError):
                pass

        # 0b. Nombre seul en fin de ligne (séparé par espace ou tab, ex: "...Pad  48")
        end_qty = re.search(r'[\t ]+(\d+)\s*$', after_code.rstrip())
        if end_qty:
            try:
                qty = int(end_qty.group(1))
                if _is_valid_qty(qty):
                    return qty
            except (ValueError, IndexError):
                pass

        # Extraire le contexte autour du code (rayon élargi)
        start = max(0, idx - radius)
        end = min(len(text), idx + len(code) + radius)
        context = text[start:end]

        # Patterns de quantité (du plus spécifique au plus général)
        qty_patterns = [
            r'qt[eéy]\s*[:\s]*(\d+)',
            r'quantit[eé]\s*[:\s]*(\d+)',
            r'(\d+)\s*(?:pcs|pi[eè]ces?|unit[eé]s?|adet|stk|stück)',  # incl. Adet (turc)
            r'x\s*(\d+)',
        ]

        for pattern in qty_patterns:
            match = re.search(pattern, context, re.IGNORECASE)
            if match:
                try:
                    qty = int(match.group(1))
                    if 0 < qty < 100000:
                        return qty
                except (ValueError, IndexError):
                    pass

        # Dernier recours : nombre après deux-points, sauf si précédé d'un mot de dessin/référence
        for m in re.finditer(r':\s*(\d+)\b', context, re.IGNORECASE):
            pre = context[max(0, m.start() - 30):m.start()].lower()
            pre = re.sub(r'[^\w\s]', ' ', pre)  # Normaliser
            if not any(kw in pre for kw in self._DRAWING_KEYWORDS):
                try:
                    qty = int(m.group(1))
                    if 0 < qty < 100000:
                        return qty
                except (ValueError, IndexError):
                    pass

        return 1  # Défaut

    def _extract_quantity_global(self, text: str) -> int:
        """Extrait la quantité globale mentionnée dans le texte (fallback)."""
        qty_patterns = [
            r'qt[eéy]\s*[:\s]*(\d+)',
            r'quantit[eé]\s*[:\s]*(\d+)',
            r'(\d+)\s*(?:pcs|pièces?|units?|unités?|adet|stk|stück)',
            r'x\s*(\d+)',
        ]

        for pattern in qty_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
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
    @lru_cache(maxsize=2048)  # Cache 2048 chaînes normalisées
    def _normalize(text: str) -> str:
        """Normalise un texte pour la comparaison fuzzy (avec cache LRU)."""
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
