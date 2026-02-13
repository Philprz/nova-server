"""
Orchestrateur du workflow Mail-to-Biz RONDOT.

Workflow séquentiel strict:
1. Log WEBHOOK_RECEIVED
2. LLM Analysis → email_analyzer.analyze_email()
3. Log LLM_ANALYSIS_COMPLETE
4. SAP Client Search → email_matcher.match_clients()
5. Log SAP_CLIENT_SEARCH_COMPLETE
6. SAP Products Search → email_matcher.match_products()
7. Log SAP_PRODUCTS_SEARCH_COMPLETE
8. Pricing → pricing_engine.calculate_price()
9. Log PRICING_COMPLETE
10. Build quote_draft structure stricte
11. Persist → quote_repo.create_quote_draft()
12. Log QUOTE_DRAFT_CREATED

IMPORTANT: Wrapper des services existants - AUCUNE modification de code existant.
Toutes requêtes SAP effectuées UNE SEULE FOIS ici.
"""

import logging
import uuid
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MailProcessor:
    """
    Orchestrateur du workflow mail-to-biz.

    Responsabilités:
    - Orchestrer LLM analysis + SAP matching + Pricing
    - Logger chaque étape
    - Construire quote_draft structure stricte
    - Persister résultats

    Services wrappés (pas de modification):
    - email_analyzer (LLM analysis)
    - email_matcher (SAP matching)
    - pricing_engine (calcul prix)
    """

    def __init__(self):
        # Import ici pour éviter circular dependencies
        from services.email_analyzer import get_email_analyzer
        from services.email_matcher import get_email_matcher
        from services.pricing_engine import get_pricing_engine
        from services.quote_repository import get_quote_repository
        from services.mail_processing_log_service import get_mail_processing_log_service

        self.email_analyzer = get_email_analyzer()
        self.email_matcher = get_email_matcher()
        self.pricing_engine = get_pricing_engine()
        self.quote_repo = get_quote_repository()
        self.log_service = get_mail_processing_log_service()

    async def process_incoming_email(
        self,
        mail_id: str,
        email_payload: Dict[str, Any]
    ) -> "QuoteDraft":
        """
        Workflow complet traitement email avec persistance stricte.

        Args:
            mail_id: ID email Microsoft (ex: "AAMk...abc123")
            email_payload: Données complètes email
                {
                    "subject": "Demande devis urgent",
                    "body": "...",
                    "from_address": "contact@marmaracam.com",
                    "from_name": "Marmara Cam",
                    "pdf_contents": [...]  # Optionnel
                }

        Returns:
            QuoteDraft avec toutes données SAP persistées

        Raises:
            Exception: Si erreur critique dans workflow

        Workflow:
            1. Log WEBHOOK_RECEIVED
            2-3. LLM Analysis
            4-5. SAP Client Search
            6-7. SAP Products Search
            8-9. Pricing
            10. Build quote_draft structure
            11-12. Persist + Log
        """
        try:
            # ÉTAPE 1: Log réception
            self.log_service.log_step(mail_id, "WEBHOOK_RECEIVED", "SUCCESS")
            logger.info(f"🚀 Processing email: {mail_id[:20]}...")

            # ÉTAPE 2: LLM Analysis
            self.log_service.log_step(mail_id, "LLM_ANALYSIS_START", "PENDING")

            llm_result = await self.email_analyzer.analyze_email(
                subject=email_payload.get("subject", ""),
                body=email_payload.get("body", ""),
                sender_email=email_payload.get("from_address", ""),
                sender_name=email_payload.get("from_name", ""),
                pdf_contents=email_payload.get("pdf_contents", [])
            )

            is_quote_request = llm_result.is_quote_request if llm_result else False

            self.log_service.log_step(
                mail_id,
                "LLM_ANALYSIS_COMPLETE",
                "SUCCESS",
                f"is_quote_request={is_quote_request}"
            )

            # ÉTAPE 4: SAP Matching (client + produits)
            # Préparer texte pour matching
            body_text = email_payload.get("body", "")
            pdf_contents = email_payload.get("pdf_contents", [])
            if pdf_contents:
                body_text += " " + " ".join(pdf_contents)

            # Clean HTML si nécessaire
            clean_text = self.email_analyzer._clean_html(body_text)

            self.log_service.log_step(mail_id, "SAP_MATCHING_START", "PENDING")

            # Matching via email_matcher existant
            match_result = await self.email_matcher.match_email(
                body=clean_text,
                sender_email=email_payload.get("from_address", ""),
                subject=email_payload.get("subject", "")
            )

            # Déterminer client status
            client_code = None
            client_status = "NOT_FOUND"

            if match_result.best_client:
                if match_result.best_client.score >= 95:
                    client_code = match_result.best_client.card_code
                    client_status = "FOUND"
                elif len(match_result.clients) > 1:
                    client_status = "AMBIGUOUS"
                else:
                    client_code = match_result.best_client.card_code
                    client_status = "FOUND"

            self.log_service.log_step(
                mail_id,
                "SAP_CLIENT_SEARCH_COMPLETE",
                "SUCCESS",
                f"client_status={client_status}, matches={len(match_result.clients)}"
            )

            # ÉTAPE 7: Build lines structure avec métadonnées SAP complètes
            lines = []
            products_found = 0

            for product in match_result.products:
                # Déterminer sap_status
                sap_status = "NOT_FOUND" if product.not_found_in_sap else (
                    "FOUND" if product.score >= 95 else "AMBIGUOUS"
                )

                if sap_status == "FOUND":
                    products_found += 1

                # Déterminer search_type depuis match_reason
                search_type = self._determine_search_type(product.match_reason)

                # Build ligne stricte
                line = {
                    "line_id": str(uuid.uuid4()),
                    "supplier_code": product.item_code,  # Code externe/fournisseur
                    "description": product.item_name,
                    "quantity": product.quantity,
                    "sap_item_code": product.item_code if not product.not_found_in_sap else None,
                    "sap_status": sap_status,
                    "sap_price": product.unit_price,  # Peut être None
                    "search_metadata": {
                        "search_type": search_type,
                        "sap_query_used": f"ItemCode search '{product.item_code}'",
                        "search_timestamp": datetime.utcnow().isoformat() + "Z",
                        "match_score": product.score
                    }
                }
                lines.append(line)

            self.log_service.log_step(
                mail_id,
                "SAP_PRODUCTS_SEARCH_COMPLETE",
                "SUCCESS",
                f"products_found={products_found}/{len(lines)}"
            )

            # ÉTAPE 9: Pricing (déjà fait par pricing_engine dans match_result)
            self.log_service.log_step(
                mail_id,
                "PRICING_COMPLETE",
                "SUCCESS",
                f"lines_with_price={sum(1 for l in lines if l['sap_price'] is not None)}"
            )

            # ÉTAPE 11: Persist quote_draft
            quote_id = self.quote_repo.create_quote_draft(
                mail_id=mail_id,
                raw_payload=email_payload,
                client_code=client_code,
                client_status=client_status,
                lines=lines
            )

            self.log_service.log_step(
                mail_id,
                "QUOTE_DRAFT_CREATED",
                "SUCCESS",
                f"quote_id={quote_id}"
            )

            logger.info(
                f"✅ Quote draft créé: {quote_id} pour mail {mail_id[:20]}... "
                f"(client: {client_status}, produits: {products_found}/{len(lines)})"
            )

            # Récupérer quote_draft complet pour retour
            quote_draft = self.quote_repo.get_quote_draft(quote_id)

            return quote_draft

        except Exception as e:
            self.log_service.log_step(
                mail_id,
                "PROCESSING_ERROR",
                "ERROR",
                f"{type(e).__name__}: {str(e)}"
            )
            logger.error(f"❌ Error processing email {mail_id}: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _determine_search_type(self, match_reason: str) -> str:
        """
        Détermine le type de recherche depuis match_reason.

        Args:
            match_reason: Raison du match (ex: "Code exact trouvé")

        Returns:
            EXACT | FUZZY | HISTORICAL
        """
        reason_lower = match_reason.lower()

        if "code exact" in reason_lower or "exact" in reason_lower:
            return "EXACT"
        elif "mapping" in reason_lower or "appris" in reason_lower or "historique" in reason_lower:
            return "HISTORICAL"
        else:
            return "FUZZY"


# Singleton instance
_mail_processor: Optional[MailProcessor] = None


def get_mail_processor() -> MailProcessor:
    """Factory pattern pour obtenir l'instance unique."""
    global _mail_processor
    if _mail_processor is None:
        _mail_processor = MailProcessor()
        logger.info("MailProcessor singleton created")
    return _mail_processor
