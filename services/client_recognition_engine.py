# services/client_recognition_engine.py
"""
Moteur de reconnaissance client multi-niveaux pour NOVA-RONDOT.

Pipeline de reconnaissance :
  Niveau 1 — Emails détectés (expéditeur final, expéditeurs forwardés, demandeur initial)
  Niveau 2 — Domaine email (avec exclusion domaines génériques : gmail, outlook, yahoo…)
  Niveau 3 — Signature du demandeur (société, téléphone, site web)
  Niveau 4 — Indices textuels dans le corps (raisons sociales avec suffixes légaux)
  Niveau 5 — Matching référentiel SAP (CardName, EmailAddress)

Résultat structuré avec score pondéré, signaux explicites, candidats triés.
"""

import re
import logging
import unicodedata
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ─── Domaines génériques à exclure du matching par domaine ───────────────────
GENERIC_DOMAINS: frozenset = frozenset({
    'gmail.com', 'googlemail.com',
    'outlook.com', 'hotmail.com', 'hotmail.fr', 'hotmail.co.uk', 'hotmail.es', 'hotmail.de',
    'live.com', 'live.fr', 'live.co.uk', 'msn.com',
    'yahoo.com', 'yahoo.fr', 'yahoo.co.uk', 'yahoo.es', 'yahoo.de', 'yahoo.it',
    'orange.fr', 'wanadoo.fr', 'free.fr', 'sfr.fr', 'laposte.net', 'bbox.fr',
    'icloud.com', 'me.com', 'mac.com',
    'protonmail.com', 'proton.me',
    'aol.com', 'gmx.com', 'gmx.de', 'gmx.fr',
    'yandex.ru', 'yandex.com', 'mail.ru',
})

# ─── Domaines internes RONDOT à ignorer ─────────────────────────────────────
INTERNAL_DOMAINS: frozenset = frozenset({
    'rondot-sas.fr', 'rondot-poc.itspirit.ovh', 'itspirit.ovh',
    'rondot.fr', 'rondot-sas.com', 'it-spirit.com',
})

# ─── Translittération explicite des caractères sans décomposition NFD ────────
# Ces caractères ne se décomposent pas via unicodedata.normalize('NFD')
# et doivent être remplacés manuellement avant la normalisation NFD.
_TRANSLITERATION_TABLE = str.maketrans({
    # ── Turc ──────────────────────────────────────────────────────────────────
    'ı': 'i',   # i sans point (U+0131) — UNIQUE : pas de décomposition NFD
    'İ': 'I',   # I avec point (U+0130)
    # Sécurité défensive : ces chars se décomposent via NFD MAIS peuvent arriver
    # en encodage Windows-1254 ou copie-colle depuis des systèmes non-UTF8.
    'Ş': 'S',  'ş': 's',   # S cédille turc (U+015E/F)
    'Ğ': 'G',  'ğ': 'g',   # G brevis turc (U+011E/F)
    # ── Nordique / polonais ───────────────────────────────────────────────────
    'ø': 'o',   'Ø': 'O',   # o barré
    'ł': 'l',   'Ł': 'L',   # l barré polonais
    'ð': 'd',   'Ð': 'D',   # eth islandais
    'þ': 'th',  'Þ': 'Th',  # thorn islandais
    # ── Allemand / français ───────────────────────────────────────────────────
    'ß': 'ss',              # eszett allemand minuscule
    'ẞ': 'SS',              # eszett allemand majuscule (U+1E9E) — sans décomposition NFD
    'æ': 'ae',  'Æ': 'AE', # ligature ae
    'œ': 'oe',  'Œ': 'OE', # ligature oe
    # ── Roumain ───────────────────────────────────────────────────────────────
    # U+021A/B et U+0218/9 : virgule souscrite ≠ cédille — NFD peut échouer
    # selon la source (Windows-1250, copie depuis Word…)
    'Ț': 'T',  'ț': 't',   # T virgule souscrite (U+021A/B)
    'Ș': 'S',  'ș': 's',   # S virgule souscrite (U+0218/9)
})

# ─── Regex pour les codes SAP parenthésés ex: "(4001)", "(Group)" ────────────
_PARENTHETICAL_CODE = re.compile(r'\s*\([^)]{1,30}\)')

# ─── Regex pour les suffixes en notation pointée : A.S. → AS, S.A.R.L. → SARL
_DOTTED_ABBREV = re.compile(r'\b([A-Za-z])\.([A-Za-z])\.(?:([A-Za-z])\.)?(?:([A-Za-z])\.)?')

def _collapse_dotted_abbrev(m: re.Match) -> str:
    """Convertit 'A.S.' → 'AS', 'S.A.R.L.' → 'SARL', etc."""
    return ''.join(g for g in m.groups() if g)

# ─── Suffixes légaux à normaliser avant comparaison ─────────────────────────
_SUFFIX_PATTERN = re.compile(
    r'\s*\b(?:SAS|SARL|SA|SNC|SCI|EURL|SASU|GIE|SCP'
    r'|LTD|LIMITED|PLC|LLC|INC|CORP|CO(?:\b)'
    r'|GMBH|AG(?:\b)|KG(?:\b)'
    r'|BV|NV|VZW'
    r'|SPA|SRL|SRLS'
    r'|AS(?:\b)|OY(?:\b)|AB(?:\b)|APS|OYJ'
    r'|PTY|NPC|CC(?:\b)'
    r')\b\.?',
    re.IGNORECASE,
)

# ─── Pondération des signaux ──────────────────────────────────────────────────
SIGNAL_WEIGHTS: Dict[str, float] = {
    'exact_email_match':      1.00,  # Email exact du client = email du client SAP
    'forwarded_email_match':  0.90,  # Email dans les forwards = email client SAP
    'domain_match':           0.82,  # Domaine (non générique) = domaine client SAP
    'signature_company_match': 0.78, # Société dans signature ≈ CardName SAP
    'llm_company_match':      0.72,  # Société extraite LLM ≈ CardName SAP
    'body_company_match':     0.62,  # Société dans corps ≈ CardName SAP
    'existing_matcher_score': 0.50,  # Score normalisé du matcher existant
}

# Seuil auto-acceptation (confidence ≥ seuil → auto-validé)
AUTO_ACCEPT_THRESHOLD: float = 0.80
# Différence max entre top-1 et top-2 pour considérer un cas ambigu.
# 0.18 (vs 0.12 initial) : réduit les faux positifs "ambigu" qui bloquaient l'industrialisation.
AMBIGUITY_GAP: float = 0.18

# Similarity minimum pour un match de nom de société (0.0-1.0)
COMPANY_NAME_SIM_THRESHOLD: float = 0.75


# ─── Utilitaires de normalisation ────────────────────────────────────────────

def strip_company_suffix(name: str) -> str:
    """Retire les suffixes légaux d'un nom d'entreprise."""
    return _SUFFIX_PATTERN.sub(' ', name).strip()


def normalize_company(name: str) -> str:
    """
    Normalise un nom d'entreprise pour la comparaison :
      1. Translittération explicite (ı→i, ß→ss…) — caractères sans décomposition NFD
      2. Normalisation NFD + suppression diacritiques (Ş→S, İ→I, Ü→U, ç→c…)
      3. Collapsage des abbréviations pointées (A.S.→AS, S.A.R.L.→SARL)
      4. Suppression des codes parenthésés SAP (ex: "(4001)")
      5. Suppression des suffixes légaux (SARL, SAS, GMBH, AS…)
      6. Minuscules + suppression ponctuation + normalisation espaces

    Exemple :
      "TÜRKİYE ŞİŞE ve CAM FABRİKALARI A.Ş. (4001)"
      → étape 1 : "TÜRKİYE ŞİŞE ve CAM FABRİKALARI A.Ş. (4001)"  (ı→i déjà OK ici)
      → étape 2 : "TURKIYE SISE ve CAM FABRIKALARI A.S. (4001)"
      → étape 3 : "TURKIYE SISE ve CAM FABRIKALARI AS (4001)"
      → étape 4 : "TURKIYE SISE ve CAM FABRIKALARI AS"
      → étape 5 : "TURKIYE SISE ve CAM FABRIKALARI"
      → étape 6 : "turkiye sise ve cam fabrikalari"
    """
    if not name:
        return ""
    # 1. Translittération (caractères sans décomposition NFD : ı, ß, æ, ø, ł…)
    name = name.translate(_TRANSLITERATION_TABLE)
    # 2. NFD → supprime diacritiques (Ş→S, İ→I, Ü→U, ç→c, é→e, etc.)
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    # 3. Abbréviations pointées : A.S. → AS, S.A.R.L. → SARL
    name = _DOTTED_ABBREV.sub(_collapse_dotted_abbrev, name)
    # 4. Codes parenthésés SAP : "(4001)" → ""
    name = _PARENTHETICAL_CODE.sub('', name)
    # 5. Suffixes légaux (opère sur texte déjà ASCII-safe)
    name = strip_company_suffix(name)
    # 6. Minuscules + ponctuation + espaces
    name = name.lower()
    name = re.sub(r'[^\w\s]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()


def is_generic_domain(domain: str) -> bool:
    """True si le domaine est générique (gmail, hotmail…) → non fiable pour identifier une société."""
    return domain.lower() in GENERIC_DOMAINS


def is_internal_domain(domain: str) -> bool:
    """True si le domaine appartient à RONDOT ou son prestataire IT."""
    return domain.lower() in INTERNAL_DOMAINS


def company_similarity(a: str, b: str) -> float:
    """
    Similarité entre deux noms d'entreprise normalisés (0.0 à 1.0).
    Utilise token_set_ratio pour être robuste aux mots supplémentaires.
    """
    na = normalize_company(a)
    nb = normalize_company(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    try:
        from thefuzz import fuzz
        return fuzz.token_set_ratio(na, nb) / 100.0
    except ImportError:
        # Fallback SequenceMatcher
        from difflib import SequenceMatcher
        return SequenceMatcher(None, na, nb).ratio()


# ─── Modèles de données ───────────────────────────────────────────────────────

@dataclass
class EmailSignals:
    """Signaux extraits de l'email pour la reconnaissance client."""
    final_sender_email: str = ""
    final_sender_domain: str = ""
    forwarded_sender_emails: List[str] = field(default_factory=list)
    # Email du vrai demandeur (premier email non-interne dans les forwards)
    best_requester_email: Optional[str] = None
    best_requester_domain: Optional[str] = None
    # Société extraite de la signature du demandeur
    signature_company: Optional[str] = None
    # Sociétés détectées dans le corps (patterns "[NOM] SARL/SAS/etc.")
    body_companies: List[str] = field(default_factory=list)
    # Société extraite par le LLM (passée depuis email_analyzer)
    llm_company: Optional[str] = None


class RecognitionSignal(BaseModel):
    """Signal ayant contribué à la reconnaissance d'un client."""
    signal_type: str   # ex: 'exact_email_match'
    value: str         # valeur qui a matché
    weight: float      # pondération utilisée
    description: str   # explication humaine


class ScoredCandidate(BaseModel):
    """Client SAP candidat avec score de confiance et signaux détaillés."""
    card_code: str
    card_name: str
    email_address: Optional[str] = None
    confidence_score: float        # 0.0-1.0 — score global
    matched_signals: List[str]     # noms des signaux ayant contribué
    signal_details: List[RecognitionSignal] = []
    # Score brut du matcher existant (pour rétrocompatibilité)
    raw_matcher_score: Optional[int] = None
    # Score converti en dict pour client_matches (rétrocompatibilité frontend)
    score: int = 0                 # = int(confidence_score * 100)
    match_reason: str = ""


class ClientRecognitionResult(BaseModel):
    """Résultat complet de la reconnaissance client."""
    matched: bool
    client_code: Optional[str] = None
    client_name: Optional[str] = None
    confidence_score: float = 0.0
    decision_reason: str = ""
    matched_signals: List[str] = []
    candidates: List[ScoredCandidate] = []
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    # Signaux extraits (traçabilité)
    final_sender_email: str = ""
    forwarded_sender_emails: List[str] = []
    best_requester_email: Optional[str] = None
    signature_company: Optional[str] = None
    body_companies: List[str] = []


# ─── Extracteur de signaux email ─────────────────────────────────────────────

# Patterns de détection d'email
_EMAIL_RE = re.compile(r'[\w._%+-]+@[\w.-]+\.\w{2,}', re.IGNORECASE)

# Patterns "From: Name email" ou "De: Name email"
_FROM_NAME_EMAIL_RE = re.compile(
    r'(?:From|De|Von|Da|Ekspeditor)\s*:\s*(.{1,80}?)\s+([\w._%+-]+@[\w.-]+\.\w{2,})',
    re.IGNORECASE
)
# Patterns "From: email" (sans nom)
_FROM_EMAIL_ONLY_RE = re.compile(
    r'(?:From|De|Von|Da|Ekspeditor)\s*:\s*([\w._%+-]+@[\w.-]+\.\w{2,})',
    re.IGNORECASE
)
# Pattern Gmail "Name email a écrit :"
_GMAIL_WROTE_RE = re.compile(
    r'(.{2,80}?)\s+([\w._%+-]+@[\w.-]+\.\w{2,})\s+(?:a[\u00a0 ]écrit|wrote|schrieb|ha scritto)',
    re.IGNORECASE
)
# Pattern société dans le corps : "NOM SARL" ou "NOM SAS" etc.
_BODY_COMPANY_RE = re.compile(
    r'([A-ZÀ-Ÿa-zà-ÿ][A-ZÀ-Ÿa-zà-ÿ\s\-&]{2,50}?)\s+'
    r'(?:SAS|SARL|SA\b|EURL|SASU|LTD|LLC|INC|GMBH|BV|SPA|SRL|AS\b|AB\b|OY\b)',
    re.IGNORECASE
)
# Suffixes légaux pour détection dans la signature
_SIG_SUFFIX_RE = re.compile(
    r'\b(?:SAS|SARL|SA|EURL|SASU|LTD|LLC|INC|GMBH|BV|SPA|SRL|AS|AB|OY)\b',
    re.IGNORECASE
)


class EmailSignalExtractor:
    """Extrait les signaux d'identification client depuis le contenu d'un email."""

    def extract(self, body: str, sender_email: str, subject: str = "") -> EmailSignals:
        """
        Extrait tous les signaux de reconnaissance client depuis l'email.

        Args:
            body: Corps de l'email (texte nettoyé, sans HTML)
            sender_email: Email de l'expéditeur (depuis les headers)
            subject: Sujet de l'email

        Returns:
            EmailSignals avec tous les signaux détectés
        """
        signals = EmailSignals(final_sender_email=sender_email)

        if "@" in sender_email:
            domain = sender_email.split("@")[-1].lower()
            if not is_internal_domain(domain) and not is_generic_domain(domain):
                signals.final_sender_domain = domain

        # Extraire tous les emails de forwarding
        forwarded = self._extract_all_forward_emails(body)
        signals.forwarded_sender_emails = forwarded

        # Trouver le meilleur email "demandeur" (premier non-interne, non-générique)
        candidate_emails = [sender_email] + forwarded
        for email_addr in candidate_emails:
            if "@" not in email_addr:
                continue
            dom = email_addr.split("@")[-1].lower()
            if not is_internal_domain(dom):
                signals.best_requester_email = email_addr
                if not is_generic_domain(dom):
                    signals.best_requester_domain = dom
                break

        # Extraire la société depuis la signature
        signals.signature_company = self._extract_signature_company(body)

        # Extraire les sociétés depuis le corps
        signals.body_companies = self._extract_body_companies(body)

        logger.debug(
            "signals_extracted sender=%s forwarded=%d sig_company=%s body_companies=%d",
            sender_email, len(forwarded), signals.signature_company, len(signals.body_companies)
        )
        return signals

    def _extract_all_forward_emails(self, body: str) -> List[str]:
        """
        Extrait TOUTES les adresses email des headers de forwarding (De:/From:).
        Retourne la liste dans l'ordre d'apparition (du plus récent au plus ancien).
        """
        if not body:
            return []

        found: List[str] = []
        seen: set = set()

        # Pattern 1 : "From/De: Nom email"
        for m in _FROM_NAME_EMAIL_RE.finditer(body):
            email_addr = m.group(2).lower()
            dom = email_addr.split("@")[-1]
            if not is_internal_domain(dom) and email_addr not in seen:
                found.append(email_addr)
                seen.add(email_addr)

        # Pattern 2 : "From/De: email" (sans nom — fallback)
        if not found:
            for m in _FROM_EMAIL_ONLY_RE.finditer(body):
                email_addr = m.group(1).lower()
                dom = email_addr.split("@")[-1]
                if not is_internal_domain(dom) and email_addr not in seen:
                    found.append(email_addr)
                    seen.add(email_addr)

        # Pattern 3 : Gmail "Name email a écrit"
        if not found:
            for m in _GMAIL_WROTE_RE.finditer(body):
                email_addr = m.group(2).lower()
                dom = email_addr.split("@")[-1]
                if not is_internal_domain(dom) and email_addr not in seen:
                    found.append(email_addr)
                    seen.add(email_addr)

        # Pattern 4 : Format Outlook/Exchange — première ligne "NOM PRENOM email@domain.com >"
        # Ex: "KADIR TERCAN KATERCAN@sisecam.com >" (pas de préfixe De:/From:)
        if not found:
            _OUTLOOK_HEADER_RE = re.compile(
                r'^.{2,60}?\s+([\w._%+-]+@[\w.-]+\.\w{2,})\s*>',
                re.IGNORECASE | re.MULTILINE,
            )
            for m in _OUTLOOK_HEADER_RE.finditer(body):
                email_addr = m.group(1).lower()
                dom = email_addr.split("@")[-1]
                if not is_internal_domain(dom) and email_addr not in seen:
                    found.append(email_addr)
                    seen.add(email_addr)

        return found

    def _extract_signature_company(self, body: str) -> Optional[str]:
        """
        Tente d'extraire le nom de société depuis la signature du message.

        Stratégie :
        1. Chercher un séparateur de signature (-- , ___, ====)
        2. Prendre les 25 dernières lignes si pas de séparateur
        3. Chercher une ligne contenant un suffixe légal
        4. Ou une ligne en majuscules (≥ 3 mots, ≥ 6 chars)
        """
        if not body:
            return None

        lines = [l.strip() for l in body.split('\n') if l.strip()]
        if not lines:
            return None

        # Trouver le séparateur de signature
        sig_start = None
        sep_re = re.compile(r'^[-_=.]{2,}$|^--\s*$|^_{3,}')
        for i in range(len(lines) - 1, max(len(lines) - 50, -1), -1):
            if sep_re.match(lines[i]):
                sig_start = i + 1
                break

        # Prendre les lignes de signature (ou les 25 dernières)
        sig_lines = lines[sig_start:] if sig_start is not None else lines[-25:]

        # 1. Chercher ligne avec suffixe légal
        for line in sig_lines:
            if _SIG_SUFFIX_RE.search(line) and len(line) >= 4:
                # Nettoyer et retourner
                company = _SIG_SUFFIX_RE.sub('', line).strip(' -|,;')
                company = re.sub(r'\s+', ' ', company).strip()
                if len(company) >= 3:
                    return company

        # 2. Chercher une ligne qui ressemble à un nom de société (majuscules, ≥ 6 chars)
        for line in sig_lines:
            # Ignorer les emails, URLs, numéros de téléphone
            if '@' in line or 'http' in line.lower() or re.match(r'^[\d\s\+\-\(\)\.]+$', line):
                continue
            # Ligne contenant plusieurs mots en majuscules
            words = line.split()
            caps_words = [w for w in words if w.isupper() and len(w) >= 3]
            if len(caps_words) >= 2 and len(line) >= 6:
                return line.strip()

        return None

    def _extract_body_companies(self, body: str) -> List[str]:
        """
        Extrait les noms de sociétés du corps de l'email en détectant
        les patterns "[Nom de Société] [Suffixe légal]".
        """
        if not body:
            return []

        companies = []
        seen = set()
        for m in _BODY_COMPANY_RE.finditer(body):
            name = m.group(1).strip()
            # Filtrer les noms trop courts ou trop courants
            if len(name) < 3:
                continue
            words = name.split()
            if len(words) == 1 and len(name) < 5:
                continue
            name_lower = name.lower()
            if name_lower in seen:
                continue
            seen.add(name_lower)
            companies.append(name)

        return companies[:5]  # Max 5 pour éviter le bruit


# ─── Moteur de scoring ────────────────────────────────────────────────────────

class ClientRecognitionEngine:
    """
    Moteur de reconnaissance client multi-niveaux.

    Prend les signaux extraits de l'email et les candidats du matcher existant,
    les re-score avec des signaux supplémentaires, et retourne un résultat
    structuré avec score de confiance et détection d'ambiguïté.
    """

    def __init__(self):
        self._extractor = EmailSignalExtractor()

    def recognize_client(
        self,
        body: str,
        sender_email: str,
        subject: str = "",
        llm_client_name: Optional[str] = None,
        llm_client_email: Optional[str] = None,
        existing_candidates: Optional[List[Any]] = None,  # List[MatchedClient] du matcher
        clients_cache: Optional[List[Dict[str, Any]]] = None,  # Cache SAP complet (fallback)
    ) -> ClientRecognitionResult:
        """
        Reconnaissance client multi-niveaux.

        Args:
            body: Corps de l'email nettoyé
            sender_email: Email de l'expéditeur
            subject: Sujet de l'email
            llm_client_name: Nom société extrait par le LLM
            llm_client_email: Email client extrait par le LLM
            existing_candidates: Candidats trouvés par EmailMatcher (List[MatchedClient])
            clients_cache: Cache complet des clients SAP (pour recherche supplémentaire)

        Returns:
            ClientRecognitionResult avec score de confiance et signaux
        """
        # 1. Extraire les signaux depuis l'email
        signals = self._extractor.extract(body, sender_email, subject)
        signals.llm_company = llm_client_name

        log_prefix = f"[CLIENT_RECOGNITION] sender={sender_email}"
        logger.info(
            "%s | forwarded=%d | sig_company=%r | llm=%r | candidates=%d",
            log_prefix,
            len(signals.forwarded_sender_emails),
            signals.signature_company,
            llm_client_name,
            len(existing_candidates) if existing_candidates else 0,
        )

        # 2. Scorer chaque candidat existant avec les signaux supplémentaires
        scored: List[ScoredCandidate] = []
        for candidate in (existing_candidates or []):
            sc = self._score_candidate(candidate, signals, llm_client_email)
            scored.append(sc)

        # 3. Recherche supplémentaire si peu de candidats ET on a un nom de société
        if len(scored) < 3 and clients_cache:
            hint_names = []
            if signals.signature_company:
                hint_names.append(signals.signature_company)
            if llm_client_name and llm_client_name not in hint_names:
                hint_names.append(llm_client_name)
            hint_names += signals.body_companies

            existing_codes = {sc.card_code for sc in scored}
            for hint in hint_names:
                extra = self._search_by_company_name(hint, clients_cache, existing_codes)
                for sc in extra:
                    # Re-scorer avec signaux complets
                    sc_full = self._score_candidate_from_dict(
                        sc, signals, llm_client_email
                    )
                    if sc_full.confidence_score >= 0.40:
                        scored.append(sc_full)
                        existing_codes.add(sc_full.card_code)

        # 4. Trier par score décroissant
        scored.sort(key=lambda s: s.confidence_score, reverse=True)
        scored = scored[:5]  # Top 5

        # 5. Construire le résultat final
        return self._build_result(scored, signals, log_prefix)

    def _score_candidate(
        self,
        candidate: Any,  # MatchedClient instance
        signals: EmailSignals,
        llm_client_email: Optional[str] = None,
    ) -> ScoredCandidate:
        """Score un candidat existant (MatchedClient) avec les signaux extraits."""
        # Convertir MatchedClient en dict-like pour _score_candidate_dict
        data = {
            'CardCode': getattr(candidate, 'card_code', ''),
            'CardName': getattr(candidate, 'card_name', ''),
            'EmailAddress': getattr(candidate, 'email_address', ''),
            '_raw_score': getattr(candidate, 'score', 0),
            '_match_reason': getattr(candidate, 'match_reason', ''),
        }
        return self._score_candidate_from_dict(data, signals, llm_client_email)

    def _score_candidate_from_dict(
        self,
        client: Dict[str, Any],
        signals: EmailSignals,
        llm_client_email: Optional[str] = None,
    ) -> ScoredCandidate:
        """Score un client SAP (dict) contre l'ensemble des signaux email."""
        import json as _json

        card_code = client.get('CardCode', '')
        card_name = client.get('CardName', '')
        email_addr = (client.get('EmailAddress', '') or '').lower().strip()
        raw_score = client.get('_raw_score', 0)
        match_reason = client.get('_match_reason', '')

        # Collecter TOUS les emails SAP de ce client (fiche + ContactEmployees)
        _all_sap_emails: set = set()
        if email_addr:
            _all_sap_emails.add(email_addr)
        _contact_emails_raw = client.get('contact_emails') or ''
        if _contact_emails_raw:
            try:
                for _ce in _json.loads(_contact_emails_raw):
                    if _ce and '@' in _ce:
                        _all_sap_emails.add(_ce.lower().strip())
            except (ValueError, TypeError):
                pass
        # Domaines SAP uniques (hors génériques / internes)
        _all_sap_domains: set = {
            e.split('@')[-1] for e in _all_sap_emails if '@' in e
            and not is_generic_domain(e.split('@')[-1])
            and not is_internal_domain(e.split('@')[-1])
        }

        matched_signals: List[str] = []
        signal_details: List[RecognitionSignal] = []
        total_weight = 0.0

        def _add(sig_type: str, value: str, weight: float, desc: str):
            matched_signals.append(sig_type)
            signal_details.append(RecognitionSignal(
                signal_type=sig_type, value=value, weight=weight, description=desc
            ))
            nonlocal total_weight
            total_weight = min(1.0, total_weight + weight)

        client_domain = email_addr.split("@")[-1] if "@" in email_addr else ""

        # ── Signal 1 : email exact ─────────────────────────────────────────────
        # Vérifie tous les emails de l'email entrant contre TOUS les emails SAP
        # (fiche principale + ContactEmployees)
        all_emails_to_check = []
        if signals.final_sender_email:
            all_emails_to_check.append(('final', signals.final_sender_email))
        if llm_client_email:
            all_emails_to_check.append(('llm', llm_client_email))
        for fwd in signals.forwarded_sender_emails:
            all_emails_to_check.append(('forwarded', fwd))

        for source, chk_email in all_emails_to_check:
            chk_lower = chk_email.lower()
            if chk_lower in _all_sap_emails:
                sig_type = 'exact_email_match' if source != 'forwarded' else 'forwarded_email_match'
                weight = SIGNAL_WEIGHTS[sig_type]
                _add(sig_type, chk_email, weight,
                     f"Email {'expéditeur' if source == 'final' else source} = email SAP client")
                break

        # ── Signal 2 : match par domaine (non générique) ──────────────────────
        # Vérifie les domaines extraits de l'email vs TOUS les domaines SAP client
        if 'exact_email_match' not in matched_signals and 'forwarded_email_match' not in matched_signals:
            if _all_sap_domains:
                domains_to_check = set()
                if signals.final_sender_domain:
                    domains_to_check.add(signals.final_sender_domain)
                if signals.best_requester_domain:
                    domains_to_check.add(signals.best_requester_domain)
                for fwd_email in signals.forwarded_sender_emails:
                    if "@" in fwd_email:
                        d = fwd_email.split("@")[-1].lower()
                        if not is_internal_domain(d) and not is_generic_domain(d):
                            domains_to_check.add(d)

                matched_domain = _all_sap_domains & domains_to_check
                if matched_domain:
                    dom = next(iter(matched_domain))
                    _add('domain_match', dom, SIGNAL_WEIGHTS['domain_match'],
                         f"Domaine email {dom} présent dans l'email")

        # ── Signal 3 : société dans la signature ─────────────────────────────
        if signals.signature_company:
            sim = company_similarity(signals.signature_company, card_name)
            if sim >= COMPANY_NAME_SIM_THRESHOLD:
                _add('signature_company_match', signals.signature_company,
                     SIGNAL_WEIGHTS['signature_company_match'] * sim,
                     f"Signature '{signals.signature_company}' ≈ '{card_name}' ({sim:.0%})")

        # ── Signal 4 : société extraite par le LLM ────────────────────────────
        if signals.llm_company:
            sim = company_similarity(signals.llm_company, card_name)
            if sim >= COMPANY_NAME_SIM_THRESHOLD:
                _add('llm_company_match', signals.llm_company,
                     SIGNAL_WEIGHTS['llm_company_match'] * sim,
                     f"LLM '{signals.llm_company}' ≈ '{card_name}' ({sim:.0%})")

        # ── Signal 5 : société dans le corps ──────────────────────────────────
        for body_company in signals.body_companies:
            sim = company_similarity(body_company, card_name)
            if sim >= COMPANY_NAME_SIM_THRESHOLD:
                _add('body_company_match', body_company,
                     SIGNAL_WEIGHTS['body_company_match'] * sim,
                     f"Corps '{body_company}' ≈ '{card_name}' ({sim:.0%})")
                break  # Un seul signal corps suffisant

        # ── Signal 6 : score du matcher existant (converti 0-1) ──────────────
        if raw_score > 0:
            # Le matcher existant couvre le matching domaine/nom — on normalise son score
            # mais on le pondère moins fort (il est déjà intégré via les signaux 1-5)
            existing_conf = (raw_score / 100.0) * SIGNAL_WEIGHTS['existing_matcher_score']
            if not matched_signals:
                # Aucun signal fort trouvé → utiliser uniquement le score matcher
                total_weight = existing_conf
            else:
                # Signaux forts présents → le score matcher est un bonus mineur
                total_weight = min(1.0, total_weight + existing_conf * 0.3)

        # Construire la description du match
        reason_parts = [match_reason] if match_reason else []
        if signal_details:
            reason_parts.append("; ".join(s.description for s in signal_details[:3]))
        decision_reason = " | ".join(reason_parts) if reason_parts else f"Score matcher: {raw_score}"

        score_int = int(total_weight * 100)

        return ScoredCandidate(
            card_code=card_code,
            card_name=card_name,
            email_address=email_addr or None,
            confidence_score=total_weight,
            matched_signals=matched_signals,
            signal_details=signal_details,
            raw_matcher_score=raw_score,
            score=score_int,
            match_reason=decision_reason,
        )

    def _search_by_company_name(
        self,
        company_hint: str,
        clients_cache: List[Dict[str, Any]],
        exclude_codes: set,
    ) -> List[Dict[str, Any]]:
        """
        Recherche dans le cache SAP les clients dont le nom ressemble à company_hint.
        Retourne les clients avec score brut 0 (seront scorés par _score_candidate_from_dict).
        """
        results = []
        norm_hint = normalize_company(company_hint)
        if not norm_hint or len(norm_hint) < 3:
            return results

        for client in clients_cache:
            code = client.get('CardCode', '')
            if code in exclude_codes:
                continue
            name = client.get('CardName', '')
            sim = company_similarity(company_hint, name)
            if sim >= COMPANY_NAME_SIM_THRESHOLD:
                results.append({**client, '_raw_score': 0, '_match_reason': ''})

        # Trier par similarité
        results.sort(
            key=lambda c: company_similarity(company_hint, c.get('CardName', '')),
            reverse=True
        )
        return results[:3]

    def _build_result(
        self,
        candidates: List[ScoredCandidate],
        signals: EmailSignals,
        log_prefix: str,
    ) -> ClientRecognitionResult:
        """Construit le ClientRecognitionResult final avec détection d'ambiguïté."""

        if not candidates:
            logger.info("%s | NO_MATCH", log_prefix)
            return ClientRecognitionResult(
                matched=False,
                decision_reason="Aucun client SAP correspondant trouvé",
                final_sender_email=signals.final_sender_email,
                forwarded_sender_emails=signals.forwarded_sender_emails,
                best_requester_email=signals.best_requester_email,
                signature_company=signals.signature_company,
                body_companies=signals.body_companies,
            )

        top = candidates[0]

        # Détection ambiguïté
        is_ambiguous = False
        ambiguity_reason = None
        if len(candidates) >= 2:
            gap = top.confidence_score - candidates[1].confidence_score
            if gap < AMBIGUITY_GAP and top.confidence_score < AUTO_ACCEPT_THRESHOLD:
                is_ambiguous = True
                ambiguity_reason = (
                    f"{candidates[0].card_name} ({top.confidence_score:.0%}) vs "
                    f"{candidates[1].card_name} ({candidates[1].confidence_score:.0%}) "
                    f"— écart {gap:.0%} < seuil {AMBIGUITY_GAP:.0%}"
                )
                logger.warning("%s | AMBIGUOUS: %s", log_prefix, ambiguity_reason)

        matched = top.confidence_score >= 0.40  # Seuil minimal pour ne pas être "non trouvé"

        if matched:
            logger.info(
                "%s | MATCH: %s (%s) conf=%.2f signals=%s ambiguous=%s",
                log_prefix, top.card_name, top.card_code,
                top.confidence_score, top.matched_signals, is_ambiguous
            )

        return ClientRecognitionResult(
            matched=matched and not is_ambiguous,
            client_code=top.card_code if matched else None,
            client_name=top.card_name if matched else None,
            confidence_score=top.confidence_score,
            decision_reason=top.match_reason,
            matched_signals=top.matched_signals,
            candidates=candidates,
            is_ambiguous=is_ambiguous,
            ambiguity_reason=ambiguity_reason,
            final_sender_email=signals.final_sender_email,
            forwarded_sender_emails=signals.forwarded_sender_emails,
            best_requester_email=signals.best_requester_email,
            signature_company=signals.signature_company,
            body_companies=signals.body_companies,
        )


# ─── Singleton ───────────────────────────────────────────────────────────────

_engine: Optional[ClientRecognitionEngine] = None


def get_client_recognition_engine() -> ClientRecognitionEngine:
    """Factory pattern — retourne l'instance singleton."""
    global _engine
    if _engine is None:
        _engine = ClientRecognitionEngine()
        logger.info("ClientRecognitionEngine instance created")
    return _engine
