# services/email_analyzer.py
"""
Service d'analyse intelligente des emails.
Utilise une approche hybride: pré-filtrage par règles + analyse LLM à la demande.
"""

import os
import re
import json
import logging
import tempfile
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


# Mots-clés pour la détection rapide (pré-filtrage sans LLM)
QUOTE_KEYWORDS_SUBJECT = [
    'devis', 'quotation', 'quote', 'prix', 'price',
    'rfq', 'request for quotation', 'demande de prix',
    'offre de prix', 'chiffrage', 'tarif'
]

QUOTE_KEYWORDS_BODY = [
    'merci de nous faire un devis',
    'please quote', 'please provide a quote',
    'we would like a quotation',
    'please send the offer', 'send the offer to',
    'demande de prix', 'demande de devis',
    'demande de chiffrage', 'demande chiffrage',
    'pouvez-vous nous faire une offre',
    'nous souhaitons recevoir une offre',
    'could you quote', 'request for price',
    'veuillez nous communiquer vos prix',
    'souhaitons obtenir un devis',
    'veuillez nous faire un chiffrage',
    'pouvez-vous chiffrer', 'merci de chiffrer',
    'veuillez trouver ci-joint', 'find attached', 'ci-joint la demande'
]

QUANTITY_PATTERNS = [
    r'\b\d+\s*(pcs|pieces?|pièces?|units?|unités?|ea|each|kits?|sets?)\b',
    r'\bqt[ey]?\.?\s*:?\s*\d+',
    r'\b\d+\s*x\s*\w+',
    r'\bquantité\s*:?\s*\d+',
]


# Modèles de données
class ExtractedProduct(BaseModel):
    description: Optional[str] = ""
    quantity: Optional[int] = None
    unit: Optional[str] = None
    reference: Optional[str] = None


class ExtractedQuoteData(BaseModel):
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_card_code: Optional[str] = None  # CardCode SAP si matché
    phone: Optional[str] = None  # Téléphone client
    siret: Optional[str] = None  # Numéro SIRET
    address: Optional[str] = None  # Adresse complète
    products: List[ExtractedProduct] = []
    delivery_requirement: Optional[str] = None
    urgency: str = "normal"
    notes: Optional[str] = None


class EmailAnalysisResult(BaseModel):
    classification: str  # QUOTE_REQUEST, INFORMATION, OTHER
    confidence: str  # high, medium, low
    is_quote_request: bool
    reasoning: str
    extracted_data: Optional[ExtractedQuoteData] = None
    quick_filter_passed: bool = False  # True si pré-filtrage règles a détecté un devis

    # Détection de doublons
    is_duplicate: bool = False
    duplicate_type: Optional[str] = None  # strict, probable, possible
    duplicate_confidence: float = 0.0
    existing_quote_id: Optional[str] = None
    existing_quote_status: Optional[str] = None

    # Matches multiples et validation
    client_matches: List = []  # List[MatchedClient] from email_matcher
    product_matches: List = []  # List[MatchedProduct] from email_matcher
    client_auto_validated: bool = False  # True si client score ≥ 95
    products_auto_validated: bool = False  # True si tous produits score = 100
    requires_user_choice: bool = False  # True si choix utilisateur nécessaire
    user_choice_reason: Optional[str] = None  # Raison du choix manuel


# Prompt LLM pour l'analyse des emails
EMAIL_CLASSIFICATION_PROMPT = """Tu es un assistant spécialisé dans la classification des emails commerciaux pour une entreprise industrielle.

Analyse cet email et détermine:
1. S'il s'agit d'une DEMANDE DE DEVIS (quote request) - un client qui demande des prix pour des produits/services
2. La confiance dans cette classification (high/medium/low)
3. Les informations extraites si c'est une demande de devis

TYPES DE CLASSIFICATION:
- "QUOTE_REQUEST": Demande de devis, RFQ, demande de prix, demande de chiffrage
- "INFORMATION": Email informatif, confirmation de meeting, newsletter, notification
- "OTHER": Facture, commande confirmée, réclamation, autre type d'email

INDICES D'UNE DEMANDE DE DEVIS:
- Phrases comme "merci de nous faire un devis", "please quote", "demande de prix"
- Liste de produits avec quantités
- Demande de délai de livraison
- Mention de références produits ou spécifications techniques

EXTRACTION DES INFORMATIONS CLIENT (important pour validation):
- Nom entreprise: chercher dans la signature ou le corps de l'email
- SIRET: chercher le numéro SIRET (14 chiffres) si présent dans la signature ou pièce jointe
- Téléphone: extraire si présent dans la signature
- Adresse: extraire l'adresse complète si présente

EXTRACTION DES PRODUITS:
- Description: description complète du produit
- Quantité: nombre d'unités demandées
- Unité: pcs, kg, m, l, etc.
- Référence: code produit, référence fournisseur si mentionnée

Réponds UNIQUEMENT en JSON valide (pas de texte avant ou après):
{
  "classification": "QUOTE_REQUEST|INFORMATION|OTHER",
  "confidence": "high|medium|low",
  "is_quote_request": true|false,
  "reasoning": "Explication courte de la classification",
  "extracted_data": {
    "client_name": "Nom de l'entreprise cliente si détecté",
    "client_email": "Email du contact si différent de l'expéditeur",
    "phone": "Numéro de téléphone si présent (format +33...)",
    "siret": "Numéro SIRET si présent (14 chiffres sans espaces)",
    "address": "Adresse complète si présente",
    "products": [
      {"description": "Description du produit", "quantity": 10, "unit": "pcs", "reference": "REF-123"}
    ],
    "delivery_requirement": "Délai de livraison si mentionné",
    "urgency": "normal|urgent",
    "notes": "Autres informations pertinentes"
  }
}

Si ce n'est PAS une demande de devis, "extracted_data" doit être null.

IMPORTANT:
- Pour le SIRET: chercher un nombre de 14 chiffres, souvent près de mentions comme "SIRET:", "SIREN:", ou dans la signature
- Pour le téléphone: format français +33, 0033, ou 0X XX XX XX XX
- Ne pas inventer de données: si une info n'est pas présente, laisser le champ à null"""


class EmailAnalyzer:
    """Service d'analyse des emails avec approche hybride."""

    def quick_classify(self, subject: str, body_preview: str) -> Dict[str, Any]:
        """
        Pré-filtrage rapide basé sur des règles (sans LLM).
        Retourne un score de probabilité et les règles matchées.
        """
        subject_lower = subject.lower()
        body_lower = body_preview.lower()
        combined = f"{subject_lower} {body_lower}"

        matched_rules = []
        score = 0

        # Vérifier les mots-clés dans le sujet (poids plus élevé)
        for keyword in QUOTE_KEYWORDS_SUBJECT:
            if keyword in subject_lower:
                matched_rules.append(f"Subject contains '{keyword}'")
                score += 30

        # Vérifier les phrases dans le body
        for phrase in QUOTE_KEYWORDS_BODY:
            if phrase in body_lower:
                matched_rules.append(f"Body contains quote phrase")
                score += 25
                break  # Une seule phrase suffit

        # Vérifier les patterns de quantité
        for pattern in QUANTITY_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                matched_rules.append("Contains quantity patterns")
                score += 15
                break

        # Déterminer le niveau de confiance du pré-filtrage
        if score >= 50:
            confidence = "high"
        elif score >= 30:
            confidence = "medium"
        elif score >= 15:
            confidence = "low"
        else:
            confidence = "none"

        return {
            "likely_quote": score >= 15,
            "score": score,
            "confidence": confidence,
            "matched_rules": matched_rules
        }

    async def analyze_email(
        self,
        subject: str,
        body: str,
        sender_email: str,
        sender_name: str = "",
        pdf_contents: List[str] = None
    ) -> EmailAnalysisResult:
        """
        Analyse complète d'un email avec LLM.

        Args:
            subject: Sujet de l'email
            body: Corps de l'email (HTML ou texte)
            sender_email: Email de l'expéditeur
            sender_name: Nom de l'expéditeur
            pdf_contents: Liste des contenus textuels extraits des PDFs
        """
        # Nettoyer le body HTML si nécessaire
        clean_body = self._clean_html(body)

        # Pré-filtrage rapide
        quick_result = self.quick_classify(subject, clean_body[:500])

        # Construire le contexte pour le LLM
        email_context = f"""SUJET: {subject}

EXPÉDITEUR: {sender_name} <{sender_email}>

CONTENU:
{clean_body[:3000]}"""

        if pdf_contents:
            email_context += "\n\nPIÈCES JOINTES (contenu extrait):\n"
            for i, content in enumerate(pdf_contents[:3], 1):
                email_context += f"\n--- Pièce jointe {i} ---\n{content[:1500]}\n"

        # Appel LLM
        try:
            llm_result = await self._call_llm(email_context)

            # Parser la réponse JSON
            analysis = self._parse_llm_response(llm_result)
            analysis.quick_filter_passed = quick_result["likely_quote"]

            # Correctif faux négatifs : si le pré-filtrage détecte clairement une demande de devis
            # (sujet/corps avec "chiffrage", "devis", etc.) avec confiance medium ou high,
            # on priorise le pré-filtrage sur le LLM (qui peut se tromper sur transferts, bilingue, etc.)
            if (
                quick_result["likely_quote"]
                and quick_result["confidence"] in ("high", "medium")
                and not analysis.is_quote_request
            ):
                logger.info(
                    f"Override LLM: pre-filter detected quote (score={quick_result['score']}, "
                    f"rules={quick_result['matched_rules'][:3]}) -> forcing QUOTE_REQUEST"
                )
                analysis.classification = "QUOTE_REQUEST"
                analysis.is_quote_request = True
                analysis.confidence = "high"  # afficher confiance élevée pour le bouton Traiter
                analysis.reasoning = (
                    f"Règle métier: {', '.join(quick_result['matched_rules'][:3])}. "
                    f"{analysis.reasoning or ''}"
                )[:500]

            return analysis

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Fallback sur le pré-filtrage seul avec extraction regex
            return self._fallback_analysis(quick_result, sender_email, sender_name, clean_body)

    async def _call_llm(self, email_context: str) -> str:
        """Appelle le LLM (Claude en priorité, OpenAI en fallback)."""

        user_message = f"""Analyse cet email commercial:

{email_context}"""

        # Essayer Claude d'abord
        if ANTHROPIC_API_KEY:
            try:
                return await self._call_claude(user_message)
            except Exception as e:
                logger.warning(f"Claude call failed: {e}, falling back to OpenAI")

        # Fallback OpenAI
        if OPENAI_API_KEY:
            return await self._call_openai(user_message)

        raise ValueError("No LLM API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)")

    async def _call_claude(self, user_message: str) -> str:
        """Appel à l'API Claude."""
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 1500,
            "system": EMAIL_CLASSIFICATION_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
            "temperature": 0.0
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data.get("content", [{}])[0].get("text", "")

    async def _call_openai(self, user_message: str) -> str:
        """Appel à l'API OpenAI (fallback)."""
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": EMAIL_CLASSIFICATION_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 1500,
            "temperature": 0.0
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _parse_llm_response(self, response: str) -> EmailAnalysisResult:
        """Parse la réponse JSON du LLM."""
        # Extraire le JSON de la réponse
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError("No JSON found in LLM response")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            raise

        # Construire le résultat
        extracted_data = None
        if data.get("extracted_data"):
            ed = data["extracted_data"]
            products = []
            for p in ed.get("products", []):
                products.append(ExtractedProduct(
                    description=p.get("description") or "",
                    quantity=p.get("quantity"),
                    unit=p.get("unit"),
                    reference=p.get("reference")
                ))

            extracted_data = ExtractedQuoteData(
                client_name=ed.get("client_name"),
                client_email=ed.get("client_email"),
                phone=ed.get("phone"),
                siret=ed.get("siret"),
                address=ed.get("address"),
                products=products,
                delivery_requirement=ed.get("delivery_requirement"),
                urgency=ed.get("urgency", "normal"),
                notes=ed.get("notes")
            )

        return EmailAnalysisResult(
            classification=data.get("classification", "OTHER"),
            confidence=data.get("confidence", "low"),
            is_quote_request=data.get("is_quote_request", False),
            reasoning=data.get("reasoning", ""),
            extracted_data=extracted_data
        )

    def _fallback_analysis(
        self,
        quick_result: Dict[str, Any],
        sender_email: str,
        sender_name: str,
        body: str = ""
    ) -> EmailAnalysisResult:
        """Analyse de secours basée uniquement sur le pré-filtrage."""
        is_quote = quick_result["likely_quote"]

        # Extraire le nom de l'entreprise depuis l'email
        domain = sender_email.split("@")[-1] if "@" in sender_email else ""
        company_name = domain.split(".")[0].title() if domain else sender_name

        # Essayer d'extraire le vrai expéditeur depuis le corps (cas forward/redirect)
        original_sender = self._extract_original_sender(body)
        if original_sender:
            company_name = original_sender

        # Extraire les produits depuis le texte avec regex
        products = self._extract_products_from_text(body) if is_quote else []

        return EmailAnalysisResult(
            classification="QUOTE_REQUEST" if is_quote else "OTHER",
            confidence=quick_result["confidence"],
            is_quote_request=is_quote,
            reasoning=f"Rule-based analysis (LLM unavailable). Matched: {', '.join(quick_result['matched_rules']) or 'None'}",
            extracted_data=ExtractedQuoteData(
                client_name=company_name,
                products=products
            ) if is_quote else None,
            quick_filter_passed=is_quote
        )

    def _extract_original_sender(self, body: str) -> Optional[str]:
        """Extrait l'expéditeur original d'un email forwardé/redirigé."""
        if not body:
            return None

        # Patterns pour détecter l'expéditeur original
        patterns = [
            r'De\s*:\s*[^<]*<([^>]+@([^>]+))>',  # De : Nom <email@domain.com>
            r'From\s*:\s*[^<]*<([^>]+@([^>]+))>',  # From : Nom <email@domain.com>
            r'De\s*:\s*(\S+@(\S+\.\w+))',  # De : email@domain.com
            r'From\s*:\s*(\S+@(\S+\.\w+))',  # From : email@domain.com
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                # Extraire le domaine de l'email original
                email = match.group(1)
                domain = email.split("@")[-1] if "@" in email else ""
                if domain and domain not in ['rondot-poc.itspirit.ovh', 'rondot-sas.fr']:
                    # C'est probablement l'expéditeur original (client)
                    company = domain.split(".")[0].upper()
                    return company

        return None

    def _is_phone_number(self, code: str) -> bool:
        """Détecte si un code ressemble à un numéro de téléphone ou fax."""
        # Numéros français : 10 chiffres commençant par 0, ou 9 chiffres
        if len(code) == 10 and code[0] == '0':
            return True
        if len(code) == 9 and code[0] in '123456789':
            return True

        # Numéros internationaux : 11-15 chiffres avec préfixe pays
        if 11 <= len(code) <= 15:
            if code.startswith('33') and len(code) == 11:  # France international
                return True
            if code.startswith(('44', '41', '49', '39', '34', '351', '352', '1', '90')):  # Ajout Turquie (90)
                return True

        # Patterns téléphone : détection de structure répétitive
        if len(code) >= 10 and code.isdigit():
            pairs = [code[i:i+2] for i in range(0, min(len(code), 10), 2)]
            unique_pairs = set(pairs)
            # Si beaucoup de répétitions, probablement un téléphone
            if len(pairs) >= 4 and len(unique_pairs) <= len(pairs) * 0.6:
                return True

        # NOUVEAU: Numéros très longs (>= 11 chiffres) sont probablement des téléphones/fax
        # Les vrais codes produits ont rarement plus de 10 chiffres purement numériques
        if code.isdigit() and len(code) >= 11:
            return True

        return False

    def _is_false_positive_product(self, code: str) -> bool:
        """Détecte les faux positifs courants dans l'extraction de produits."""
        code_normalized = code.upper().replace('-', '').replace('_', '')

        # Liste noire de termes à exclure
        blacklist = {
            # Termes machines (anglais)
            'XAXIS', 'YAXIS', 'ZAXIS',
            'AAXIS', 'BAXIS', 'CAXIS',

            # Termes machines (turc)
            'XEKSENI', 'YEKSENI', 'ZEKSENI',
            'EKSENI',  # "axe" en turc

            # Mots courants français
            'CIJOINT', 'CIJOINTS', 'CIJOINTE', 'CIJOINTES',
            'ENPIECE', 'ENPIECES',

            # Mots courants anglais
            'ATTACHED', 'ATTACHMENT',
            'DRAWING', 'DRAWINGS',
            'SKETCH', 'SKETCHES',

            # Termes génériques
            'PIECE', 'PIECES', 'PART', 'PARTS',
            'ITEM', 'ITEMS', 'REF', 'REFERENCE',
        }

        # Vérifier si le code est dans la blacklist
        if code_normalized in blacklist:
            return True

        # Vérifier si le code CONTIENT un terme de la blacklist (ex: "X-AXIS" contient "XAXIS")
        for term in blacklist:
            if len(term) >= 4 and term in code_normalized:
                return True

        return False

    def _extract_products_from_text(self, body: str) -> List[ExtractedProduct]:
        """Extrait les références produits et quantités du texte."""
        products = []
        if not body:
            return products

        # Pattern pour les références produits (codes alphanumériques)
        ref_patterns = [
            r'(?:article|ref|référence|réf|reference|part|code)\s*(?:suivant|:)?\s*[:\s]*([A-Z0-9][-A-Z0-9]{5,})',
            r'\b(\d{8,})\b',  # Codes numériques longs (8+ chiffres)
            r'\b([A-Z]{2,}\d{4,})\b',  # Codes alphanumériques (ex: AB12345)
        ]

        # Pattern pour les quantités
        qty_patterns = [
            r'qt[eéy]\s*[:\s]*(\d+)',
            r'quantit[eé]\s*[:\s]*(\d+)',
            r'(\d+)\s*(?:pcs|pièces?|units?|unités?)',
            r'x\s*(\d+)',
        ]

        found_refs = set()
        for pattern in ref_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            for match in matches:
                ref = match.strip().upper()
                # Filtrer les numéros de téléphone ET les faux positifs courants
                if (ref and len(ref) >= 6 and ref not in found_refs
                    and not self._is_phone_number(ref)
                    and not self._is_false_positive_product(ref)):
                    found_refs.add(ref)

        # Trouver la quantité globale ou utiliser 1 par défaut
        quantity = 1
        for pattern in qty_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                try:
                    quantity = int(match.group(1))
                    break
                except ValueError:
                    pass

        # Créer les produits
        for ref in found_refs:
            products.append(ExtractedProduct(
                description=f"Article {ref}",
                quantity=quantity,
                reference=ref,
                unit="pcs"
            ))

        return products

    def _clean_html(self, html_content: str) -> str:
        """Nettoie le contenu HTML pour extraire le texte TOUT EN PRÉSERVANT LES ADRESSES EMAIL."""
        if not html_content:
            return ""

        # ÉTAPE 1: Décoder les entités HTML AVANT extraction des emails
        # (car les emails peuvent être encodés comme &lt;email@domain.com&gt;)
        text = html_content.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # ÉTAPE 2: Extraire et protéger les adresses email (maintenant décodées)
        # Pattern pour détecter les emails dans <email@domain.com>
        email_pattern = r'<([\w\.-]+@[\w\.-]+\.\w+)>'
        emails_found = []

        def save_email(match):
            """Remplace l'email par un placeholder et sauvegarde l'email"""
            email = match.group(1)
            placeholder = f"__EMAIL_{len(emails_found)}__"
            emails_found.append(email)
            return placeholder

        # Remplacer les emails par des placeholders
        text = re.sub(email_pattern, save_email, text)

        # ÉTAPE 3: Supprimer les balises HTML (maintenant sans risque pour les emails)
        text = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', text)
        text = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', text)
        text = re.sub(r'<[^>]+>', ' ', text)

        # ÉTAPE 4: Réinjecter les emails (sans les angle brackets pour éviter confusion HTML)
        for idx, email in enumerate(emails_found):
            placeholder = f"__EMAIL_{idx}__"
            text = text.replace(placeholder, email)  # Juste l'email, sans <>

        # ÉTAPE 5: Nettoyer les espaces
        text = re.sub(r'\s+', ' ', text)

        return text.strip()


# Instance singleton
_email_analyzer: Optional[EmailAnalyzer] = None


def get_email_analyzer() -> EmailAnalyzer:
    """Factory pattern pour obtenir l'instance de l'analyseur."""
    global _email_analyzer
    if _email_analyzer is None:
        _email_analyzer = EmailAnalyzer()
        logger.info("EmailAnalyzer instance created")
    return _email_analyzer


# Utilitaire pour extraire le texte des PDFs
async def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extrait le texte d'un PDF à partir de ses bytes.
    Utilise le PDFParser existant de file_parsers.py.
    """
    try:
        from services.file_parsers import PDFParser

        # Sauvegarder temporairement le PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            # Parser le PDF
            import fitz  # PyMuPDF

            doc = fitz.open(tmp_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            return text.strip()

        except ImportError:
            # Fallback pdfplumber
            try:
                import pdfplumber
                with pdfplumber.open(tmp_path) as pdf:
                    text = ""
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return text.strip()
            except ImportError:
                logger.warning("No PDF library available (pymupdf or pdfplumber)")
                return ""

        finally:
            # Nettoyer le fichier temporaire
            import os
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""
