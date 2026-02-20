"""
Moteur de pricing intelligent RONDOT-SAS
Implémentation des 4 CAS déterministes selon organigramme
"""

import logging
import uuid
import os
from typing import Optional, Dict, Any, List
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
from services.sap_sql_service import get_sap_sql_service

logger = logging.getLogger(__name__)

# Cache en mémoire pour éviter recalculs (TTL 5 minutes)
from typing import Tuple
_pricing_cache: Dict[str, Tuple[datetime, PricingDecision]] = {}
_cache_ttl_seconds = 300  # 5 minutes
_max_cache_entries = 100  # Limite taille cache


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
        self.sql_service = get_sap_sql_service()
        self.default_margin = 45.0  # Marge RONDOT-SAS : 45%
        self.use_sap_pricing_function = os.getenv("USE_SAP_PRICING_FUNCTION", "true").lower() == "true"

    async def calculate_price(self, context: PricingContext) -> PricingResult:
        """
        Point d'entrée principal du moteur de pricing

        Args:
            context: Contexte de calcul (article, client, quantité, prix fournisseur)

        Returns:
            Résultat avec décision de pricing
        """
        start_time = datetime.now()

        # Vérifier cache (clé unique basée sur contexte)
        cache_key = f"{context.item_code}:{context.card_code}:{context.quantity}:{context.apply_margin}"

        if not context.force_recalculate and cache_key in _pricing_cache:
            cached_time, cached_decision = _pricing_cache[cache_key]

            if (datetime.now() - cached_time).total_seconds() < _cache_ttl_seconds:
                logger.debug(f"Cache hit for {cache_key}")
                return PricingResult(
                    success=True,
                    decision=cached_decision,
                    processing_time_ms=0
                )

        try:
            # Récupérer prix fournisseur si non fourni
            if context.supplier_price is None:
                context.supplier_price = await self._get_supplier_price(context.item_code)
                if context.supplier_price is None:
                    return PricingResult(
                        success=False,
                        error=f"Prix fournisseur introuvable pour {context.item_code}"
                    )

            # ÉTAPE 0 : Tenter d'utiliser la fonction SAP fn_ITS_GetPriceAnalysis (prioritaire)
            if self.use_sap_pricing_function:
                sap_price_analysis = self.sql_service.get_price_analysis(
                    context.item_code,
                    context.card_code
                )
                if sap_price_analysis:
                    # ✨ Récupérer les 3 dernières ventes pour transparence
                    historical_sales = await self.history_service.get_last_n_sales_to_client(
                        context.item_code,
                        context.card_code,
                        limit=3
                    )

                    # La fonction SAP a retourné un prix recommandé
                    decision = self._create_decision_from_sap_function(context, sap_price_analysis, historical_sales)
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000

                    # Sauvegarder la décision dans la base d'audit
                    pricing_audit_db.save_pricing_decision(decision)

                    # Créer demande de validation si nécessaire
                    validation_id = None
                    if decision.requires_validation and os.getenv("PRICING_CREATE_VALIDATIONS", "true").lower() == "true":
                        validation_id = await self._create_validation_request(decision, context)

                    logger.info(
                        f"✓ Pricing SAP FUNCTION : {context.item_code} → {decision.calculated_price:.2f} EUR "
                        f"(temps: {processing_time:.1f}ms)"
                        + (f" → Validation créée: {validation_id}" if validation_id else "")
                    )

                    return PricingResult(
                        success=True,
                        decision=decision,
                        processing_time_ms=round(processing_time, 2)
                    )
                else:
                    logger.debug(f"ℹ️ Fonction SAP pricing non disponible pour {context.item_code}/{context.card_code} - Fallback sur logique classique")

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

            # Stocker dans le cache
            _pricing_cache[cache_key] = (datetime.now(), decision)

            # Cleanup cache si trop d'entrées (FIFO)
            if len(_pricing_cache) > _max_cache_entries:
                oldest_key = min(_pricing_cache.keys(), key=lambda k: _pricing_cache[k][0])
                del _pricing_cache[oldest_key]
                logger.debug(f"Cache cleanup: removed oldest entry")

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
        # ✨ NOUVEAU : Récupérer les 3 dernières ventes pour transparence
        historical_sales = await self.history_service.get_last_n_sales_to_client(
            context.item_code,
            context.card_code,
            limit=3
        )

        # Vérifier variation prix fournisseur
        variation = await self.history_service.get_supplier_price_variation(
            context.item_code,
            context.supplier_price
        )

        is_stable = variation.is_stable if variation else True

        if is_stable and not context.force_recalculate:
            # CAS 1 : Prix stable → Reprendre prix dernière vente
            historical_margin = self._calculate_margin(context.supplier_price, last_sale.unit_price)
            min_margin = float(os.getenv("PRICING_MIN_MARGIN", "35.0"))
            max_margin = float(os.getenv("PRICING_MAX_MARGIN", "45.0"))

            # Vérifier si la marge historique respecte le min/max configuré
            margin_alerts = []
            final_price = last_sale.unit_price
            final_margin = historical_margin

            if context.supplier_price and context.supplier_price > 0:
                if historical_margin < min_margin:
                    # Marge insuffisante : recalculer au minimum
                    final_price = self._apply_margin(context.supplier_price, min_margin)
                    final_margin = min_margin
                    margin_alerts.append(
                        f"⚠ Marge historique {historical_margin:.1f}% < minimum {min_margin:.0f}% "
                        f"→ Prix ajusté à {final_price:.2f} EUR"
                    )
                elif historical_margin > max_margin:
                    margin_alerts.append(
                        f"ℹ Marge historique {historical_margin:.1f}% > maximum {max_margin:.0f}% "
                        f"(prix conservé)"
                    )

            return PricingDecision(
                decision_id=str(uuid.uuid4()),
                item_code=context.item_code,
                card_code=context.card_code,
                quantity=context.quantity,
                case_type=PricingCaseType.CAS_1_HC,
                case_description="Historique client + Prix fournisseur stable (< 5%)",
                calculated_price=final_price,
                supplier_price=context.supplier_price,
                margin_applied=final_margin,
                last_sale_date=last_sale.doc_date,
                last_sale_price=last_sale.unit_price,
                last_sale_doc_num=last_sale.doc_num,
                historical_sales=historical_sales,
                price_variation=variation,
                justification=(
                    f"Reprise prix dernière vente ({last_sale.unit_price:.2f} EUR, marge {historical_margin:.1f}%) "
                    f"du {last_sale.doc_date} (Devis {last_sale.doc_num}). "
                    f"Variation prix fournisseur : {variation.variation_percent:+.2f}% (stable)." if variation
                    else f"Reprise prix dernière vente ({last_sale.unit_price:.2f} EUR, marge {historical_margin:.1f}%) "
                    f"du {last_sale.doc_date}."
                ) + (f" {margin_alerts[0]}" if margin_alerts else ""),
                confidence_score=1.0,
                requires_validation=len(margin_alerts) > 0,
                validation_reason=margin_alerts[0] if margin_alerts else None,
                alerts=margin_alerts
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
                historical_sales=historical_sales,  # ✨ NOUVEAU : 3 dernières ventes
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

    def _create_decision_from_sap_function(
        self,
        context: PricingContext,
        sap_analysis: Dict[str, Any],
        historical_sales: List = None
    ) -> PricingDecision:
        """
        Crée une décision de pricing basée sur le résultat de fn_ITS_GetPriceAnalysis

        Args:
            context: Contexte de pricing
            sap_analysis: Résultat de la fonction SAP (dictionnaire de colonnes)

        Returns:
            PricingDecision avec le prix recommandé par SAP
        """
        # Extraire les champs du résultat SAP (les noms de colonnes peuvent varier)
        # Adapter selon la structure réelle retournée par fn_ITS_GetPriceAnalysis
        recommended_price = (
            sap_analysis.get('RecommendedPrice') or
            sap_analysis.get('UnitPrice') or
            sap_analysis.get('Price') or
            sap_analysis.get('SuggestedPrice')
        )

        # Déterminer le type de CAS basé sur les informations SAP
        case_type = PricingCaseType.SAP_FUNCTION  # Nouveau type à ajouter aux modèles
        last_sale_price = sap_analysis.get('LastSalePrice')
        avg_price = sap_analysis.get('AveragePrice')

        # Construire la justification
        justification_parts = [
            f"Prix calculé par fonction SAP fn_ITS_GetPriceAnalysis",
            f"Article: {context.item_code}",
            f"Client: {context.card_code}",
        ]

        if last_sale_price:
            justification_parts.append(f"Dernière vente: {last_sale_price:.2f} EUR")

        if avg_price:
            justification_parts.append(f"Prix moyen: {avg_price:.2f} EUR")

        # Ajouter tous les autres champs retournés pour traçabilité
        sap_details = []
        for key, value in sap_analysis.items():
            if key not in ['RecommendedPrice', 'LastSalePrice', 'AveragePrice', 'ItemCode', 'CardCode']:
                sap_details.append(f"{key}: {value}")

        if sap_details:
            justification_parts.append("Détails SAP: " + ", ".join(sap_details))

        # Déterminer si validation requise
        # Par exemple, si le prix diffère significativement du dernier prix
        requires_validation = False
        validation_reason = None

        if last_sale_price and recommended_price:
            price_diff_pct = abs((recommended_price - last_sale_price) / last_sale_price * 100)
            if price_diff_pct > 10:
                requires_validation = True
                validation_reason = f"Variation {price_diff_pct:.1f}% par rapport au dernier prix"

        # Calculer la marge si le prix fournisseur est disponible
        margin_pct = None
        if context.supplier_price and recommended_price:
            margin_pct = self._calculate_margin(context.supplier_price, recommended_price)

        return PricingDecision(
            decision_id=str(uuid.uuid4()),
            item_code=context.item_code,
            card_code=context.card_code,
            quantity=context.quantity,
            case_type=case_type,
            case_description="Prix calculé par fonction SAP fn_ITS_GetPriceAnalysis",
            calculated_price=recommended_price,
            justification="\n".join(justification_parts),
            requires_validation=requires_validation,
            validation_reason=validation_reason,
            confidence_score=1.0,  # Confiance maximale car vient de SAP
            supplier_price=context.supplier_price,
            margin_applied=margin_pct,
            sap_price_analysis=sap_analysis,  # ✨ NOUVEAU : Résultat brut SAP
            historical_sales=historical_sales or [],  # ✨ NOUVEAU : 3 dernières ventes
            last_sale_price=last_sale_price,
            average_price_others=avg_price,
            alerts=[]
        )

    async def _get_supplier_price(self, item_code: str) -> Optional[float]:
        """
        Récupère le prix fournisseur depuis supplier_tariffs_db.

        Stratégie :
        1. Chercher directement par item_code SAP
        2. Si rien, chercher les références fournisseurs connues via product_mapping_db
        3. Si rien, utiliser le prix SAP (AvgStdPrice) comme fallback
        """
        try:
            # 1. Cherche directement par item_code SAP
            products = search_products(item_code, limit=1)
            if products:
                price = products[0].get('unit_price')
                if price and price > 0:
                    logger.debug(f"Prix fournisseur direct pour {item_code}: {price}")
                    return price

            # 2. Chercher via le mapping de références (external_code → SAP)
            # Le mapping_db connaît les refs fournisseurs associées au code SAP
            try:
                from services.product_mapping_db import get_product_mapping_db
                mapping_db = get_product_mapping_db()

                import sqlite3
                conn = sqlite3.connect(mapping_db.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Chercher toutes les refs externes qui mappent vers ce code SAP
                cursor.execute("""
                    SELECT external_code FROM product_code_mapping
                    WHERE matched_item_code = ? AND status = 'VALIDATED'
                    LIMIT 5
                """, (item_code,))
                ext_codes = [r[0] for r in cursor.fetchall()]
                conn.close()

                for ext_code in ext_codes:
                    products = search_products(ext_code, limit=1)
                    if products:
                        price = products[0].get('unit_price')
                        if price and price > 0:
                            logger.debug(f"Prix fournisseur via mapping {ext_code}→{item_code}: {price}")
                            return price
            except Exception as map_err:
                logger.debug(f"Mapping lookup failed: {map_err}")

            # 3. Fallback : chercher par mots-clés du nom SAP dans les tarifs
            try:
                from services.sap_cache_db import get_sap_cache_db
                sap_cache = get_sap_cache_db()

                import sqlite3
                conn = sqlite3.connect(sap_cache.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT ItemName, Price FROM sap_items WHERE ItemCode = ?", (item_code,))
                row = cursor.fetchone()
                conn.close()

                if row and row['ItemName']:
                    # Extraire ref numérique du nom SAP (ex: "2323060165 BRACKET SHORT" → "2323060165")
                    import re
                    nums = re.findall(r'\b\d{7,}\b', row['ItemName'])
                    for num in nums:
                        products = search_products(num, limit=1)
                        if products:
                            price = products[0].get('unit_price')
                            if price and price > 0:
                                logger.debug(f"Prix fournisseur via nom SAP {num}→{item_code}: {price}")
                                return price

                    # Fallback ultime : prix SAP (AvgStdPrice)
                    if row['Price'] and row['Price'] > 0:
                        sap_price = row['Price']
                        # Estimer prix fournisseur à partir du prix de vente SAP (marge 40%)
                        estimated_cost = round(sap_price / 1.40, 2)
                        logger.info(f"Fallback prix fournisseur estimé pour {item_code}: {estimated_cost} EUR (basé sur AvgStdPrice {sap_price})")
                        return estimated_cost
            except Exception as sap_err:
                logger.debug(f"SAP cache lookup failed: {sap_err}")

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
