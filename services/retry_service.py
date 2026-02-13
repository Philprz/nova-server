"""
Service de relance recherche SAP pour ligne isolée.

Permet retry sans refaire tout le workflow mail-to-biz:
- Récupère quote_draft existant
- Relance SAP uniquement pour ligne spécifiée
- Update UNIQUEMENT cette ligne dans DB
- Log RETRY_LINE_SEARCH

Cas d'usage:
1. Utilisateur clique "Relancer recherche" dans UI
2. Utilisateur saisit code RONDOT manuellement
3. Article créé en parallèle dans SAP
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LineRetryResult(BaseModel):
    """
    Résultat d'une relance recherche SAP pour ligne isolée.

    success: True si update réussi
    sap_item_code: Nouveau code SAP (ou None)
    sap_status: FOUND | NOT_FOUND | AMBIGUOUS
    sap_price: Nouveau prix (ou None)
    updated_at: Timestamp de l'update
    """
    success: bool
    sap_item_code: Optional[str] = None
    sap_status: str
    sap_price: Optional[float] = None
    updated_at: str


class RetryService:
    """
    Service de relance recherche SAP pour ligne isolée.

    Responsabilités:
    - Relancer SAP pour UNE ligne uniquement
    - Calculer prix si trouvé
    - Update ligne dans DB (UNIQUEMENT celle-ci)
    - Logger RETRY_LINE_SEARCH

    Cas d'usage:
    - Retry automatique (fuzzy élargi)
    - Retry manuel (code saisi par utilisateur)
    """

    def __init__(self):
        # Import ici pour éviter circular dependencies
        from services.sap_client import get_sap_client
        from services.quote_repository import get_quote_repository
        from services.mail_processing_log_service import get_mail_processing_log_service

        self.sap_client = get_sap_client()
        self.quote_repo = get_quote_repository()
        self.log_service = get_mail_processing_log_service()

    async def retry_line_search(
        self,
        quote_id: str,
        line_id: str,
        manual_code: Optional[str] = None
    ) -> LineRetryResult:
        """
        Relance recherche SAP pour une ligne uniquement.

        Args:
            quote_id: UUID du quote_draft
            line_id: UUID de la ligne à relancer
            manual_code: Code RONDOT saisi manuellement (optionnel)

        Returns:
            LineRetryResult avec:
            - success: True si update réussi
            - sap_item_code: Nouveau code SAP
            - sap_status: FOUND | NOT_FOUND | AMBIGUOUS
            - sap_price: Nouveau prix
            - updated_at: Timestamp

        Raises:
            ValueError: Si quote_id ou line_id non trouvé

        Workflow:
            1. Récupérer quote_draft
            2. Identifier ligne à relancer
            3. Si manual_code fourni → Chercher SAP avec code exact
            4. Sinon → Relancer fuzzy search
            5. Calculer prix si trouvé
            6. Update ligne dans DB (UNIQUEMENT celle-ci)
            7. Log RETRY_LINE_SEARCH
        """
        try:
            # 1. Récupérer quote_draft
            quote = self.quote_repo.get_quote_draft(quote_id)
            if not quote:
                raise ValueError(f"Quote {quote_id} not found")

            # 2. Trouver ligne
            line = next((l for l in quote.lines if l["line_id"] == line_id), None)
            if not line:
                raise ValueError(f"Line {line_id} not found in quote {quote_id}")

            logger.info(
                f"🔄 Retry search for line {line_id[:8]}... "
                f"(manual_code={manual_code or 'auto'})"
            )

            # 3. Recherche SAP
            if manual_code:
                # Recherche avec code manuel
                self.log_service.log_step(
                    quote.mail_id,
                    "MANUAL_CODE_UPDATE",
                    "PENDING",
                    f"line_id={line_id[:8]}..., manual_code={manual_code}"
                )

                search_result = await self.sap_client.search_item(
                    code=manual_code,
                    description=line["description"],
                    supplier_card_code=quote.client_code
                )
            else:
                # Retry automatique avec seuil baissé
                self.log_service.log_step(
                    quote.mail_id,
                    "RETRY_LINE_SEARCH",
                    "PENDING",
                    f"line_id={line_id[:8]}..."
                )

                search_result = await self.sap_client.search_item(
                    code=line["supplier_code"],
                    description=line["description"],
                    supplier_card_code=quote.client_code
                )

            # 4. Calculer prix si trouvé
            sap_price = None
            if search_result.status == "FOUND" and search_result.item_code:
                sap_price = await self.sap_client.get_item_price(
                    item_code=search_result.item_code,
                    card_code=quote.client_code or "UNKNOWN",
                    quantity=line["quantity"]
                )

                if sap_price:
                    logger.info(
                        f"💰 Prix calculé: {sap_price} EUR pour {search_result.item_code}"
                    )

            # 5. Update ligne dans DB
            search_metadata = {
                "search_type": "MANUAL" if manual_code else "RETRY_FUZZY",
                "sap_query_used": search_result.query_used,
                "search_timestamp": search_result.timestamp,
                "match_score": search_result.matches[0]["score"] if search_result.matches else 0
            }

            self.quote_repo.update_line_sap_data(
                quote_id=quote_id,
                line_id=line_id,
                sap_item_code=search_result.item_code,
                sap_status=search_result.status,
                sap_price=sap_price,
                search_metadata=search_metadata
            )

            # 6. Log succès
            self.log_service.log_step(
                quote.mail_id,
                "MANUAL_CODE_UPDATE" if manual_code else "RETRY_LINE_SEARCH",
                "SUCCESS",
                f"line_id={line_id[:8]}..., sap_status={search_result.status}"
            )

            logger.info(
                f"✅ Ligne {line_id[:8]}... updated: sap_status={search_result.status}, "
                f"price={sap_price}"
            )

            return LineRetryResult(
                success=True,
                sap_item_code=search_result.item_code,
                sap_status=search_result.status,
                sap_price=sap_price,
                updated_at=datetime.utcnow().isoformat() + "Z"
            )

        except ValueError as e:
            # Quote ou ligne non trouvée
            logger.error(f"❌ {str(e)}")
            raise

        except Exception as e:
            # Erreur SAP ou autre
            if quote:
                self.log_service.log_step(
                    quote.mail_id,
                    "RETRY_LINE_ERROR",
                    "ERROR",
                    f"{type(e).__name__}: {str(e)}"
                )

            logger.error(f"❌ Error retrying line {line_id}: {e}")
            import traceback
            traceback.print_exc()
            raise


# Singleton instance
_retry_service: Optional[RetryService] = None


def get_retry_service() -> RetryService:
    """Factory pattern pour obtenir l'instance unique."""
    global _retry_service
    if _retry_service is None:
        _retry_service = RetryService()
        logger.info("RetryService singleton created")
    return _retry_service
