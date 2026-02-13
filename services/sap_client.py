"""
Client SAP centralisé - Isolation de TOUS les appels SAP Business One.

Ce module wrapper les services existants:
- email_matcher.py → search_client(), search_item()
- pricing_engine.py → get_item_price()

Chaque fonction retourne métadonnées complètes:
- status (FOUND | NOT_FOUND | AMBIGUOUS)
- matches[] avec scores
- query_used (pour traçabilité)
- timestamp (ISO format)

IMPORTANT: Un seul module fait appels SAP - traçabilité centralisée.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SAPClientSearchResult(BaseModel):
    """
    Résultat de recherche client dans SAP avec métadonnées complètes.

    status: FOUND | NOT_FOUND | AMBIGUOUS
    card_code: Code SAP du client (si FOUND)
    matches: Liste des matchs trouvés avec scores
    query_used: Query SAP exécutée (traçabilité)
    timestamp: Moment de la recherche
    """
    status: str
    card_code: Optional[str] = None
    matches: List[Dict[str, Any]] = []
    query_used: str
    timestamp: str


class SAPItemSearchResult(BaseModel):
    """
    Résultat de recherche article dans SAP avec métadonnées complètes.

    status: FOUND | NOT_FOUND | AMBIGUOUS
    item_code: Code SAP de l'article (si FOUND)
    item_name: Nom article
    matches: Liste des matchs trouvés avec scores
    query_used: Query SAP exécutée (traçabilité)
    timestamp: Moment de la recherche
    """
    status: str
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    matches: List[Dict[str, Any]] = []
    query_used: str
    timestamp: str


class SAPClient:
    """
    Client SAP centralisé - Wrapper des services existants.

    Responsabilités:
    - Centraliser TOUS les appels SAP
    - Ajouter métadonnées complètes (query, timestamp, scores)
    - Traçabilité centralisée

    Services wrappés:
    - email_matcher (matching client/produits)
    - pricing_engine (calcul prix)
    """

    def __init__(self):
        # Import ici pour éviter circular dependencies
        from services.email_matcher import get_email_matcher
        from services.pricing_engine import get_pricing_engine

        self.email_matcher = get_email_matcher()
        self.pricing_engine = get_pricing_engine()

    async def search_client(
        self,
        name: str,
        email: Optional[str] = None
    ) -> SAPClientSearchResult:
        """
        Recherche client dans SAP avec métadonnées complètes.

        Args:
            name: Nom client (ex: "MARMARA CAM")
            email: Email client (optionnel, ex: "contact@marmaracam.com")

        Returns:
            SAPClientSearchResult avec:
            - status: FOUND | NOT_FOUND | AMBIGUOUS
            - card_code: "C00042" (si FOUND)
            - matches: [{"card_code", "card_name", "score", "match_reason"}]
            - query_used: Description query SAP
            - timestamp: ISO datetime

        Wrapper:
            email_matcher.match_clients() existant
        """
        # Assurer cache SAP chargé
        await self.email_matcher.ensure_cache()

        # Extraire domaines email
        text = f"{name} {email or ''}"
        domains = self.email_matcher._extract_email_domains(text, email or "")

        # Matching via email_matcher existant
        matches = self.email_matcher._match_clients(text, domains)

        # Déterminer status
        status = "NOT_FOUND"
        card_code = None

        if matches:
            best = matches[0]
            if best.score >= 95 and len(matches) == 1:
                status = "FOUND"
                card_code = best.card_code
            elif len(matches) > 1 and matches[1].score >= 85:
                status = "AMBIGUOUS"
            else:
                status = "FOUND"
                card_code = best.card_code

        # Build résultat avec métadonnées
        return SAPClientSearchResult(
            status=status,
            card_code=card_code,
            matches=[
                {
                    "card_code": m.card_code,
                    "card_name": m.card_name,
                    "score": m.score,
                    "match_reason": m.match_reason
                }
                for m in matches[:5]  # Top 5 matches
            ],
            query_used=f"Fuzzy match '{name}' + domain search '{email or 'N/A'}'",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    async def search_item(
        self,
        code: str,
        description: Optional[str] = None,
        supplier_card_code: Optional[str] = None
    ) -> SAPItemSearchResult:
        """
        Recherche article dans SAP avec métadonnées complètes.

        Args:
            code: Code article fournisseur (ex: "HST-117-03")
            description: Description article (optionnel)
            supplier_card_code: Code fournisseur (optionnel, pour mapping)

        Returns:
            SAPItemSearchResult avec:
            - status: FOUND | NOT_FOUND | AMBIGUOUS
            - item_code: "C315-6305RS" (code SAP RONDOT)
            - item_name: "SIZE 3 PUSHER BLADE"
            - matches: [{"item_code", "item_name", "score", "match_reason"}]
            - query_used: Description query SAP
            - timestamp: ISO datetime

        Wrapper:
            email_matcher._match_single_product_intelligent() existant
        """
        # Assurer cache SAP chargé
        await self.email_matcher.ensure_cache()

        # Matching via email_matcher existant
        text = f"{code} {description or ''}"
        matched_product = self.email_matcher._match_single_product_intelligent(
            code=code,
            description=description or "",
            text=text,
            supplier_card_code=supplier_card_code
        )

        # Cas NOT_FOUND
        if not matched_product or matched_product.not_found_in_sap:
            return SAPItemSearchResult(
                status="NOT_FOUND",
                item_code=None,
                item_name=None,
                matches=[],
                query_used=f"ItemCode exact + fuzzy search '{code}'",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

        # Déterminer status
        status = "FOUND" if matched_product.score >= 95 else "AMBIGUOUS"

        return SAPItemSearchResult(
            status=status,
            item_code=matched_product.item_code,
            item_name=matched_product.item_name,
            matches=[{
                "item_code": matched_product.item_code,
                "item_name": matched_product.item_name,
                "score": matched_product.score,
                "match_reason": matched_product.match_reason
            }],
            query_used=f"ItemCode exact + fuzzy search '{code}'",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    async def get_item_price(
        self,
        item_code: str,
        card_code: str,
        quantity: float
    ) -> Optional[float]:
        """
        Calcule prix intelligent via pricing_engine.

        Args:
            item_code: Code SAP article (ex: "C315-6305RS")
            card_code: Code SAP client (ex: "C00042")
            quantity: Quantité (ex: 50)

        Returns:
            Prix calculé (float) ou None si erreur

        Wrapper:
            pricing_engine.calculate_price() existant
            Utilise CAS 1/2/3/4 automatiquement
        """
        from services.pricing_models import PricingContext

        try:
            context = PricingContext(
                item_code=item_code,
                card_code=card_code,
                quantity=quantity,
                supplier_price=None,  # Sera récupéré automatiquement
                apply_margin=45.0  # Marge par défaut RONDOT
            )

            result = await self.pricing_engine.calculate_price(context)

            if result.success and result.decision:
                logger.info(
                    f"💰 Prix calculé: {result.decision.calculated_price} EUR "
                    f"({result.decision.case_type}) pour {item_code}"
                )
                return result.decision.calculated_price
            else:
                logger.warning(
                    f"⚠️ Pricing failed for {item_code}: {result.error}"
                )
                return None

        except Exception as e:
            logger.error(f"❌ Error calculating price for {item_code}: {e}")
            return None


# Singleton instance
_sap_client: Optional[SAPClient] = None


def get_sap_client() -> SAPClient:
    """Factory pattern pour obtenir l'instance unique."""
    global _sap_client
    if _sap_client is None:
        _sap_client = SAPClient()
        logger.info("SAPClient singleton created")
    return _sap_client
