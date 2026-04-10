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

    async def _get_invoice_headers(self, filter_str: str, top: int = 50) -> List[dict]:
        """
        Récupère les headers de factures sans $expand (compatible toutes versions SAP B1).
        Le $expand=DocumentLines sur collection n'est pas supporté par certaines versions.
        """
        params = {
            "$filter": filter_str,
            "$orderby": "DocDate desc",
            "$top": top,
            "$select": "DocEntry,DocNum,DocDate,CardCode,CardName"
        }
        result = await self.sap_service._call_sap("/Invoices", params=params)
        return result.get("value", [])

    async def _get_invoice_lines(self, doc_entry: int) -> List[dict]:
        """
        Récupère les lignes d'une facture individuelle.
        GET /Invoices({DocEntry}) sans paramètre retourne déjà DocumentLines dans le body SAP B1.
        """
        try:
            detail = await self.sap_service._call_sap(f"/Invoices({doc_entry})")
            return detail.get("DocumentLines", [])
        except Exception as e:
            logger.warning(f"Impossible de récupérer les lignes facture {doc_entry} : {e}")
            return []

    async def _get_purchase_invoice_headers(self, filter_str: str, top: int = 20) -> List[dict]:
        """Récupère les headers de factures achat sans $expand."""
        params = {
            "$filter": filter_str,
            "$orderby": "DocDate desc",
            "$top": top,
            "$select": "DocEntry,DocNum,DocDate,CardCode"
        }
        result = await self.sap_service._call_sap("/PurchaseInvoices", params=params)
        return result.get("value", [])

    async def _get_purchase_invoice_lines(self, doc_entry: int) -> List[dict]:
        """
        Récupère les lignes d'une facture achat individuelle.
        GET /PurchaseInvoices({DocEntry}) sans paramètre retourne déjà DocumentLines dans le body SAP B1.
        """
        try:
            detail = await self.sap_service._call_sap(f"/PurchaseInvoices({doc_entry})")
            return detail.get("DocumentLines", [])
        except Exception as e:
            logger.warning(f"Impossible de récupérer les lignes facture achat {doc_entry} : {e}")
            return []

    async def get_last_sale_to_client(
        self,
        item_code: str,
        card_code: str,
        lookback_days: int = 365
    ) -> Optional[SalesHistoryEntry]:
        """
        Récupère la dernière vente d'un article à un client (CAS 1/2).
        Approche 2 étapes : headers d'abord, puis lignes par facture.
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            filter_str = f"CardCode eq '{card_code}' and DocDate ge '{cutoff_date}'"

            headers = await self._get_invoice_headers(filter_str, top=50)

            for header in headers:
                doc_entry = header.get("DocEntry")
                lines = await self._get_invoice_lines(doc_entry)
                for line in lines:
                    if line.get("ItemCode") == item_code:
                        return SalesHistoryEntry(
                            doc_entry=header.get("DocEntry"),
                            doc_num=header.get("DocNum"),
                            doc_date=datetime.strptime(header.get("DocDate"), "%Y-%m-%d").date(),
                            card_code=header.get("CardCode"),
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

    async def get_last_n_sales_to_client(
        self,
        item_code: str,
        card_code: str,
        limit: int = 3,
        lookback_days: int = 365
    ) -> List[SalesHistoryEntry]:
        """
        Récupère les N dernières ventes d'un article à un client.
        Approche 2 étapes : headers d'abord, puis lignes par facture.
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            filter_str = f"CardCode eq '{card_code}' and DocDate ge '{cutoff_date}'"

            headers = await self._get_invoice_headers(filter_str, top=50)

            sales = []
            for header in headers:
                if len(sales) >= limit:
                    break
                doc_entry = header.get("DocEntry")
                lines = await self._get_invoice_lines(doc_entry)
                for line in lines:
                    if line.get("ItemCode") == item_code:
                        sales.append(SalesHistoryEntry(
                            doc_entry=header.get("DocEntry"),
                            doc_num=header.get("DocNum"),
                            doc_date=datetime.strptime(header.get("DocDate"), "%Y-%m-%d").date(),
                            card_code=header.get("CardCode"),
                            item_code=line.get("ItemCode"),
                            quantity=line.get("Quantity", 0),
                            unit_price=line.get("UnitPrice", 0),
                            line_total=line.get("LineTotal", 0),
                            discount_percent=line.get("DiscountPercent", 0)
                        ))
                        break  # Une ligne par facture

            logger.info(f"✓ {len(sales)} vente(s) trouvée(s) pour {item_code} au client {card_code}")
            return sales

        except Exception as e:
            logger.error(f"✗ Erreur récupération historique ventes : {e}")
            return []

    async def get_sales_to_other_clients(
        self,
        item_code: str,
        exclude_card_code: Optional[str] = None,
        lookback_days: int = 365,
        limit: int = 50
    ) -> List[WeightedSaleData]:
        """
        Récupère les ventes d'un article à AUTRES clients (CAS 3).
        Approche 2 étapes : headers d'abord, puis lignes par facture.
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            filter_parts = [f"DocDate ge '{cutoff_date}'"]
            if exclude_card_code:
                filter_parts.append(f"CardCode ne '{exclude_card_code}'")
            filter_str = " and ".join(filter_parts)

            # Limiter à 30 headers max pour éviter trop d'appels individuels
            headers = await self._get_invoice_headers(filter_str, top=min(limit, 30))

            sales = []
            for header in headers:
                doc_entry = header.get("DocEntry")
                lines = await self._get_invoice_lines(doc_entry)
                for line in lines:
                    if line.get("ItemCode") == item_code:
                        sales.append(WeightedSaleData(
                            card_code=header.get("CardCode"),
                            card_name=header.get("CardName", ""),
                            unit_price=line.get("UnitPrice", 0),
                            quantity=line.get("Quantity", 0),
                            sale_date=datetime.strptime(header.get("DocDate"), "%Y-%m-%d").date()
                        ))
                        break  # Une ligne par facture

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
        Détecte la variation du prix fournisseur (CAS 1 vs CAS 2).
        Approche 2 étapes : headers achat, puis lignes par facture.
        """
        try:
            cutoff_date = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            filter_str = f"DocDate ge '{cutoff_date}'"

            headers = await self._get_purchase_invoice_headers(filter_str, top=20)

            # Trouver le dernier achat de cet article
            previous_price = None
            last_date = None

            for header in headers:
                doc_entry = header.get("DocEntry")
                lines = await self._get_purchase_invoice_lines(doc_entry)
                for line in lines:
                    if line.get("ItemCode") == item_code:
                        previous_price = line.get("UnitPrice", 0)
                        last_date = datetime.strptime(header.get("DocDate"), "%Y-%m-%d").date()
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
