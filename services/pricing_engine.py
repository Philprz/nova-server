"""
Moteur de pricing intelligent RONDOT-SAS
Implémentation des 4 CAS déterministes selon organigramme
"""

import logging
import uuid
import os
from typing import Optional
from datetime import datetime
from services.pricing_models import (
    PricingContext,
    PricingDecision,
    PricingResult,
    PricingCaseType,
    SupplierPriceVariation
)
from services.sap_history_service import get_sap_history_service
from services.supplier_tariffs_db import search_products
import services.pricing_audit_db as pricing_audit_db

logger = logging.getLogger(__name__)


class PricingEngine:
    """
    Moteur de pricing selon organigramme RONDOT-SAS

    LOGIQUE DÉCISIONNELLE :

    1. Recherche historique vente à CE client
       - OUI → Vérifier variation prix fournisseur
         - < 5% → CAS 1 (HC) : Reprendre prix dernière vente
         - ≥ 5% → CAS 2 (HCM) : Recalculer avec marge 45% + Alerte commerciale
       - NON → Continuer

    2. Article déjà vendu à AUTRES clients ?
       - OUI → CAS 3 (HA) : Prix moyen pondéré + Vérifier évolution prix fournisseur
       - NON → Continuer

    3. Nouveau produit (jamais vendu)
       → CAS 4 (NP) : Prix fournisseur + marge 45% + Validation commerciale
    """

    def __init__(self):
        self.history_service = get_sap_history_service()
        self.default_margin = 45.0  # Marge RONDOT-SAS : 45%

    async def calculate_price(self, context: PricingContext) -> PricingResult:
        """
        Point d'entrée principal du moteur de pricing

        Args:
            context: Contexte de calcul (article, client, quantité, prix fournisseur)

        Returns:
            Résultat avec décision de pricing
        """
        start_time = datetime.now()

        try:
            # Récupérer prix fournisseur si non fourni
            if context.supplier_price is None:
                context.supplier_price = await self._get_supplier_price(context.item_code)
                if context.supplier_price is None:
                    return PricingResult(
                        success=False,
                        error=f"Prix fournisseur introuvable pour {context.item_code}"
                    )

            # ÉTAPE 1 : Recherche historique vente à CE client
            last_sale = await self.history_service.get_last_sale_to_client(
                context.item_code,
                context.card_code
            )

            if last_sale:
                # Article déjà vendu à ce client
                decision = await self._handle_existing_client_sale(context, last_sale)
            else:
                # ÉTAPE 2 : Recherche ventes à AUTRES clients
                other_sales = await self.history_service.get_sales_to_other_clients(
                    context.item_code,
                    exclude_card_code=context.card_code
                )

                if other_sales:
                    # CAS 3 : Article vendu à autres clients
                    decision = await self._handle_sales_to_others(context, other_sales)
                else:
                    # CAS 4 : Nouveau produit jamais vendu
                    decision = await self._handle_new_product(context)

            # Calcul temps de traitement
            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            # Sauvegarder la décision dans la base d'audit
            pricing_audit_db.save_pricing_decision(decision)

            # Créer demande de validation si nécessaire
            validation_id = None
            if decision.requires_validation and os.getenv("PRICING_CREATE_VALIDATIONS", "true").lower() == "true":
                validation_id = await self._create_validation_request(decision, context)

            logger.info(
                f"✓ Pricing {decision.case_type} : {context.item_code} → {decision.calculated_price:.2f} EUR "
                f"(temps: {processing_time:.1f}ms)"
                + (f" → Validation créée: {validation_id}" if validation_id else "")
            )

            return PricingResult(
                success=True,
                decision=decision,
                processing_time_ms=round(processing_time, 2)
            )

        except Exception as e:
            logger.error(f"✗ Erreur moteur pricing : {e}")
            return PricingResult(
                success=False,
                error=str(e)
            )

    async def _handle_existing_client_sale(
        self,
        context: PricingContext,
        last_sale
    ) -> PricingDecision:
        """
        Gestion CAS 1 ou CAS 2 : Article déjà vendu à ce client

        Logique :
        - Calculer variation prix fournisseur
        - Si < 5% → CAS 1 (reprendre prix)
        - Si ≥ 5% → CAS 2 (recalculer + alerte)
        """
        # Vérifier variation prix fournisseur
        variation = await self.history_service.get_supplier_price_variation(
            context.item_code,
            context.supplier_price
        )

        is_stable = variation.is_stable if variation else True

        if is_stable and not context.force_recalculate:
            # CAS 1 : Prix stable → Reprendre prix dernière vente
            return PricingDecision(
                decision_id=str(uuid.uuid4()),
                item_code=context.item_code,
                card_code=context.card_code,
                quantity=context.quantity,
                case_type=PricingCaseType.CAS_1_HC,
                case_description="Historique client + Prix fournisseur stable (< 5%)",
                calculated_price=last_sale.unit_price,
                supplier_price=context.supplier_price,
                margin_applied=self._calculate_margin(context.supplier_price, last_sale.unit_price),
                last_sale_date=last_sale.doc_date,
                last_sale_price=last_sale.unit_price,
                last_sale_doc_num=last_sale.doc_num,
                price_variation=variation,
                justification=(
                    f"Reprise prix dernière vente ({last_sale.unit_price:.2f} EUR) "
                    f"du {last_sale.doc_date} (Devis {last_sale.doc_num}). "
                    f"Variation prix fournisseur : {variation.variation_percent:+.2f}% (stable)." if variation
                    else f"Reprise prix dernière vente ({last_sale.unit_price:.2f} EUR) du {last_sale.doc_date}."
                ),
                confidence_score=1.0,
                requires_validation=False
            )
        else:
            # CAS 2 : Prix instable → Recalculer avec marge 45%
            new_price = self._apply_margin(context.supplier_price, context.apply_margin)
            price_diff = new_price - last_sale.unit_price

            return PricingDecision(
                decision_id=str(uuid.uuid4()),
                item_code=context.item_code,
                card_code=context.card_code,
                quantity=context.quantity,
                case_type=PricingCaseType.CAS_2_HCM,
                case_description="Historique client + Prix fournisseur modifié (≥ 5%)",
                calculated_price=new_price,
                supplier_price=context.supplier_price,
                margin_applied=context.apply_margin,
                last_sale_date=last_sale.doc_date,
                last_sale_price=last_sale.unit_price,
                last_sale_doc_num=last_sale.doc_num,
                price_variation=variation,
                justification=(
                    f"Prix recalculé ({new_price:.2f} EUR) avec marge {context.apply_margin}%. "
                    f"Ancien prix vente : {last_sale.unit_price:.2f} EUR. "
                    f"Écart : {price_diff:+.2f} EUR ({(price_diff/last_sale.unit_price*100):+.2f}%). "
                    f"Variation prix fournisseur : {variation.variation_percent:+.2f}% (instable)." if variation
                    else f"Prix recalculé ({new_price:.2f} EUR) avec marge {context.apply_margin}%."
                ),
                confidence_score=0.9,
                requires_validation=True,
                validation_reason=f"Variation prix fournisseur importante ({variation.variation_percent:+.2f}%)" if variation else "Recalcul nécessaire",
                alerts=[
                    f"⚠ ALERTE COMMERCIALE : Variation prix fournisseur {variation.variation_percent:+.2f}%" if variation else "⚠ ALERTE : Recalcul prix",
                    f"Impact prix vente : {price_diff:+.2f} EUR"
                ]
            )

    async def _handle_sales_to_others(
        self,
        context: PricingContext,
        other_sales
    ) -> PricingDecision:
        """
        CAS 3 : Article jamais vendu à CE client, mais vendu à AUTRES

        Logique :
        - Calculer prix moyen pondéré des ventes autres clients
        - Vérifier évolution prix fournisseur depuis dernières ventes
        """
        avg_price = await self.history_service.calculate_weighted_average_price(other_sales)

        if avg_price is None:
            # Fallback sur CAS 4 si calcul impossible
            return await self._handle_new_product(context)

        # Vérifier évolution prix fournisseur
        variation = await self.history_service.get_supplier_price_variation(
            context.item_code,
            context.supplier_price
        )

        # Liste clients référence
        clients_ref = ", ".join(set(s.card_code for s in other_sales[:5]))

        return PricingDecision(
            decision_id=str(uuid.uuid4()),
            item_code=context.item_code,
            card_code=context.card_code,
            quantity=context.quantity,
            case_type=PricingCaseType.CAS_3_HA,
            case_description="Historique autres clients (prix moyen pondéré)",
            calculated_price=avg_price,
            supplier_price=context.supplier_price,
            margin_applied=self._calculate_margin(context.supplier_price, avg_price),
            average_price_others=avg_price,
            reference_sales_count=len(other_sales),
            price_variation=variation,
            justification=(
                f"Prix moyen pondéré : {avg_price:.2f} EUR "
                f"(basé sur {len(other_sales)} ventes à autres clients). "
                f"Clients référence : {clients_ref}. "
                f"Prix fournisseur actuel : {context.supplier_price:.2f} EUR."
            ),
            confidence_score=0.85,
            requires_validation=False,
            alerts=[
                f"Première vente à ce client (basée sur {len(other_sales)} ventes similaires)"
            ] if len(other_sales) < 3 else []
        )

    async def _handle_new_product(self, context: PricingContext) -> PricingDecision:
        """
        CAS 4 : Nouveau produit (jamais vendu)

        Logique :
        - Prix fournisseur + marge 45%
        - Validation commerciale OBLIGATOIRE
        """
        new_price = self._apply_margin(context.supplier_price, context.apply_margin)

        return PricingDecision(
            decision_id=str(uuid.uuid4()),
            item_code=context.item_code,
            card_code=context.card_code,
            quantity=context.quantity,
            case_type=PricingCaseType.CAS_4_NP,
            case_description="Nouveau produit (aucun historique)",
            calculated_price=new_price,
            supplier_price=context.supplier_price,
            margin_applied=context.apply_margin,
            justification=(
                f"Nouveau produit sans historique. "
                f"Prix calculé : {new_price:.2f} EUR "
                f"(prix fournisseur {context.supplier_price:.2f} EUR + marge {context.apply_margin}%). "
                f"VALIDATION COMMERCIALE REQUISE."
            ),
            confidence_score=0.7,
            requires_validation=True,
            validation_reason="Nouveau produit sans historique de vente",
            alerts=[
                "⚠ NOUVEAU PRODUIT : Aucun historique de vente disponible",
                "Validation commerciale OBLIGATOIRE avant création devis"
            ]
        )

    async def _create_validation_request(
        self,
        decision: PricingDecision,
        context: PricingContext
    ) -> Optional[str]:
        """
        Crée une demande de validation commerciale pour une décision pricing
        Retourne l'ID de la validation créée, ou None si erreur
        """
        try:
            # Import lazy pour éviter les dépendances circulaires
            from services.quote_validator import get_quote_validator

            validator = get_quote_validator()
            validation_request = validator.create_validation_request(
                pricing_decision=decision,
                email_id=context.email_id if hasattr(context, 'email_id') else None,
                email_subject=context.email_subject if hasattr(context, 'email_subject') else None
            )

            logger.info(f"✓ Demande de validation créée: {validation_request.validation_id} (priorité: {validation_request.priority.value})")
            return validation_request.validation_id

        except Exception as e:
            logger.error(f"✗ Erreur création demande de validation : {e}")
            return None

    async def _get_supplier_price(self, item_code: str) -> Optional[float]:
        """Récupère le prix fournisseur depuis supplier_tariffs_db"""
        try:
            products = search_products(item_code, limit=1)
            if products:
                price = products[0].get('unit_price')
                if price and price > 0:
                    return price
            return None
        except Exception as e:
            logger.error(f"✗ Erreur récupération prix fournisseur : {e}")
            return None

    def _apply_margin(self, supplier_price: float, margin_percent: float) -> float:
        """Applique la marge sur le prix fournisseur"""
        return round(supplier_price * (1 + margin_percent / 100), 2)

    def _calculate_margin(self, supplier_price: float, sale_price: float) -> float:
        """Calcule la marge réalisée"""
        if supplier_price == 0:
            return 0.0
        return round(((sale_price - supplier_price) / supplier_price) * 100, 2)


# Instance singleton
_pricing_engine: Optional[PricingEngine] = None


def get_pricing_engine() -> PricingEngine:
    """Factory pour obtenir l'instance du moteur"""
    global _pricing_engine
    if _pricing_engine is None:
        _pricing_engine = PricingEngine()
        logger.info("PricingEngine initialisé")
    return _pricing_engine
