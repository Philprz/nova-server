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
    # Français
    'devis', 'prix', 'rfq', 'demande de prix', 'offre de prix', 'chiffrage', 'tarif',
    'offre',  # "TR: INFO / OFFRE", "demande d'offre" etc.
    # Anglais
    'quotation', 'quote', 'price', 'request for quotation', 'request for quote',
    'spare parts', 'spare part', 'parts request', 'price request',
    'inquiry', 'enquiry',  # sujets RFQ courants en B2B industriel
]

QUOTE_KEYWORDS_BODY = [
    # Français
    'merci de nous faire un devis', 'demande de prix', 'demande de devis',
    'demande de chiffrage', 'demande chiffrage', 'pouvez-vous nous faire une offre',
    'nous souhaitons recevoir une offre', 'veuillez nous communiquer vos prix',
    'souhaitons obtenir un devis', 'veuillez nous faire un chiffrage',
    'pouvez-vous chiffrer', 'merci de chiffrer',
    'faire chiffrer', 'à chiffrer', 'le chiffrage', 'un chiffrage',
    'retourner le chiffrage', 'retourner un chiffrage', 'nous faire parvenir un chiffrage',
    'disponible chez vous', 'dispo chez vous', 'pièces dispo',
    'veuillez trouver ci-joint', 'ci-joint la demande',
    # Anglais — patterns courants dans les mails B2B industriels
    'please quote', 'please provide a quote', 'could you quote',
    'we would like a quotation', 'please send the offer', 'send the offer to',
    'request for price', 'find attached', 'please find attached',
    'could you please send us a quotation', 'send us a quotation',
    'please send us a quotation', 'could you share a price quote',
    'share a price quote', 'price quote for', 'quotation for the',
    'kindly quote', 'kindly provide a quotation', 'kindly send a quotation',
    'we need a quote', 'we need pricing', 'requesting a quote',
    'please provide pricing', 'can you provide a quote',
    'attached you will find', 'attached please find',
    'quotation for', 'prepare a quotation', 'prepare the quotation',
    'would like a quote', 'would like to receive a quote',
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
    ship_to: Optional[str] = None  # Lieu/site de livraison distinct du client (ex: "BDF")


class EmailAnalysisResult(BaseModel):
    classification: str  # QUOTE_REQUEST, PROBABLE_QUOTE, INFORMATION, OTHER
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

    # Référence commande client (Form No, PO No, etc.) → utilisée dans NumAtCard SAP
    customer_reference: Optional[str] = None

    # Signaux géographiques extraits du texte email (depuis email_matcher)
    detected_country: Optional[str] = None   # Code ISO pays détecté (ex: "BG", "GR")
    detected_city: Optional[str] = None      # Ville détectée (ex: "Plovdiv")
    auto_select_reason: Optional[str] = None  # Raison de l'auto-sélection ou de son absence

    # Risque client (vérification Pappers — non bloquant)
    client_risk: Optional[dict] = None  # {status, reason, source, raw}


# Prompt LLM pour l'analyse des emails
EMAIL_CLASSIFICATION_PROMPT = """Tu es un assistant spécialisé dans la classification des emails commerciaux pour une entreprise industrielle (RONDOT-SAS, fabricant de pièces industrielles).

Analyse cet email et détermine:
1. S'il s'agit d'une DEMANDE DE DEVIS (quote request) - un client qui demande des prix pour des produits/services
2. La confiance dans cette classification (high/medium/low)
3. Les informations extraites si c'est une demande de devis

TYPES DE CLASSIFICATION:
- "QUOTE_REQUEST": Demande de devis explicite, RFQ, demande de prix, demande de chiffrage (confiance haute)
- "PROBABLE_QUOTE": Email qui ressemble fortement à une demande de devis sans formulation explicite : pièces jointes techniques avec liste de pièces, forward d'un client demandant des prix, références produits industrielles + expéditeur professionnel, email en langue étrangère avec contexte commercial (confiance moyenne)
- "INFORMATION": Email informatif, confirmation de meeting, newsletter, notification
- "OTHER": Facture, commande confirmée, réclamation, autre type d'email

INDICES D'UNE DEMANDE DE DEVIS (toutes langues acceptées — français, anglais, allemand, turc, etc.) :
- Phrases explicites : "merci de nous faire un devis", "please quote", "demande de prix", "could you send us a quotation", "please share a price quote", "kindly provide pricing"
- Email forwardé (Fwd:/FW:) d'un client industriel avec liste de pièces ou références
- Corps contenant une liste de références produits / pièces détachées avec quantités
- Demande de délai de livraison ou de disponibilité stock
- Pièces jointes mentionnées (Excel, PDF) avec liste d'articles à chiffrer

ATTENTION :
- Un sujet technique (ex: numéro de commande, référence longue) ne disqualifie PAS un email : analyser LE CORPS
- Les emails en anglais ou dans d'autres langues doivent être traités comme les emails en français
- Un email forwardé doit être analysé sur le contenu forwardé, pas sur l'en-tête de transfert

EXTRACTION DES INFORMATIONS CLIENT (important pour validation):
- Nom entreprise: chercher dans la SIGNATURE DU VRAI EXPÉDITEUR (la personne qui demande le devis)
  * Si email forwardé (Fwd/FW) : l'expéditeur réel est dans le bloc "From:" du corps — extraire son nom ET son entreprise depuis sa signature
  * Ne pas prendre une entreprise mentionnée dans un fil de discussion antérieur ou dans un autre contexte
  * Prioriser : signature de l'expéditeur réel > domaine email expéditeur > en-tête From: dans le corps forwardé
- SIRET: chercher le numéro SIRET (14 chiffres) si présent dans la signature ou pièce jointe
- Téléphone: extraire si présent dans la signature de l'expéditeur réel
- Adresse: extraire l'adresse complète si présente dans la signature du vrai expéditeur

EXTRACTION DES PRODUITS:
- Description: description complète du produit
- Quantité: nombre d'unités demandées POUR CE PRODUIT SPÉCIFIQUE (sur la même ligne ou directement associé au produit)
- Unité: pcs, kg, m, l, etc.
- Référence: code produit, référence fournisseur si mentionnée

RÈGLES CRITIQUES POUR LES QUANTITÉS:
- N'extraire QUE les quantités directement associées à un produit (sur la même ligne que la description/référence du produit, ou avec indicateur clair comme "qté:", "qty:", "x2", "2 pcs")
- Par défaut à 1 si la quantité d'un produit n'est pas clairement indiquée
- IGNORER absolument les nombres suivants (NE JAMAIS les utiliser comme quantités):
  * Numéros de formulaire, de document, de commande (ex: "Formulaire 194", "BC n°194", "Devis 2567")
  * Numéros de page (ex: "Page 1/3")
  * Dates et années (ex: 2024, 2025)
  * Codes postaux (ex: 75001)
  * Numéros de téléphone ou fax
  * Numéros d'identification (SIRET, TVA, etc.)
  * Tout nombre qui n'est PAS sur la même ligne que la description ou référence d'un produit

RÈGLES CRITIQUES POUR LES PRODUITS:
- N'extraire QUE des produits/articles physiques réels (pièces, composants, matériaux)
- NE JAMAIS extraire comme produit : des mots communs d'une langue (ex: "e-posta" = email en turc, "e-postanın", "Anlık"), des adresses email, des URLs, des mentions de pièces jointes ("attached", "ci-joint"), des formules de politesse
- NE JAMAIS extraire comme produit : des éléments d'adresse postale (noms de rues, numéros de rue, fragments de ville/pays, codes postaux), des numéros de TVA/VAT/USt-IdNr (ex: "DE813794940", "FR12345678901"), des numéros d'enregistrement de société, des noms de rues ou fragments d'adresse (ex: "von-Siemens-Str", "au-Mont-d'Or", "Werner-von-Siemens"), des informations de pied de page/signature d'entreprise
- Si la liste de produits est dans une pièce jointe mentionnée mais pas dans le corps : laisser products = [] et indiquer dans notes que les produits sont en pièce jointe
- Une référence de commande (ex: "Bid Request No: 6000199732") est une NOTE, pas un produit

Réponds UNIQUEMENT en JSON valide (pas de texte avant ou après):
{
  "classification": "QUOTE_REQUEST|PROBABLE_QUOTE|INFORMATION|OTHER",
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

        # Détecter si c'est un forward et extraire l'expéditeur réel
        # Pour les expéditeurs internes (RONDOT IT), passer le sender_email pour
        # utiliser le DERNIER "De:" dans la chaîne (expéditeur original = le client)
        forward_info = self._extract_forward_info(clean_body, sender_email=sender_email)
        # Si pas de forward info depuis le corps, essayer depuis le sujet (cas SAP PO)
        if not forward_info or forward_info.get('email', '') == sender_email:
            subject_info = self._extract_client_from_subject(subject, sender_email)
            if subject_info:
                forward_info = subject_info
                logger.info("subject_client_extracted: subject=%r → company=%r", subject, subject_info['company'])
        forward_note = ""
        _fi_email = forward_info.get('email', '') if forward_info else ''
        if forward_info and _fi_email.lower() != sender_email.lower():
            parts = []
            if forward_info['name']:
                parts.append(f"nom={forward_info['name']}")
            if _fi_email:
                parts.append(f"email={_fi_email}")
            company_hint = forward_info['company']
            forward_note = (
                f"\n⚠️ CLIENT IDENTIFIÉ — société : {company_hint}"
                + (f" ({', '.join(parts)})" if parts else "")
                + f"\n→ NE PAS utiliser '{sender_name} <{sender_email}>' comme client — c'est le transitaire interne.\n"
            )
            logger.info(
                "forward_detected sender=%s real_client_email=%s company=%s",
                sender_email, _fi_email, company_hint
            )
        else:
            logger.info("no_forward_detected sender=%s forward_info=%s", sender_email, forward_info)

        # Construire le contexte pour le LLM
        email_context = f"""SUJET: {subject}

EXPÉDITEUR (boîte de réception RONDOT): {sender_name} <{sender_email}>{forward_note}

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

            # ── Correction déterministe du client sur emails forwardés ─────────
            # Si on a détecté un client réel (forward ou sujet SAP) différent de l'expéditeur,
            # on force le client_name indépendamment de ce que le LLM a dit.
            _fi_email_override = forward_info.get('email', '') if forward_info else ''
            if forward_info and _fi_email_override.lower() != sender_email.lower():
                detected_company = forward_info['company']
                if analysis.extracted_data is None:
                    analysis.extracted_data = ExtractedQuoteData()
                llm_client = (analysis.extracted_data.client_name or "").strip()
                if llm_client.lower() != detected_company.lower():
                    logger.info(
                        "client_override: LLM=%r → forced=%r (forward/subject detected)",
                        llm_client, detected_company
                    )
                    analysis.extracted_data.client_name = detected_company
                    if _fi_email_override:
                        analysis.extracted_data.client_email = _fi_email_override
            # ─────────────────────────────────────────────────────────────────

            # Grounding check : rejeter client_email halluciné si absent du corps
            if analysis.extracted_data and analysis.extracted_data.client_email:
                grounding_text_for_email = (clean_body + " " + " ".join(pdf_contents or [])).lower()
                extracted_emails = [
                    e.strip().lower()
                    for e in analysis.extracted_data.client_email.replace(';', ',').split(',')
                    if e.strip()
                ]
                grounded_emails = [e for e in extracted_emails if e in grounding_text_for_email]
                if not grounded_emails:
                    logger.info(
                        "[GROUNDING] client_email '%s' non trouvé dans le corps — supprimé (hallucination LLM)",
                        analysis.extracted_data.client_email
                    )
                    analysis.extracted_data.client_email = None

            # Filtrer les produits non-ancrés dans le texte de l'email
            # (élimine les produits hallucinés ou extraits d'un fil de discussion parasite)
            if analysis.extracted_data and analysis.extracted_data.products:
                # Inclure le contenu des PDFs dans le texte de référence pour le grounding
                grounding_text = clean_body
                if pdf_contents:
                    grounding_text += " " + " ".join(pdf_contents)
                body_norm_for_grounding = grounding_text.lower()
                grounded = [
                    p for p in analysis.extracted_data.products
                    if self._is_product_grounded(p, body_norm_for_grounding)
                ]
                discarded_count = len(analysis.extracted_data.products) - len(grounded)
                if grounded and discarded_count > 0:
                    logger.info(
                        "[GROUNDING] %d produit(s) non-ancrés supprimés (sur %d extraits par LLM)",
                        discarded_count, len(analysis.extracted_data.products)
                    )
                    analysis.extracted_data.products = grounded
                elif not grounded and discarded_count > 0:
                    logger.info(
                        "[GROUNDING] Filtre annulé : tous les %d produit(s) seraient supprimés "
                        "(produits probablement dans pièce jointe uniquement)",
                        len(analysis.extracted_data.products)
                    )
                    # Conserver les produits tels quels

                # Filtrer les faux-positifs adresses/TVA que le LLM a quand même extrait
                if analysis.extracted_data.products:
                    before_fp = len(analysis.extracted_data.products)
                    analysis.extracted_data.products = [
                        p for p in analysis.extracted_data.products
                        if not self._is_false_positive_product(p.reference or "")
                    ]
                    fp_removed = before_fp - len(analysis.extracted_data.products)
                    if fp_removed > 0:
                        logger.info(
                            "[FALSE_POSITIVE] %d produit(s) adresse/TVA supprimés post-LLM",
                            fp_removed
                        )

            # Correctif faux négatifs : si le pré-filtrage détecte clairement une demande de devis
            # (sujet/corps avec "chiffrage", "devis", etc.) avec confiance medium ou high,
            # on priorise le pré-filtrage sur le LLM (qui peut se tromper sur transferts, bilingue, etc.)
            if (
                quick_result["likely_quote"]
                and quick_result["confidence"] in ("high", "medium")
                and not analysis.is_quote_request
            ):
                # Pré-filtrage détecte un devis mais LLM dit non → PROBABLE_QUOTE (pas forçage direct)
                logger.info(
                    f"Override LLM: pre-filter detected quote (score={quick_result['score']}, "
                    f"rules={quick_result['matched_rules'][:3]}) -> upgrading to PROBABLE_QUOTE"
                )
                analysis.classification = "PROBABLE_QUOTE"
                analysis.is_quote_request = True
                analysis.confidence = "medium"
                analysis.reasoning = (
                    f"Probable devis (règles métier): {', '.join(quick_result['matched_rules'][:3])}. "
                    f"{analysis.reasoning or ''}"
                )[:500]

            # ── Extraction ship_to (moteur strict séparé) ────────────────────
            if analysis.is_quote_request or analysis.quick_filter_passed:
                try:
                    ship_to_text = clean_body
                    if pdf_contents:
                        ship_to_text = clean_body + "\n\n" + "\n\n".join(pdf_contents[:3])
                    ship_to = await self._extract_ship_to(ship_to_text)
                    if ship_to and analysis.extracted_data:
                        analysis.extracted_data.ship_to = ship_to
                        logger.info("ship_to extracted: %r", ship_to)
                except Exception as _st_err:
                    logger.warning("_extract_ship_to failed (non-blocking): %s", _st_err)
            # ─────────────────────────────────────────────────────────────────

            return analysis

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Fallback sur le pré-filtrage seul avec extraction regex
            return self._fallback_analysis(quick_result, sender_email, sender_name, clean_body)

    async def _extract_ship_to(self, text: str) -> Optional[str]:
        """
        Moteur d'extraction strict : retourne le lieu de livraison UNIQUEMENT si
        un pattern explicite est présent dans le texte. Jamais d'inférence.
        """
        SHIP_TO_SYSTEM = """Tu es un moteur d'extraction strict.

Objectif : extraire UNIQUEMENT une destination de livraison (ship_to) si elle est explicitement mentionnée et différente du client.

Règles OBLIGATOIRES :

1. Tu extrais UNIQUEMENT si un pattern explicite est présent :
- "deliver to"
- "ship to"
- "to destination"
- "livrer chez"
- "expédier à"
- "delivery address"

2. Tu n'infères JAMAIS.
3. Tu ne devines JAMAIS.
4. Si doute → retourner null.

5. Tu NE DOIS PAS confondre avec :
- client
- société émettrice
- adresse de facturation

6. Tu retournes STRICTEMENT un JSON valide :
{"ship_to": string | null}

7. Si aucune mention claire → {"ship_to": null}

FEW SHOTS (CRITIQUES)
Exemple 1 — positif
Email: Please deliver to BDF site in Lyon
Output: {"ship_to": "BDF site in Lyon"}

Exemple 2 — positif
Email: Livraison à effectuer chez BDF
Output: {"ship_to": "BDF"}

Exemple 3 — négatif
Email: Client: BDF
Output: {"ship_to": null}

Exemple 4 — négatif
Email: Send quotation to BDF
Output: {"ship_to": null}

Exemple 5 — négatif ambigu
Email: BDF mentioned in footer
Output: {"ship_to": null}

GUARDRAIL FINAL : Si tu n'es pas certain à 100% → retourne null."""

        if ANTHROPIC_API_KEY:
            try:
                headers = {
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 64,
                    "system": SHIP_TO_SYSTEM,
                    "messages": [{"role": "user", "content": text[:3000]}],
                    "temperature": 0.0
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    raw = response.json()["content"][0]["text"].strip()
                    data = json.loads(raw)
                    return data.get("ship_to") or None
            except Exception as e:
                logger.debug("_extract_ship_to claude error: %s", e)

        if OPENAI_API_KEY:
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=64,
                    temperature=0.0,
                    messages=[
                        {"role": "system", "content": SHIP_TO_SYSTEM},
                        {"role": "user", "content": text[:3000]},
                    ]
                )
                raw = resp.choices[0].message.content.strip()
                data = json.loads(raw)
                return data.get("ship_to") or None
            except Exception as e:
                logger.debug("_extract_ship_to openai error: %s", e)

        return None

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

        classification = data.get("classification", "OTHER")
        # PROBABLE_QUOTE → traité comme un devis (pipeline complet) mais conserve la classification
        is_quote_request = data.get("is_quote_request", False) or classification == "PROBABLE_QUOTE"

        return EmailAnalysisResult(
            classification=classification,
            confidence=data.get("confidence", "low"),
            is_quote_request=is_quote_request,
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

    # Domaines internes RONDOT à ignorer lors de la détection de forward
    _RONDOT_DOMAINS = {
        'rondot-poc.itspirit.ovh', 'rondot-sas.fr', 'rondot-sa.com',
        'it-spirit.com',  # prestataire IT
    }

    def _extract_forward_info(self, body: str, sender_email: str = "") -> Optional[dict]:
        """
        Détecte un email forwardé et extrait les infos de l'expéditeur réel.
        Travaille sur le texte NETTOYÉ (sans balises HTML, sans <> autour des emails).
        Retourne {'name': str, 'email': str, 'company': str} ou None.

        Pour les expéditeurs INTERNES (RONDOT IT), on prend le DERNIER "De:" trouvé
        dans la chaîne (= l'expéditeur original du fil, i.e. le vrai client).
        Pour les expéditeurs EXTERNES, on prend le PREMIER "De:" (direct forwarder).
        """
        if not body:
            return None

        # Email regex réutilisable
        EMAIL_RE = r'[\w\.\-\+]+@[\w\.\-]+\.\w+'

        # Expéditeur interne = RONDOT IT ou prestataire → prend le DERNIER "De:" dans le fil
        sender_domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""
        is_internal_sender = sender_domain in self._RONDOT_DOMAINS

        # --- Patterns sur texte nettoyé (les <> ont été retirés par _clean_html) ---

        # 1. "From: NOM PRENOM email@domain.com"  ou  "De: NOM email@domain.com"
        p_from_name_email = re.compile(
            r'(?:From|De)\s*:\s*(.{2,60}?)\s+(' + EMAIL_RE + r')',
            re.IGNORECASE
        )

        # 2. "From: email@domain.com" (sans nom)
        p_from_email_only = re.compile(
            r'(?:From|De)\s*:\s*(' + EMAIL_RE + r')',
            re.IGNORECASE
        )

        # 3. Gmail / style "NOM email@domain.com a écrit :" (sans "From:")
        p_gmail = re.compile(
            r'(.{2,60}?)\s+(' + EMAIL_RE + r')\s+(?:a[\u00a0\s]écrit|wrote|schrieb|ha scritto)',
            re.IGNORECASE
        )

        # 4. Format Outlook Exchange : première ligne = "NOM PRENOM email@domain.com >"
        # (l'angle bracket de fermeture > est préservé après _clean_html — l'ouvrant < est retiré)
        # Ex: "KADIR TERCAN KATERCAN@sisecam.com >"
        p_outlook_header = re.compile(
            r'^(.{2,60}?)\s+(' + EMAIL_RE + r')\s*>\s*$',
            re.IGNORECASE | re.MULTILINE
        )

        def _result(name: str, email_addr: str) -> Optional[dict]:
            domain = email_addr.split("@")[-1].lower()
            if domain not in self._RONDOT_DOMAINS:
                company = domain.split(".")[0].upper()
                return {'name': name.strip(), 'email': email_addr, 'company': company}
            return None

        # Collecter TOUS les matches "De:" (patterns 1 et 2)
        all_from_matches = []
        for m in p_from_name_email.finditer(body):
            res = _result(m.group(1), m.group(2))
            if res:
                all_from_matches.append(res)

        # Pattern 2 en fallback : "De: email" sans nom
        if not all_from_matches:
            for m in p_from_email_only.finditer(body):
                res = _result('', m.group(1))
                if res:
                    all_from_matches.append(res)

        if all_from_matches:
            # Expéditeur interne : le DERNIER "De:" = expéditeur original du fil (le vrai client)
            # Expéditeur externe : le PREMIER "De:" = le forwarder direct (le client)
            return all_from_matches[-1] if is_internal_sender else all_from_matches[0]

        # Pattern Gmail
        m = p_gmail.search(body)
        if m:
            res = _result(m.group(1), m.group(2))
            if res:
                return res

        # Pattern Outlook Exchange (en-tête de forward sans De:/From:)
        for m in p_outlook_header.finditer(body):
            res = _result(m.group(1), m.group(2))
            if res:
                # Pour expéditeur interne : prend le premier (= l'expéditeur réel du fil)
                # Pour expéditeur externe : même logique (premier forward = le client)
                return res

        return None

    def _extract_client_from_subject(self, subject: str, sender_email: str) -> Optional[dict]:
        """
        Extrait le nom client depuis le sujet d'un email interne (RONDOT IT).
        Sert de fallback quand aucun forward header n'est trouvé dans le corps.
        Format SAP courant : "[N°] NOM_CLIENT USINE VILLE FABRI--SAP_REF"
        Ex: "76 SISECAM CAM AMBALAJ ESKISEHIR FABRI--1000354990" → SISECAM
        """
        sender_domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""
        if sender_domain not in self._RONDOT_DOMAINS:
            return None  # Seulement pour les expéditeurs internes

        # Nettoyer les préfixes Re:/Fw: etc.
        subj = re.sub(r'^(?:Re|Fw|Fwd|Tr|TR|RE|FW)\s*:\s*', '', subject.strip(), flags=re.IGNORECASE).strip()

        # Format SAP : numéro puis nom en majuscules
        # "76 SISECAM ..." → groupe 1 = "SISECAM"
        m = re.match(r'^[0-9]+\s+([A-Z][A-Z0-9\-]{2,})', subj.upper())
        if m:
            company = m.group(1)
            blocklist = {'THE', 'FOR', 'FROM', 'NEW', 'OLD', 'REF', 'RFQ', 'CMD', 'PO', 'SPARE', 'PARTS'}
            if company not in blocklist:
                logger.info("subject_client: subject=%r → company=%r", subject, company)
                return {'name': '', 'email': '', 'company': company}

        return None

    def _extract_original_sender(self, body: str) -> Optional[str]:
        """Rétrocompatibilité — retourne juste le nom société."""
        info = self._extract_forward_info(body)
        return info['company'] if info else None

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

    # Préfixes/termes caractéristiques d'adresses et de données administratives
    # (TVA européenne, rue, info société) qui ne peuvent PAS être des références produit
    _ADDRESS_PREFIXES = re.compile(
        r'^(UST|UST-ID|USTIDNR|USTID|VAT|TVA|SIRET|SIREN|'
        r'STRNR|STEUERNR|HRB|HRNR|'          # registre commercial allemand
        r'VONSIEMENS|WERNERVON|'              # noms de rues allemands courants
        r'AUMONTD|PARC|ALLEE|AVENUE|'        # fragments d'adresse français
        r'GEWERBE|INDUSTRIESTR|GEWERBERING|' # zones industrielles
        r'POSTFACH|POBOX)',                   # boîtes postales
        re.IGNORECASE
    )
    # Motif : code fiscal/TVA européen (2 lettres pays + 8-12 chiffres)
    _VAT_PATTERN = re.compile(r'^[A-Z]{2}\d{8,12}$')

    def _is_false_positive_product(self, code: str) -> bool:
        """Détecte les faux positifs courants dans l'extraction de produits."""
        code_normalized = code.upper().replace('-', '').replace('_', '').replace(' ', '')

        # Numéros de TVA européens (ex: DE813794940, FR12345678901)
        if self._VAT_PATTERN.match(code_normalized):
            return True

        # Préfixes d'adresse / données administratives
        if self._ADDRESS_PREFIXES.match(code_normalized):
            return True

        # Termes explicites d'adresse (fragments de noms de rue courants)
        address_fragments = {
            'STR', 'STRASSE', 'STRAßE', 'STREET', 'AVENUE', 'BOULEVARD',
            'AUMONTD',  # "au-Mont-d'Or"
        }
        for frag in address_fragments:
            if code_normalized.endswith(frag) and len(code_normalized) > len(frag) + 2:
                return True

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

            # Données administratives
            'USTIDNR', 'USTID',
        }

        # Vérifier si le code est dans la blacklist
        if code_normalized in blacklist:
            return True

        # Vérifier si le code CONTIENT un terme de la blacklist (ex: "X-AXIS" contient "XAXIS")
        for term in blacklist:
            if len(term) >= 4 and term in code_normalized:
                return True

        return False

    def _is_product_grounded(self, product: "ExtractedProduct", body_norm: str) -> bool:
        """
        Vérifie qu'un produit extrait par le LLM est réellement ancré dans le texte de l'email.

        Un produit est "ancré" si :
        - Sa référence (nettoyée de la ponctuation) apparaît dans le corps, OU
        - Au moins 2 de ses mots significatifs (≥5 chars) apparaissent dans le corps.

        Objectif : éliminer les produits hallucinés ou extraits d'un fil de discussion
        sans rapport avec la demande actuelle.
        """
        # Normalisation du corps (déjà normalisé, mais on s'assure)
        body_lower = body_norm.lower()

        # --- Vérification par référence ---
        ref = product.reference or ""
        if ref:
            ref_clean = re.sub(r'[^a-z0-9]', '', ref.lower())
            body_clean = re.sub(r'[^a-z0-9]', '', body_lower)
            if len(ref_clean) >= 4 and ref_clean in body_clean:
                return True

        # --- Vérification par mots de la description ---
        desc = product.description or ""
        if desc:
            sig_words = re.findall(r'\b\w{5,}\b', desc.lower())
            if sig_words:
                matches = sum(1 for w in sig_words if w in body_lower)
                threshold = 1 if len(sig_words) <= 2 else 2
                if matches >= threshold:
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

        # ÉTAPE 3b: Préserver la structure des tableaux et blocs
        # Remplacer les fins de cellule/ligne par espace/newline pour garder la structure
        # Ex: <tr><td>HST-117-01</td><td>Size 01</td><td>48</td></tr>
        #  → "HST-117-01 Size 01 48\n"
        text = re.sub(r'</td>|</th>', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'</tr>|</p>|<br\s*/?>|</div>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)

        # ÉTAPE 4: Réinjecter les emails (sans les angle brackets pour éviter confusion HTML)
        for idx, email in enumerate(emails_found):
            placeholder = f"__EMAIL_{idx}__"
            text = text.replace(placeholder, email)  # Juste l'email, sans <>

        # ÉTAPE 5: Nettoyer les espaces (par ligne, sans écraser les sauts de ligne)
        lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)

        return text


# Instance singleton
_email_analyzer: Optional[EmailAnalyzer] = None


def get_email_analyzer() -> EmailAnalyzer:
    """Factory pattern pour obtenir l'instance de l'analyseur."""
    global _email_analyzer
    if _email_analyzer is None:
        _email_analyzer = EmailAnalyzer()
        logger.info("EmailAnalyzer instance created")
    return _email_analyzer


# ---------------------------------------------------------------------------
# Utilitaires pour extraire le texte des PDFs
# ---------------------------------------------------------------------------

# Unités de quantité reconnues (insensible à la casse)
_QTY_UNIT_WORDS = frozenset({
    'adet', 'pcs', 'pc', 'pieces', 'pièces', 'units', 'unités',
    'stk', 'stück', 'ea', 'each', 'qty', 'qté',
})

# Bandes de colonnes du formulaire Sheppee / Marmara Cam (coordonnées PDF en points)
_COL_QTY_X_MIN = 360      # Colonne "Quantity"  : x >= 360
_COL_ROWNO_X_MAX = 70     # Colonne "Row No"    : x <= 70
_COL_DETAIL_X_MIN = 200   # Colonne "Material Detail" : x >= 200
_COL_NAME_X_MIN = 70      # Colonne "Material Name"   : 70 <= x < 200
_COL_NAME_X_MAX = 200


def _extract_offer_request_form_text(tmp_path: str) -> str:
    """
    Extraction structurée d'un 'Offer Request Form' basée sur les coordonnées de mots (PyMuPDF).

    Stratégie :
      1. Pour chaque page, lire les mots avec leurs coordonnées X/Y.
      2. Identifier la colonne "Quantity" (x >= 360) et extraire les paires (nombre, unité).
      3. Identifier la colonne "Row No" (x <= 70) et extraire les entiers dans l'ordre Y.
      4. Identifier la colonne "Material Detail" (x >= 200) et extraire les codes après "CODE:".
      5. Associer par index (même ordre Y dans le document).
      6. Sérialiser en "Row N: CODE - DESC - QTY Adet" lisible par _extract_offer_request_rows().

    Fonctionnement sans "Adet" :
      Les colonnes sont identifiées par POSITION (x/y), pas par le mot "Adet".
      Toute valeur numérique dans la colonne Quantity est une quantité valide,
      quelle que soit l'unité (Adet, pcs, unités, ou simple nombre).

    Retourne "" si le PDF n'est pas un Offer Request Form reconnu (fallback vers texte brut).
    """
    try:
        import fitz
    except ImportError:
        return ""

    all_rows: Dict[int, Dict] = {}   # row_no → {code, qty, desc}
    plain_text_pages: List[str] = []

    try:
        doc = fitz.open(tmp_path)
    except Exception as e:
        logger.warning(f"[PDF COORDS] fitz.open failed: {e}")
        return ""

    for page in doc:
        plain_text_pages.append(page.get_text())
        words = page.get_text('words')  # liste de (x0, y0, x1, y1, text, ...)

        # Pré-condition : la page doit contenir au moins un mot d'unité de quantité
        # OU la colonne "Quantity" doit être détectée via des décimaux à x >= QTY_X_MIN
        texts_lower = {w[4].lower() for w in words}
        has_unit = bool(texts_lower & _QTY_UNIT_WORDS)
        # Si pas d'unité, vérifier s'il y a des décimaux dans la zone Qty (format "2,00")
        has_qty_decimals = any(
            w[0] >= _COL_QTY_X_MIN and re.match(r'^\d+[.,]\d+$', w[4])
            for w in words
        )
        if not has_unit and not has_qty_decimals:
            continue  # Pas un tableau Offer Request sur cette page

        # --- 1. Quantités dans la colonne Qty (x >= QTY_X_MIN) ---
        qty_col = sorted(
            [(w[1], w[0], w[4]) for w in words if w[0] >= _COL_QTY_X_MIN],
            key=lambda x: x[0],  # trier par Y
        )

        qty_values: List[tuple] = []  # [(qty_int, y_position)]
        i = 0
        while i < len(qty_col):
            y, x, text = qty_col[i]
            if re.match(r'^\d+[.,]\d+$', text):
                qty_int = int(float(text.replace(',', '.')))
                # Chercher une unité dans les prochains mots de la même colonne (y proche)
                found_unit = False
                for j in range(i + 1, min(i + 4, len(qty_col))):
                    next_y, _, next_text = qty_col[j]
                    if abs(next_y - y) <= 30 and next_text.lower() in _QTY_UNIT_WORDS:
                        qty_values.append((qty_int, y))
                        i = j + 1
                        found_unit = True
                        break
                if not found_unit:
                    # Pas d'unité trouvée mais le nombre est dans la colonne Qty → accepter quand même
                    # (cas de PDF sans mot d'unité, juste un chiffre)
                    qty_values.append((qty_int, y))
                    i += 1
            else:
                i += 1

        if not qty_values:
            continue

        # --- 2. Row No dans la colonne RowNo (x <= ROWNO_X_MAX) ---
        rowno_with_y = sorted(
            [(w[1], int(w[4])) for w in words if w[0] <= _COL_ROWNO_X_MAX and w[4].isdigit()],
            key=lambda x: x[0],  # trier par Y
        )
        rowno_values = [rn for (_, rn) in rowno_with_y]

        # --- 3. Codes : mot après "CODE:" dans la colonne Detail (x >= DETAIL_X_MIN) ---
        detail_sorted = sorted(
            [(w[0], w[1], w[4]) for w in words if w[0] >= _COL_DETAIL_X_MIN],
            key=lambda w: (w[1], w[0]),  # Y puis X
        )
        code_values: List[tuple] = []  # [(code_str, y_position)]
        for didx, (dx, dy, dtext) in enumerate(detail_sorted):
            if dtext.upper() == 'CODE:':
                # Chercher le code sur la même ligne OU la ligne suivante
                # (certains PDFs renvoient le code à la ligne, ex: "SHEPPEE CODE:\nC233-50AT10-1940G3)")
                nearby = [
                    (nx, ny, nt) for (nx, ny, nt) in detail_sorted[didx + 1:]
                    if abs(ny - dy) <= 15  # tolérance élargie pour codes à la ligne suivante
                ]
                if nearby:
                    raw_code = nearby[0][2]
                    # Extraire le code en ignorant les caractères non-valides (ex: ")")
                    code_match = re.match(r'([A-Z0-9][A-Z0-9\-\.]{2,})', raw_code, re.IGNORECASE)
                    if code_match:
                        code_values.append((code_match.group(1), dy))
        code_values.sort(key=lambda x: x[1])
        codes = [c for (c, _) in code_values]

        # --- 4. Associer par index (même ordre Y dans le document) ---
        n = min(len(qty_values), len(rowno_values), len(codes))
        if n == 0:
            logger.debug(
                f"[PDF COORDS] Page sans correspondance complète: "
                f"qtys={len(qty_values)}, rownos={len(rowno_values)}, codes={len(codes)}"
            )
            continue

        for idx in range(n):
            qty_val, qty_y = qty_values[idx]
            row_no = rowno_values[idx]
            code = codes[idx]

            # Description depuis la colonne Material Name (70 <= x < 200) autour de qty_y
            name_words = [
                w[4] for w in words
                if _COL_NAME_X_MIN <= w[0] < _COL_NAME_X_MAX and abs(w[1] - qty_y) <= 55
            ]
            description = ' '.join(name_words[:6]) if name_words else 'PART'

            all_rows[row_no] = {'code': code, 'qty': qty_val, 'desc': description}

    doc.close()

    if not all_rows:
        logger.debug("[PDF COORDS] Aucun Offer Request Form détecté dans le PDF")
        return ""

    # Sérialiser en format "Row N: CODE - DESC - QTY Adet"
    # → lisible par email_matcher._extract_offer_request_rows()
    structured_lines = []
    for row_no in sorted(all_rows.keys()):
        row = all_rows[row_no]
        line = f"Row {row_no}: {row['code']} - {row['desc']} - {row['qty']} Adet"
        structured_lines.append(line)

    plain_text = '\n'.join(plain_text_pages)
    structured = '\n'.join(structured_lines)

    logger.info(
        f"[PDF COORDS] Offer Request Form extrait : {len(all_rows)} lignes "
        f"(Row {min(all_rows)} → Row {max(all_rows)})"
    )
    return plain_text + "\n\n" + structured


async def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extrait le texte d'un PDF à partir de ses bytes.

    Stratégie (par priorité) :
      1. Détection Offer Request Form via coordonnées PyMuPDF (colonne-aware)
         → produit "Row N: CODE - DESC - QTY Adet" pour _extract_offer_request_rows()
      2. Texte brut PyMuPDF (fallback pour PDFs non-tabulaires)
      3. Texte brut pdfplumber (fallback si PyMuPDF absent)
    """
    try:
        # Sauvegarder temporairement le PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            import fitz  # PyMuPDF

            # --- Tentative 1 : Offer Request Form avec coordonnées ---
            structured = _extract_offer_request_form_text(tmp_path)
            if structured:
                return structured

            # --- Tentative 2 : Texte brut PyMuPDF (comportement existant) ---
            doc = fitz.open(tmp_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text.strip()

        except ImportError:
            # --- Fallback : pdfplumber (comportement existant inchangé) ---
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
            import os
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""
