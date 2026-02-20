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

logger = logging.getLogger(__name__)

# --- Regex pré-compilés pour performance ---
WORD_PATTERN_4PLUS = re.compile(r'\b\w{4,}\b')  # Mots 4+ caractères
WORD_PATTERN_6PLUS = re.compile(r'\b\w{6,}\b')  # Mots 6+ caractères
EMAIL_PATTERN = re.compile(r'[\w._%+-]+@([\w.-]+\.\w{2,})', re.IGNORECASE)
MAILTO_PATTERN = re.compile(r'mailto:([\w._%+-]+@([\w.-]+\.\w{2,}))', re.IGNORECASE)


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
    last_sale_date: Optional[str] = None  # Date dernière vente
    average_price_others: Optional[float] = None  # Prix moyen autres clients (CAS 3)


class MatchResult(BaseModel):
    clients: List[MatchedClient] = []
    products: List[MatchedProduct] = []
    best_client: Optional[MatchedClient] = None
    extracted_domains: List[str] = []


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

            logger.info(f"[OK] Produits charges: {len(self._items_cache)} "
                        f"({len(self._items_normalized)} noms normalisés)")

        except Exception as e:
            logger.error(f"Erreur chargement cache SQLite: {e}")
            # Fallback: initialiser avec des listes vides
            self._clients_cache = []
            self._items_cache = {}
            self._client_domains = {}

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

        # 2. Matcher les clients
        matched_clients = self._match_clients(full_text, extracted_domains)

        # Meilleur client (pour apprentissage produits)
        best_client = matched_clients[0] if matched_clients else None
        supplier_card_code = best_client.card_code if best_client else None

        # 3. Matcher les produits (avec apprentissage si supplier connu)
        matched_products = self._match_products(full_text, supplier_card_code)

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
        extracted_domains: List[str]
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

            # --- Stratégie 1 : Match par domaine email (score 95) ---
            if email and "@" in email:
                client_domain = email.split("@")[-1].lower().strip()
                if client_domain in extracted_domains:
                    has_domain_match = True
                    best_score = 95
                    best_reason = f"Domaine email: {client_domain}"

            # --- Stratégie 1b : Match domaine extrait vs nom client (score 97) ---
            # Si un domaine dans le texte ressemble au nom du client (ex: marmaracam.com.tr vs MARMARA CAM)
            if not has_domain_match and extracted_domains:
                logger.debug(f"[Stratégie 1b] Test pour {card_code} avec domaines: {extracted_domains}")
                name_parts = name_normalized.split()  # Utilise cache au lieu de re-normaliser

                for domain in extracted_domains:
                    # Extraire le nom de l'entreprise du domaine (avant le .com, .fr, etc.)
                    domain_base = domain.split('.')[0]  # marmaracam.com.tr → marmaracam

                    if len(domain_base) < 6:
                        continue

                    # Tester toutes les combinaisons de 1 à 3 mots du nom
                    # Ex: "MARMARA CAM SANAYI" → teste "marmara", "marmaracam", "marmaracamsanayi"
                    for num_words in range(1, min(4, len(name_parts) + 1)):
                        compact_name = ''.join(name_parts[:num_words])

                        # Match exact compact
                        if compact_name == domain_base:
                            logger.info(f"[Strategie 1b] MATCH! {card_code}: '{compact_name}' = '{domain_base}' -> score 97")
                            has_domain_match = True
                            best_score = 97
                            best_reason = f"Domaine match nom exact: {domain} = {' '.join(name_parts[:num_words])}"
                            break

                        # Fuzzy match domaine vs nom compact
                        if len(compact_name) >= 6:
                            ratio = SequenceMatcher(None, domain_base, compact_name).ratio()
                            if ratio > 0.90:  # Seuil plus strict pour éviter faux positifs
                                score = int(92 + (ratio - 0.90) * 50)  # 92-97
                                if score > best_score:
                                    has_domain_match = True
                                    best_score = min(score, 97)
                                    best_reason = f"Domaine match nom fuzzy: {domain} ~ {' '.join(name_parts[:num_words])} ({ratio:.0%})"

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
        return MatchedProduct(
            item_code=item.get("ItemCode", ""),
            item_name=item.get("ItemName", ""),
            quantity=quantity,
            score=score,
            match_reason=match_reason,
            not_found_in_sap=not_found_in_sap,
            # Prix depuis SAP (sera utilisé par pricing engine si disponible)
            unit_price=item.get("Price"),  # Prix SAP de base
            supplier_price=item.get("SupplierPrice")  # Prix fournisseur si disponible
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

        # 1b. Fallback: Chercher dans le cache SQLite (TOUS les produits SAP)
        try:
            sap_cache_items = self._cache_db.search_items(code, limit=1)
            if sap_cache_items:
                item = {
                    "ItemCode": sap_cache_items[0]["ItemCode"],
                    "ItemName": sap_cache_items[0]["ItemName"]
                }
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
                    item = {
                        "ItemCode": sap_cache_items[0]["ItemCode"],
                        "ItemName": sap_cache_items[0]["ItemName"]
                    }
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

        # --- ÉTAPE 3: Fuzzy match sur ItemName avec description (optimisé) ---
        if description and len(description) >= 4:
            desc_normalized = self._normalize(description)
            # Pré-extraire les mots UNE SEULE FOIS (performance)
            desc_words = set(WORD_PATTERN_4PLUS.findall(desc_normalized))

            best_match = None
            best_score = 0

            for item_code, item in self._items_cache.items():
                # Utiliser le nom normalisé depuis le cache (au lieu de re-normaliser)
                name_normalized = self._items_normalized.get(item_code, "")
                if not name_normalized:
                    continue

                # Match exact substring
                if desc_normalized in name_normalized or name_normalized in desc_normalized:
                    score = 85
                    if score > best_score:
                        best_score = score
                        best_match = (item_code, item, "Nom similaire (substring)")

                # Fuzzy match
                ratio = SequenceMatcher(None, desc_normalized, name_normalized).ratio()
                if ratio > 0.7:
                    score = int(60 + ratio * 30)  # 60-90
                    if score > best_score:
                        best_score = score
                        best_match = (item_code, item, f"Fuzzy nom ({ratio:.0%})")

                # Match par mots communs (utilise pré-extraction des mots)
                name_words = set(WORD_PATTERN_4PLUS.findall(name_normalized))
                common_words = desc_words & name_words

                if len(common_words) >= 2:
                    match_ratio = len(common_words) / max(len(desc_words), 1)
                    if match_ratio > 0.5:
                        score = int(60 + match_ratio * 20)  # 60-80
                        if score > best_score:
                            best_score = score
                            best_match = (item_code, item, f"Mots communs: {', '.join(list(common_words)[:2])}")

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
            'PIECE', 'PIECES', 'PART', 'PARTS', 'ITEM', 'ITEMS', 'REF', 'REFERENCE'
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

    def _extract_quantity_global(self, text: str) -> int:
        """Extrait la quantité globale mentionnée dans le texte (fallback)."""
        qty_patterns = [
            r'qt[eéy]\s*[:\s]*(\d+)',
            r'quantit[eé]\s*[:\s]*(\d+)',
            r'(\d+)\s*(?:pcs|pièces?|units?|unités?)',
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
