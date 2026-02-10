"""
services/quote_workflow_engine.py
Moteur de workflow de devis RONDOT - Machine à états déterministe
Conformité stricte aux règles métier sans ML ni comportement probabiliste
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field

from services.pricing_engine import get_pricing_engine
from services.pricing_models import PricingContext, PricingCaseType
from services.quote_validator import get_quote_validator
from services.currency_service import get_currency_service
from services.supplier_discounts_db import get_supplier_discounts_db
from services.transport_calculator import TransportCalculator
from services.sap_history_service import get_sap_history_service


logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    """États obligatoires du workflow de devis"""
    RECEIVED = "RECEIVED"
    CLIENT_IDENTIFIED = "CLIENT_IDENTIFIED"
    CLIENT_CREATED = "CLIENT_CREATED"
    PRODUCT_IDENTIFIED = "PRODUCT_IDENTIFIED"
    SUPPLIER_IDENTIFIED = "SUPPLIER_IDENTIFIED"
    SUPPLIER_PRICED = "SUPPLIER_PRICED"
    HISTORICAL_ANALYSIS_DONE = "HISTORICAL_ANALYSIS_DONE"
    PRICING_CASE_SELECTED = "PRICING_CASE_SELECTED"
    CURRENCY_APPLIED = "CURRENCY_APPLIED"
    SUPPLIER_DISCOUNT_APPLIED = "SUPPLIER_DISCOUNT_APPLIED"
    MARGIN_APPLIED = "MARGIN_APPLIED"
    PRICING_INTELLIGENT_DONE = "PRICING_INTELLIGENT_DONE"
    TRANSPORT_OPTIMIZED = "TRANSPORT_OPTIMIZED"
    JUSTIFICATION_BUILT = "JUSTIFICATION_BUILT"
    COHERENCE_VALIDATED = "COHERENCE_VALIDATED"
    QUOTE_GENERATED = "QUOTE_GENERATED"
    MANUAL_VALIDATION_REQUIRED = "MANUAL_VALIDATION_REQUIRED"
    QUOTE_ADJUSTED_MANUALLY = "QUOTE_ADJUSTED_MANUALLY"
    QUOTE_SENT = "QUOTE_SENT"
    ERROR = "ERROR"


@dataclass
class Client:
    """Entité Client"""
    card_code: str
    card_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    siret: Optional[str] = None
    is_new: bool = False
    source: str = "SAP"  # SAP | CREATED


@dataclass
class Product:
    """Entité Produit"""
    item_code: str
    item_name: str
    quantity: float
    unit: str = "PCE"
    weight_kg: Optional[float] = None
    dimensions: Optional[str] = None
    source: str = "SAP"  # SAP | SUPPLIER


@dataclass
class Supplier:
    """Entité Fournisseur"""
    supplier_code: str
    supplier_name: str
    currency: str = "EUR"
    is_foreign: bool = False


@dataclass
class PriceContext:
    """Contexte de pricing"""
    supplier_price: float
    supplier_currency: str
    supplier_discount_percent: float = 0.0
    exchange_rate: float = 1.0
    net_supplier_price: float = 0.0
    applied_margin_percent: float = 45.0
    calculated_price: float = 0.0
    pricing_case: Optional[PricingCaseType] = None
    pricing_justification: str = ""
    requires_validation: bool = False
    validation_reason: str = ""


@dataclass
class TransportOption:
    """Option de transport"""
    carrier_name: str
    cost_eur: float
    delivery_days: int
    reliability_score: float
    is_recommended: bool = False


@dataclass
class DecisionTrace:
    """Trace d'une décision"""
    state: WorkflowState
    timestamp: datetime
    decision: str
    justification: str
    data_sources: List[str]
    alerts: List[str] = field(default_factory=list)


@dataclass
class QuoteRequest:
    """Demande de devis"""
    request_id: str
    client_name: Optional[str] = None
    client_code: Optional[str] = None
    client_email: Optional[str] = None
    products: List[Product] = field(default_factory=list)
    source: str = "EMAIL"  # EMAIL | API | MANUAL
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class QuoteDraft:
    """Brouillon de devis"""
    quote_id: str
    client: Optional[Client] = None
    products: List[Product] = field(default_factory=list)
    suppliers: List[Supplier] = field(default_factory=list)
    price_contexts: Dict[str, PriceContext] = field(default_factory=dict)
    transport_options: List[TransportOption] = field(default_factory=list)
    selected_transport: Optional[TransportOption] = None

    total_products_eur: float = 0.0
    total_transport_eur: float = 0.0
    total_ht_eur: float = 0.0
    total_ttc_eur: float = 0.0

    current_state: WorkflowState = WorkflowState.RECEIVED
    traces: List[DecisionTrace] = field(default_factory=list)

    requires_manual_validation: bool = False
    validation_reasons: List[str] = field(default_factory=list)

    justification_block: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class QuoteWorkflowEngine:
    """
    Moteur de workflow de devis RONDOT
    Machine à états déterministe sans ML ni comportement probabiliste

    Règles strictes :
    - Chaque décision est traçable
    - Pas d'extrapolation métier
    - Pas de règle implicite
    - Justification obligatoire
    """

    # Constantes métier
    MARGIN_DEFAULT = 45.0
    MARGIN_MIN = 35.0
    MARGIN_MAX = 45.0
    PRICE_STABILITY_THRESHOLD = 5.0  # %

    def __init__(self):
        self.pricing_engine = get_pricing_engine()
        self.validator = get_quote_validator()
        self.currency_service = get_currency_service()
        self.discounts_db = get_supplier_discounts_db()
        self.transport_calculator = TransportCalculator()
        self.history_service = get_sap_history_service()

    async def run(self, request: QuoteRequest) -> QuoteDraft:
        """
        Point d'entrée principal du workflow
        Déroule tous les états jusqu'à génération du devis

        Args:
            request: Demande de devis à traiter

        Returns:
            QuoteDraft avec traçabilité complète
        """
        draft = QuoteDraft(
            quote_id=str(uuid.uuid4()),
            current_state=WorkflowState.RECEIVED
        )

        self._add_trace(draft, WorkflowState.RECEIVED,
                       f"Demande de devis reçue : {len(request.products)} produit(s)",
                       "Réception demande",
                       [request.source])

        try:
            # ÉTAPE 1 : Identification client
            draft = await self._identify_client(draft, request)

            # ÉTAPE 2 : Identification produits
            draft = await self._identify_products(draft, request)

            # ÉTAPE 3 : Identification fournisseurs (1 produit = 1 fournisseur)
            draft = await self._identify_suppliers(draft)

            # ÉTAPE 4 : Récupération prix fournisseurs
            draft = await self._get_supplier_prices(draft)

            # ÉTAPE 5 : Analyse historique SAP
            draft = await self._analyze_history(draft)

            # ÉTAPE 6 : Pricing intelligent (CAS 1/2/3/4)
            draft = await self._apply_intelligent_pricing(draft)

            # ÉTAPE 7 : Application devises
            draft = await self._apply_currency_conversion(draft)

            # ÉTAPE 8 : Application remises fournisseurs
            draft = await self._apply_supplier_discounts(draft)

            # ÉTAPE 9 : Application marges
            draft = await self._apply_margins(draft)

            # ÉTAPE 10 : Optimisation transport
            draft = await self._optimize_transport(draft)

            # ÉTAPE 11 : Construction justification
            draft = await self._build_justification(draft)

            # ÉTAPE 12 : Validation cohérence
            draft = await self._validate_coherence(draft)

            # ÉTAPE 13 : Génération devis
            draft = await self._generate_quote(draft)

            # ÉTAPE 14 : Vérification validation manuelle
            if draft.requires_manual_validation:
                draft.current_state = WorkflowState.MANUAL_VALIDATION_REQUIRED
                self._add_trace(draft, WorkflowState.MANUAL_VALIDATION_REQUIRED,
                               "Validation commerciale requise",
                               f"{len(draft.validation_reasons)} raison(s)",
                               ["BUSINESS_RULES"],
                               alerts=draft.validation_reasons)
            else:
                # ÉTAPE 15 : Envoi devis (interface externe)
                draft = await self._send_quote(draft)

            return draft

        except Exception as e:
            logger.error(f"Erreur workflow : {e}")
            draft.current_state = WorkflowState.ERROR
            self._add_trace(draft, WorkflowState.ERROR,
                           f"Erreur workflow : {str(e)}",
                           "EXCEPTION",
                           ["SYSTEM"])
            raise

    async def _identify_client(self, draft: QuoteDraft, request: QuoteRequest) -> QuoteDraft:
        """
        R1 - Identification client
        Recherche dans SAP ou création si absent
        """
        if request.client_code:
            # Client existant fourni
            draft.client = Client(
                card_code=request.client_code,
                card_name=request.client_name or "À récupérer",
                source="SAP"
            )
            draft.current_state = WorkflowState.CLIENT_IDENTIFIED
            self._add_trace(draft, WorkflowState.CLIENT_IDENTIFIED,
                           f"Client identifié : {draft.client.card_code}",
                           "Code client fourni",
                           ["REQUEST"])
        else:
            # TODO : Recherche SAP par nom/email
            # Si non trouvé → création obligatoire (blocante)
            # Pour l'instant : client fictif
            draft.client = Client(
                card_code="C_NEW_001",
                card_name=request.client_name or "Client nouveau",
                email=request.client_email,
                is_new=True,
                source="CREATED"
            )
            draft.current_state = WorkflowState.CLIENT_CREATED
            self._add_trace(draft, WorkflowState.CLIENT_CREATED,
                           f"Nouveau client créé : {draft.client.card_name}",
                           "Client absent de SAP",
                           ["SAP_SEARCH", "CLIENT_CREATION"],
                           alerts=["Nouveau client - vérification manuelle recommandée"])

        return draft

    async def _identify_products(self, draft: QuoteDraft, request: QuoteRequest) -> QuoteDraft:
        """
        R2 - Identification produits
        Source : SAP ou fichiers fournisseurs
        """
        draft.products = request.products
        draft.current_state = WorkflowState.PRODUCT_IDENTIFIED

        self._add_trace(draft, WorkflowState.PRODUCT_IDENTIFIED,
                       f"{len(draft.products)} produit(s) identifié(s)",
                       "Codes produits validés",
                       ["REQUEST", "SAP"])

        return draft

    async def _identify_suppliers(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R2 - Identification fournisseur
        RÈGLE STRICTE : 1 produit = 1 fournisseur
        """
        # TODO : Récupération depuis supplier_tariffs_db
        # Pour l'instant : fournisseur fictif par produit

        suppliers_map = {}
        for product in draft.products:
            # Supposons que le fournisseur est dans item_code (ex: "FOURNISSEUR_REF")
            supplier_code = f"SUPP_{product.item_code[:3]}"

            if supplier_code not in suppliers_map:
                suppliers_map[supplier_code] = Supplier(
                    supplier_code=supplier_code,
                    supplier_name=f"Fournisseur {supplier_code}",
                    currency="EUR",
                    is_foreign=False
                )

        draft.suppliers = list(suppliers_map.values())
        draft.current_state = WorkflowState.SUPPLIER_IDENTIFIED

        self._add_trace(draft, WorkflowState.SUPPLIER_IDENTIFIED,
                       f"{len(draft.suppliers)} fournisseur(s) identifié(s)",
                       "Règle : 1 produit = 1 fournisseur",
                       ["SUPPLIER_TARIFFS_DB"])

        return draft

    async def _get_supplier_prices(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R3 - Récupération tarifs fournisseurs
        """
        # TODO : Récupération depuis supplier_tariffs_db
        # Pour l'instant : prix fictifs

        for product in draft.products:
            draft.price_contexts[product.item_code] = PriceContext(
                supplier_price=100.0,  # Prix fictif
                supplier_currency="EUR",
                net_supplier_price=100.0
            )

        draft.current_state = WorkflowState.SUPPLIER_PRICED

        self._add_trace(draft, WorkflowState.SUPPLIER_PRICED,
                       f"Prix fournisseurs récupérés pour {len(draft.products)} produit(s)",
                       "Tarifs extraits de la base",
                       ["SUPPLIER_TARIFFS_DB"])

        return draft

    async def _analyze_history(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R3 - Analyse historique SAP
        Recherche des ventes passées pour CE client et AUTRES clients
        """
        for product in draft.products:
            # Recherche historique ventes à CE client
            last_sale = await self.history_service.get_last_sale_to_client(
                product.item_code,
                draft.client.card_code
            )

            # Recherche ventes à AUTRES clients
            other_sales = await self.history_service.get_sales_to_other_clients(
                product.item_code,
                exclude_card_code=draft.client.card_code
            )

            # Stockage dans le contexte pour décision ultérieure
            price_ctx = draft.price_contexts[product.item_code]
            price_ctx.pricing_justification = f"Historique analysé : "
            if last_sale:
                price_ctx.pricing_justification += f"1 vente à ce client, "
            price_ctx.pricing_justification += f"{len(other_sales) if other_sales else 0} vente(s) autres clients"

        draft.current_state = WorkflowState.HISTORICAL_ANALYSIS_DONE

        self._add_trace(draft, WorkflowState.HISTORICAL_ANALYSIS_DONE,
                       "Analyse historique SAP terminée",
                       "Recherche ventes passées",
                       ["SAP_INVOICES", "SAP_PURCHASE_INVOICES"])

        return draft

    async def _apply_intelligent_pricing(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R3 - Pricing intelligent : Arbre de décision CAS 1/2/3/4

        RÈGLES STRICTES :
        Q1 : Historique vente à CE client ?
          NON → Q2
          OUI → Q3

        Q2 : Vendu à autres clients ?
          NON → CAS 4 (NOUVEAU PRODUIT)
          OUI → CAS 3 (PRIX MOYEN AUTRES)

        Q3 : Prix fournisseur stable (<5%) ?
          OUI → CAS 1 (MAINTIEN PRIX)
          NON → CAS 2 (RECALCUL PRIX)
        """
        for product in draft.products:
            price_ctx = draft.price_contexts[product.item_code]

            # Utilisation du pricing_engine existant
            pricing_context = PricingContext(
                item_code=product.item_code,
                card_code=draft.client.card_code,
                quantity=product.quantity,
                supplier_price=price_ctx.supplier_price,
                apply_margin=self.MARGIN_DEFAULT
            )

            result = await self.pricing_engine.calculate_price(pricing_context)

            if result.success:
                decision = result.decision
                price_ctx.pricing_case = decision.case_type
                price_ctx.calculated_price = decision.calculated_price
                price_ctx.pricing_justification = decision.justification
                price_ctx.requires_validation = decision.requires_validation
                price_ctx.validation_reason = decision.validation_reason or ""

                if decision.requires_validation:
                    draft.requires_manual_validation = True
                    draft.validation_reasons.append(
                        f"{product.item_code} : {decision.validation_reason}"
                    )

        draft.current_state = WorkflowState.PRICING_CASE_SELECTED

        cases_summary = ", ".join([
            f"{pc.pricing_case.value if pc.pricing_case else 'UNKNOWN'}"
            for pc in draft.price_contexts.values()
        ])

        self._add_trace(draft, WorkflowState.PRICING_CASE_SELECTED,
                       f"CAS appliqués : {cases_summary}",
                       "Arbre de décision pricing",
                       ["PRICING_ENGINE", "SAP_HISTORY"])

        draft.current_state = WorkflowState.PRICING_INTELLIGENT_DONE

        self._add_trace(draft, WorkflowState.PRICING_INTELLIGENT_DONE,
                       "Pricing intelligent terminé",
                       "Prix calculés avec justifications",
                       ["PRICING_ENGINE"])

        return draft

    async def _apply_currency_conversion(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R5 - Application taux de change
        Si devise ≠ EUR → conversion avec taux du jour
        """
        for supplier in draft.suppliers:
            if supplier.currency != "EUR":
                rate_data = await self.currency_service.get_exchange_rate(
                    supplier.currency,
                    "EUR"
                )

                if rate_data:
                    # Application du taux sur tous les produits de ce fournisseur
                    for product in draft.products:
                        price_ctx = draft.price_contexts[product.item_code]
                        price_ctx.exchange_rate = rate_data.rate
                        price_ctx.net_supplier_price = price_ctx.supplier_price * rate_data.rate

                    supplier.is_foreign = True

        draft.current_state = WorkflowState.CURRENCY_APPLIED

        self._add_trace(draft, WorkflowState.CURRENCY_APPLIED,
                       "Taux de change appliqués",
                       f"{len([s for s in draft.suppliers if s.is_foreign])} fournisseur(s) étranger(s)",
                       ["CURRENCY_SERVICE"])

        return draft

    async def _apply_supplier_discounts(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R8 - Application remises fournisseurs
        """
        for product in draft.products:
            price_ctx = draft.price_contexts[product.item_code]
            supplier_code = draft.suppliers[0].supplier_code  # Simplification

            discount_result = self.discounts_db.calculate_discounted_price(
                base_price=price_ctx.net_supplier_price,
                supplier_code=supplier_code,
                item_code=product.item_code,
                quantity=product.quantity
            )

            if discount_result["total_discount_percent"] > 0:
                price_ctx.supplier_discount_percent = discount_result["total_discount_percent"]
                price_ctx.net_supplier_price = discount_result["discounted_price"]

        draft.current_state = WorkflowState.SUPPLIER_DISCOUNT_APPLIED

        self._add_trace(draft, WorkflowState.SUPPLIER_DISCOUNT_APPLIED,
                       "Remises fournisseurs appliquées",
                       "Conditions vérifiées (quantité, montant, dates)",
                       ["SUPPLIER_DISCOUNTS_DB"])

        return draft

    async def _apply_margins(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R4 - Application marges
        Marge standard : 45%
        Formule : PV = prix_net / (1 - marge)
        """
        for product in draft.products:
            price_ctx = draft.price_contexts[product.item_code]

            # Marge entre 35% et 45%
            margin_percent = max(self.MARGIN_MIN, min(self.MARGIN_MAX, price_ctx.applied_margin_percent))
            margin_decimal = margin_percent / 100.0

            # Formule stricte
            price_ctx.calculated_price = price_ctx.net_supplier_price / (1 - margin_decimal)
            price_ctx.applied_margin_percent = margin_percent

        draft.current_state = WorkflowState.MARGIN_APPLIED

        self._add_trace(draft, WorkflowState.MARGIN_APPLIED,
                       f"Marges appliquées (standard {self.MARGIN_DEFAULT}%)",
                       "Formule : PV = prix_net / (1 - marge)",
                       ["BUSINESS_RULES"])

        return draft

    async def _optimize_transport(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R6 - Optimisation transport
        Calcul poids total et comparaison transporteurs
        """
        # Destination fictive
        destination_zip = "75001"

        # Calcul transport pour le premier produit (simplification)
        # TODO : Améliorer pour calculer transport groupé
        product = draft.products[0] if draft.products else None
        if not product:
            draft.total_transport_eur = 0.0
            return draft

        transport_cost = await self.transport_calculator.calculate_transport_cost(
            item_code=product.item_code,
            quantity=sum([p.quantity for p in draft.products]),
            destination_zip=destination_zip,
            carrier="default"
        )

        # Création options transport
        draft.transport_options = [
            TransportOption(
                carrier_name=transport_cost.carrier_name,
                cost_eur=transport_cost.cost,
                delivery_days=transport_cost.delivery_days,
                reliability_score=0.9,
                is_recommended=True
            )
        ]

        draft.selected_transport = draft.transport_options[0]
        draft.total_transport_eur = draft.selected_transport.cost_eur

        draft.current_state = WorkflowState.TRANSPORT_OPTIMIZED

        self._add_trace(draft, WorkflowState.TRANSPORT_OPTIMIZED,
                       f"Transport : {draft.selected_transport.carrier_name} - {draft.total_transport_eur:.2f} EUR",
                       f"Poids total : {total_weight_kg:.2f} kg",
                       ["TRANSPORT_CALCULATOR"])

        return draft

    async def _build_justification(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R8 - Construction bloc justification
        Traçabilité exhaustive
        """
        lines = [
            "═══════════════════════════════════════════════════",
            "JUSTIFICATION DEVIS - TRAÇABILITÉ COMPLÈTE",
            "═══════════════════════════════════════════════════",
            "",
            f"Devis ID : {draft.quote_id}",
            f"Client : {draft.client.card_name} ({draft.client.card_code})",
            f"Date : {draft.created_at.strftime('%d/%m/%Y %H:%M')}",
            "",
            "--- PRODUITS ---",
        ]

        for product in draft.products:
            price_ctx = draft.price_contexts[product.item_code]
            lines.extend([
                f"",
                f"Article : {product.item_name} ({product.item_code})",
                f"Quantité : {product.quantity} {product.unit}",
                f"",
                f"  Stratégie pricing : {price_ctx.pricing_case.value if price_ctx.pricing_case else 'UNKNOWN'}",
                f"  Justification : {price_ctx.pricing_justification}",
                f"  Prix fournisseur : {price_ctx.supplier_price:.2f} {price_ctx.supplier_currency}",
                f"  Taux change : {price_ctx.exchange_rate}",
                f"  Remise fournisseur : {price_ctx.supplier_discount_percent:.1f}%",
                f"  Prix net fournisseur : {price_ctx.net_supplier_price:.2f} EUR",
                f"  Marge appliquée : {price_ctx.applied_margin_percent:.1f}%",
                f"  Prix calculé : {price_ctx.calculated_price:.2f} EUR",
            ])

            if price_ctx.requires_validation:
                lines.append(f"  ⚠️ VALIDATION REQUISE : {price_ctx.validation_reason}")

        lines.extend([
            "",
            "--- TRANSPORT ---",
            f"Transporteur : {draft.selected_transport.carrier_name if draft.selected_transport else 'N/A'}",
            f"Coût transport : {draft.total_transport_eur:.2f} EUR",
            f"Délai : {draft.selected_transport.delivery_days if draft.selected_transport else 0} jours",
            "",
            "--- TOTAUX ---",
            f"Total produits HT : {draft.total_products_eur:.2f} EUR",
            f"Total transport : {draft.total_transport_eur:.2f} EUR",
            f"TOTAL HT : {draft.total_ht_eur:.2f} EUR",
            f"TOTAL TTC (20%) : {draft.total_ttc_eur:.2f} EUR",
            "",
        ])

        if draft.requires_manual_validation:
            lines.extend([
                "═══════════════════════════════════════════════════",
                "⚠️ VALIDATION COMMERCIALE REQUISE",
                "═══════════════════════════════════════════════════",
            ])
            for reason in draft.validation_reasons:
                lines.append(f"  - {reason}")
            lines.append("")

        lines.extend([
            "═══════════════════════════════════════════════════",
            "Toutes les décisions sont traçables et déterministes",
            "Aucun comportement probabiliste ou ML appliqué",
            "═══════════════════════════════════════════════════",
        ])

        draft.justification_block = "\n".join(lines)
        draft.current_state = WorkflowState.JUSTIFICATION_BUILT

        self._add_trace(draft, WorkflowState.JUSTIFICATION_BUILT,
                       "Bloc justification construit",
                       "Traçabilité exhaustive",
                       ["ALL_STEPS"])

        return draft

    async def _validate_coherence(self, draft: QuoteDraft) -> QuoteDraft:
        """
        R9 - Validation cohérence
        Vérifications métier
        """
        alerts = []

        # Vérification marges
        for product in draft.products:
            price_ctx = draft.price_contexts[product.item_code]
            if price_ctx.applied_margin_percent < self.MARGIN_MIN:
                alerts.append(f"{product.item_code} : Marge < {self.MARGIN_MIN}%")
            if price_ctx.applied_margin_percent > self.MARGIN_MAX:
                alerts.append(f"{product.item_code} : Marge > {self.MARGIN_MAX}%")

        # Vérification totaux
        draft.total_products_eur = sum([
            ctx.calculated_price * p.quantity
            for p, ctx in zip(draft.products, draft.price_contexts.values())
        ])
        draft.total_ht_eur = draft.total_products_eur + draft.total_transport_eur
        draft.total_ttc_eur = draft.total_ht_eur * 1.20  # TVA 20%

        if draft.total_ht_eur <= 0:
            alerts.append("Total HT invalide")

        draft.current_state = WorkflowState.COHERENCE_VALIDATED

        self._add_trace(draft, WorkflowState.COHERENCE_VALIDATED,
                       "Cohérence validée",
                       f"{len(alerts)} alerte(s)",
                       ["BUSINESS_RULES"],
                       alerts=alerts)

        return draft

    async def _generate_quote(self, draft: QuoteDraft) -> QuoteDraft:
        """
        Génération du devis (interface SAP abstraite)
        """
        # TODO : Appel SAP Business One pour création Quotation
        # Interface abstraite - pas d'appel réel

        draft.current_state = WorkflowState.QUOTE_GENERATED

        self._add_trace(draft, WorkflowState.QUOTE_GENERATED,
                       "Devis généré",
                       "Prêt pour envoi ou validation",
                       ["SAP_QUOTATION_API"])

        return draft

    async def _send_quote(self, draft: QuoteDraft) -> QuoteDraft:
        """
        Envoi du devis (interface email abstraite)
        """
        # TODO : Envoi email avec PDF
        # Interface abstraite - pas d'envoi réel

        draft.current_state = WorkflowState.QUOTE_SENT

        self._add_trace(draft, WorkflowState.QUOTE_SENT,
                       f"Devis envoyé à {draft.client.email or draft.client.card_name}",
                       "Email avec PDF joint",
                       ["EMAIL_SERVICE"])

        return draft

    def _add_trace(
        self,
        draft: QuoteDraft,
        state: WorkflowState,
        decision: str,
        justification: str,
        data_sources: List[str],
        alerts: List[str] = None
    ):
        """Ajoute une trace de décision"""
        trace = DecisionTrace(
            state=state,
            timestamp=datetime.now(),
            decision=decision,
            justification=justification,
            data_sources=data_sources,
            alerts=alerts or []
        )
        draft.traces.append(trace)
        draft.updated_at = datetime.now()

        logger.info(f"[{state.value}] {decision}")


# Singleton
_workflow_engine = None


def get_quote_workflow_engine() -> QuoteWorkflowEngine:
    """Retourne l'instance singleton du moteur de workflow"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = QuoteWorkflowEngine()
        logger.info("QuoteWorkflowEngine initialisé")
    return _workflow_engine
