"""
Service d'accès aux historiques SAP (factures ventes/achats)
Nécessaire pour implémentation CAS 1/2/3 du pricing
"""

import logging
from typing import List, Optional
from datetime import datetime, date, timedelta
from services.sap_business_service import SAPBusinessService
from services.pricing_models import (
    SalesHistoryEntry,
    WeightedSaleData,
    SupplierPriceVariation
)

logger = logging.getLogger(__name__)


class SAPHistoryService:
    """Service d'interrogation des historiques SAP"""

    def __init__(self, sap_service: SAPBusinessService):
        self.sap_service = sap_service

    async def get_last_sale_to_client(
        self,
        item_code: str,
        card_code: str,
        lookback_days: int = 365
    ) -> Optional[SalesHistoryEntry]:
        """
        Récupère la dernière vente d'un article à un client (CAS 1/2)

        Endpoint SAP : GET /Invoices
        Filtre : CardCode eq '{card_code}' AND DocumentLines/any(line: line/ItemCode eq '{item_code}')

        Args:
            item_code: Code article
            card_code: Code client
            lookback_days: Période de recherche (défaut 365j)

        Returns:
            Dernière vente ou None si jamais vendu
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            # Requête SAP avec filtre OData
            params = {
                "$filter": f"CardCode eq '{card_code}' and DocDate ge '{cutoff_date}'",
                "$expand": "DocumentLines",
                "$orderby": "DocDate desc",
                "$top": 50  # Limite pour performance
            }

            result = await self.sap_service._call_sap("/Invoices", params=params)

            # Parcourir les factures pour trouver l'article
            for invoice in result.get("value", []):
                for line in invoice.get("DocumentLines", []):
                    if line.get("ItemCode") == item_code:
                        # Première occurrence = dernière vente
                        return SalesHistoryEntry(
                            doc_entry=invoice.get("DocEntry"),
                            doc_num=invoice.get("DocNum"),
                            doc_date=datetime.strptime(invoice.get("DocDate"), "%Y-%m-%d").date(),
                            card_code=invoice.get("CardCode"),
                            item_code=line.get("ItemCode"),
                            quantity=line.get("Quantity", 0),
                            unit_price=line.get("UnitPrice", 0),
                            line_total=line.get("LineTotal", 0),
                            discount_percent=line.get("DiscountPercent", 0)
                        )

            logger.info(f"Aucune vente trouvée pour {item_code} au client {card_code}")
            return None

        except Exception as e:
            logger.error(f"✗ Erreur récupération historique vente : {e}")
            return None

    async def get_sales_to_other_clients(
        self,
        item_code: str,
        exclude_card_code: Optional[str] = None,
        lookback_days: int = 365,
        limit: int = 50
    ) -> List[WeightedSaleData]:
        """
        Récupère les ventes d'un article à AUTRES clients (CAS 3)

        Args:
            item_code: Code article
            exclude_card_code: Client à exclure (client actuel)
            lookback_days: Période de recherche
            limit: Nombre max de ventes

        Returns:
            Liste des ventes avec pondération
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            # Filtre : exclure le client actuel
            filter_parts = [f"DocDate ge '{cutoff_date}'"]
            if exclude_card_code:
                filter_parts.append(f"CardCode ne '{exclude_card_code}'")

            params = {
                "$filter": " and ".join(filter_parts),
                "$expand": "DocumentLines",
                "$orderby": "DocDate desc",
                "$top": limit
            }

            result = await self.sap_service._call_sap("/Invoices", params=params)

            sales = []
            for invoice in result.get("value", []):
                for line in invoice.get("DocumentLines", []):
                    if line.get("ItemCode") == item_code:
                        sales.append(WeightedSaleData(
                            card_code=invoice.get("CardCode"),
                            card_name=invoice.get("CardName"),
                            unit_price=line.get("UnitPrice", 0),
                            quantity=line.get("Quantity", 0),
                            sale_date=datetime.strptime(invoice.get("DocDate"), "%Y-%m-%d").date()
                        ))

            logger.info(f"✓ Trouvé {len(sales)} ventes de {item_code} à autres clients")
            return sales

        except Exception as e:
            logger.error(f"✗ Erreur récupération ventes autres clients : {e}")
            return []

    async def calculate_weighted_average_price(
        self,
        sales: List[WeightedSaleData]
    ) -> Optional[float]:
        """
        Calcule le prix moyen pondéré des ventes (CAS 3)

        Pondération basée sur :
        - Récence de la vente (plus récent = plus de poids)
        - Quantité vendue

        Args:
            sales: Liste des ventes

        Returns:
            Prix moyen pondéré ou None
        """
        if not sales:
            return None

        total_weighted_price = 0.0
        total_weight = 0.0

        for sale in sales:
            weighted_price = sale.unit_price * sale.weight
            total_weighted_price += weighted_price
            total_weight += sale.weight

        if total_weight == 0:
            return None

        avg_price = total_weighted_price / total_weight
        logger.info(f"✓ Prix moyen pondéré calculé : {avg_price:.2f} EUR ({len(sales)} ventes)")
        return round(avg_price, 2)

    async def get_supplier_price_variation(
        self,
        item_code: str,
        current_supplier_price: float,
        lookback_days: int = 180
    ) -> Optional[SupplierPriceVariation]:
        """
        Détecte la variation du prix fournisseur (CAS 1 vs CAS 2)

        Endpoint : GET /PurchaseInvoices
        Seuil stabilité : 5%

        Args:
            item_code: Code article
            current_supplier_price: Prix fournisseur actuel
            lookback_days: Période de recherche

        Returns:
            Variation ou None
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            params = {
                "$filter": f"DocDate ge '{cutoff_date}'",
                "$expand": "DocumentLines",
                "$orderby": "DocDate desc",
                "$top": 20
            }

            result = await self.sap_service._call_sap("/PurchaseInvoices", params=params)

            # Trouver le dernier achat de cet article
            previous_price = None
            last_date = None

            for invoice in result.get("value", []):
                for line in invoice.get("DocumentLines", []):
                    if line.get("ItemCode") == item_code:
                        previous_price = line.get("UnitPrice", 0)
                        last_date = datetime.strptime(invoice.get("DocDate"), "%Y-%m-%d").date()
                        break
                if previous_price:
                    break

            if previous_price is None:
                logger.info(f"Aucun historique achat pour {item_code}")
                return None

            variation = SupplierPriceVariation(
                previous_price=previous_price,
                current_price=current_supplier_price,
                last_price_date=last_date
            )

            logger.info(
                f"✓ Variation prix fournisseur {item_code} : "
                f"{previous_price:.2f} → {current_supplier_price:.2f} "
                f"({variation.variation_percent:+.2f}%) - "
                f"Stable : {variation.is_stable}"
            )

            return variation

        except Exception as e:
            logger.error(f"✗ Erreur calcul variation prix fournisseur : {e}")
            return None


# Instance singleton
_sap_history_service: Optional[SAPHistoryService] = None


def get_sap_history_service() -> SAPHistoryService:
    """Factory pour obtenir l'instance du service"""
    global _sap_history_service
    if _sap_history_service is None:
        from services.sap_business_service import get_sap_business_service
        _sap_history_service = SAPHistoryService(get_sap_business_service())
        logger.info("SAPHistoryService initialisé")
    return _sap_history_service
