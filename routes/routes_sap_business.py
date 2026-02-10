"""
Routes API pour SAP Business One - mail-to-biz
Gère les articles, prix et création de devis
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from services.sap_business_service import get_sap_business_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sap", tags=["SAP Business"])


# ===== MODÈLES DE REQUÊTE/RÉPONSE =====

class ItemSearchRequest(BaseModel):
    query: str
    top: int = 10


class ItemSearchResponse(BaseModel):
    success: bool
    items: List[Dict[str, Any]]
    count: int


class ItemPriceRequest(BaseModel):
    item_code: str
    card_code: Optional[str] = None
    quantity: float = 1


class ItemPriceResponse(BaseModel):
    success: bool
    item_code: str
    price: Optional[float] = None
    currency: str = "EUR"


class BusinessPartnerSearchRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class BusinessPartnerResponse(BaseModel):
    success: bool
    partner: Optional[Dict[str, Any]] = None


class BusinessPartnerCreateRequest(BaseModel):
    card_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class QuotationLineRequest(BaseModel):
    item_code: Optional[str] = None
    item_description: str
    quantity: float = 1
    unit_price: Optional[float] = None


class QuotationCreateRequest(BaseModel):
    card_code: str
    lines: List[QuotationLineRequest]
    comments: Optional[str] = None
    reference: Optional[str] = None  # ID de l'email source


class QuotationCreateResponse(BaseModel):
    success: bool
    doc_entry: Optional[int] = None
    doc_num: Optional[int] = None
    error: Optional[str] = None


# ===== ENDPOINTS =====

@router.get("/health")
async def sap_health():
    """Vérifie la connexion à SAP"""
    try:
        sap_service = get_sap_business_service()
        connected = await sap_service.ensure_session()

        return {
            "connected": connected,
            "company_db": sap_service.company_db,
            "base_url": sap_service.base_url
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/search", response_model=ItemSearchResponse)
async def search_items(request: ItemSearchRequest):
    """
    Recherche des articles dans SAP par code ou description

    Example:
        POST /api/sap/items/search
        {"query": "MOT", "top": 10}
    """
    try:
        sap_service = get_sap_business_service()
        items = await sap_service.search_items(request.query, request.top)

        items_dict = [item.model_dump() for item in items]

        return ItemSearchResponse(
            success=True,
            items=items_dict,
            count=len(items_dict)
        )

    except Exception as e:
        logger.error(f"Item search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/price", response_model=ItemPriceResponse)
async def get_item_price(request: ItemPriceRequest):
    """
    Récupère le prix d'un article

    Example:
        POST /api/sap/items/price
        {"item_code": "MOT-5KW-001", "card_code": "C00001", "quantity": 10}
    """
    try:
        sap_service = get_sap_business_service()
        price = await sap_service.get_item_price(
            request.item_code,
            request.card_code,
            request.quantity
        )

        return ItemPriceResponse(
            success=True,
            item_code=request.item_code,
            price=price,
            currency="EUR"
        )

    except Exception as e:
        logger.error(f"Get item price failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/partners/search", response_model=BusinessPartnerResponse)
async def search_business_partner(request: BusinessPartnerSearchRequest):
    """
    Recherche un Business Partner (client) dans SAP

    Example:
        POST /api/sap/partners/search
        {"name": "ACME Industries"}
    """
    try:
        sap_service = get_sap_business_service()
        partner = await sap_service.search_business_partner(
            request.name,
            request.email
        )

        partner_dict = partner.model_dump() if partner else None

        return BusinessPartnerResponse(
            success=True,
            partner=partner_dict
        )

    except Exception as e:
        logger.error(f"Partner search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/partners/create", response_model=BusinessPartnerResponse)
async def create_business_partner(request: BusinessPartnerCreateRequest):
    """
    Crée un nouveau Business Partner (client) dans SAP

    Example:
        POST /api/sap/partners/create
        {"card_name": "Nouveau Client", "email": "client@example.com"}
    """
    try:
        sap_service = get_sap_business_service()
        card_code = await sap_service.create_business_partner(
            request.card_name,
            request.email,
            request.phone
        )

        if not card_code:
            raise HTTPException(status_code=500, detail="Échec de la création du client")

        # Récupérer le client créé
        partner = await sap_service.search_business_partner(name=request.card_name)

        return BusinessPartnerResponse(
            success=True,
            partner=partner.model_dump() if partner else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Partner creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotations/create", response_model=QuotationCreateResponse)
async def create_quotation(request: QuotationCreateRequest):
    """
    Crée un devis (Sales Quotation) dans SAP

    Example:
        POST /api/sap/quotations/create
        {
            "card_code": "C00001",
            "lines": [
                {"item_code": "MOT-5KW-001", "item_description": "Moteur 5kW", "quantity": 10}
            ],
            "comments": "Devis généré depuis email",
            "reference": "email-123"
        }
    """
    try:
        sap_service = get_sap_business_service()

        # Convertir les lignes au format SAP
        sap_lines = []
        for line in request.lines:
            sap_line = {
                "ItemDescription": line.item_description,
                "Quantity": line.quantity
            }

            # Ajouter ItemCode si fourni
            if line.item_code:
                sap_line["ItemCode"] = line.item_code

            # Ajouter prix si fourni
            if line.unit_price is not None:
                sap_line["UnitPrice"] = line.unit_price

            sap_lines.append(sap_line)

        # Créer le devis
        doc_entry = await sap_service.create_quotation(
            card_code=request.card_code,
            lines=sap_lines,
            comments=request.comments,
            reference=request.reference
        )

        if not doc_entry:
            return QuotationCreateResponse(
                success=False,
                error="Échec de la création du devis dans SAP"
            )

        return QuotationCreateResponse(
            success=True,
            doc_entry=doc_entry,
            doc_num=None  # SAP génère le DocNum automatiquement
        )

    except Exception as e:
        logger.error(f"Quotation creation failed: {e}")
        return QuotationCreateResponse(
            success=False,
            error=str(e)
        )


@router.post("/quotations/from-email")
async def create_quotation_from_email(
    email_id: str,
    extracted_data: Dict[str, Any]
):
    """
    Crée un devis SAP à partir des données extraites d'un email

    Cette route orchestre:
    1. Recherche/création du client
    2. Recherche des articles et prix
    3. Création du devis

    Args:
        email_id: ID de l'email source
        extracted_data: Données extraites par l'IA (ExtractedQuoteData)
    """
    try:
        sap_service = get_sap_business_service()

        # 1. Gérer le client
        client_name = extracted_data.get("client_name") or "Client inconnu"
        client_email = extracted_data.get("client_email")
        client_siret = extracted_data.get("siret")  # SIRET extrait par l'IA
        client_phone = extracted_data.get("phone")

        # Rechercher le client existant
        partner = await sap_service.search_business_partner(
            name=client_name,
            email=client_email
        )

        # Créer le client s'il n'existe pas
        if not partner:
            logger.info(f"Client non trouvé, création avec validation complète: {client_name}")

            # Import du validateur client
            from services.client_validator import ClientValidator

            # Préparer les données pour validation
            client_data_for_validation = {
                "nom": client_name,
                "email": client_email,
                "siret": client_siret,
                "telephone": client_phone
            }

            # Variables pour stocker les données enrichies
            enriched_data = {}

            # Tenter validation et enrichissement si on a un SIRET
            if client_siret:
                try:
                    validator = ClientValidator()
                    logger.info(f"Validation et enrichissement du client via SIRET: {client_siret}")

                    # Valider et enrichir via INSEE et Pappers
                    validation_result = await validator.validate_and_enrich(client_data_for_validation)

                    if validation_result.get("valid"):
                        enriched_data = validation_result.get("enriched_data", {})
                        logger.info(f"✓ Client validé et enrichi via INSEE/Pappers")

                        # Log des données récupérées
                        if enriched_data.get("numero_tva_intra"):
                            logger.info(f"  TVA Intra: {enriched_data['numero_tva_intra']}")
                        if enriched_data.get("forme_juridique"):
                            logger.info(f"  Forme juridique: {enriched_data['forme_juridique']}")
                    else:
                        logger.warning(f"⚠ Validation client échouée, création avec données partielles")

                except Exception as e:
                    logger.warning(f"⚠ Impossible de valider le client (continuant avec données partielles): {e}")
            else:
                logger.info("Pas de SIRET fourni, création client sans enrichissement")

            # Créer le client dans SAP avec toutes les données disponibles
            card_code = await sap_service.create_business_partner(
                card_name=enriched_data.get("denomination") or client_name,
                email=client_email,
                phone=enriched_data.get("telephone") or client_phone,
                siret=enriched_data.get("siret") or client_siret,
                tva_intra=enriched_data.get("numero_tva_intra"),
                address=enriched_data.get("adresse_ligne_1"),
                city=enriched_data.get("ville"),
                zip_code=enriched_data.get("code_postal"),
                country=enriched_data.get("code_pays", "FR"),
                legal_form=enriched_data.get("forme_juridique"),
                capital=enriched_data.get("capital")
            )

            if not card_code:
                raise HTTPException(status_code=500, detail="Impossible de créer le client")

            logger.info(f"✓ Client créé dans SAP: {client_name} ({card_code})")
        else:
            card_code = partner.CardCode
            logger.info(f"Client trouvé: {partner.CardName} ({card_code})")

        # 2. Préparer les lignes du devis
        sap_lines = []
        products = extracted_data.get("products", [])

        # Import des services
        from services.supplier_tariffs_db import search_products
        from services.pricing_engine import get_pricing_engine
        from services.pricing_models import PricingContext
        import services.pricing_audit_db as pricing_audit_db

        pricing_engine = get_pricing_engine()

        for product in products:
            description = product.get("description", "")
            quantity = product.get("quantity", 1)
            reference = product.get("reference")

            item_code = None
            unit_price = None

            if reference:
                # 1. Rechercher l'article dans SAP
                items = await sap_service.search_items(reference, top=1)

                if items:
                    # Article trouvé dans SAP → Utiliser moteur pricing intelligent
                    item_code = items[0].ItemCode
                    logger.info(f"Article trouvé dans SAP: {reference} -> {item_code}")

                    # NOUVEAU : Pricing intelligent avec CAS 1/2/3/4
                    pricing_context = PricingContext(
                        item_code=item_code,
                        card_code=card_code,
                        quantity=quantity,
                        supplier_price=None,  # Sera récupéré automatiquement
                        apply_margin=45.0  # Marge RONDOT-SAS
                    )

                    pricing_result = await pricing_engine.calculate_price(pricing_context)

                    if pricing_result.success:
                        decision = pricing_result.decision
                        unit_price = decision.calculated_price

                        # Log pricing intelligent
                        logger.info(f"✓ Pricing {decision.case_type}: {item_code} = {unit_price:.2f} EUR")
                        logger.info(f"  {decision.justification}")

                        # Alerte si validation requise
                        if decision.requires_validation:
                            logger.warning(
                                f"⚠ VALIDATION COMMERCIALE REQUISE pour {item_code}:\n"
                                f"  Raison: {decision.validation_reason}\n"
                                f"  Alertes: {', '.join(decision.alerts)}"
                            )
                    else:
                        # Fallback pricing basique si erreur moteur
                        unit_price = await sap_service.get_item_price(item_code, card_code, quantity)
                        logger.warning(f"⚠ Fallback pricing basique: {pricing_result.error}")

                else:
                    # 2. Article non trouvé → chercher dans tarifs fournisseurs
                    logger.info(f"Article {reference} non trouvé dans SAP, recherche dans tarifs fournisseurs...")

                    supplier_products = search_products(reference, limit=1)

                    if supplier_products:
                        supplier_product = supplier_products[0]
                        supplier_price = supplier_product.get('unit_price')

                        logger.info(f"Produit trouvé chez fournisseur: {supplier_product.get('designation')}")

                        # 3. Créer l'article dans SAP SEULEMENT si on a un prix
                        if supplier_price and supplier_price > 0:
                            # Extraire toutes les métadonnées disponibles
                            item_code = await sap_service.create_item(
                                item_code=reference,
                                item_name=supplier_product.get('designation') or description,
                                purchase_price=supplier_price,
                                # Métadonnées enrichies depuis tarifs fournisseurs
                                delivery_days=supplier_product.get('delivery_days'),
                                transport_cost=supplier_product.get('transport_cost'),
                                transport_days=supplier_product.get('transport_days'),
                                supplier_code=supplier_product.get('supplier_code'),
                                supplier_name=supplier_product.get('supplier_name'),
                                weight=supplier_product.get('weight'),
                                dimensions=supplier_product.get('dimensions'),
                                characteristics=supplier_product.get('technical_specs')
                            )

                            if item_code:
                                # NOUVEAU : Pricing intelligent pour article créé (CAS 4 - Nouveau produit)
                                pricing_context = PricingContext(
                                    item_code=item_code,
                                    card_code=card_code,
                                    quantity=quantity,
                                    supplier_price=supplier_price,
                                    delivery_days=supplier_product.get('delivery_days'),
                                    transport_cost=supplier_product.get('transport_cost'),
                                    supplier_code=supplier_product.get('supplier_code'),
                                    supplier_name=supplier_product.get('supplier_name'),
                                    apply_margin=45.0
                                )

                                pricing_result = await pricing_engine.calculate_price(pricing_context)

                                if pricing_result.success:
                                    decision = pricing_result.decision
                                    unit_price = decision.calculated_price

                                    logger.info(f"✓ Article créé avec pricing {decision.case_type}: {item_code}")
                                    logger.info(f"  Prix fournisseur: {supplier_price:.2f} EUR")
                                    logger.info(f"  Prix vente calculé: {unit_price:.2f} EUR (marge {decision.margin_applied:.1f}%)")
                                    logger.info(f"  {decision.justification}")

                                    if decision.requires_validation:
                                        logger.warning(f"⚠ {decision.validation_reason}")
                                else:
                                    # Fallback sur prix fournisseur avec marge 45%
                                    unit_price = round(supplier_price * 1.45, 2)
                                    logger.warning(f"⚠ Fallback pricing basique (marge 45%): {pricing_result.error}")

                                if supplier_product.get('delivery_days'):
                                    logger.info(f"  Délai livraison fournisseur: {supplier_product.get('delivery_days')} jours")
                            else:
                                logger.error(f"✗ Échec création article {reference}")
                        else:
                            logger.warning(f"✗ Prix manquant pour {reference} - article non créé")

                    else:
                        # 4. Pas trouvé dans tarifs fournisseurs → impossible de créer
                        logger.warning(f"✗ Référence {reference} non trouvée dans tarifs fournisseurs - article non créé")

            # Si toujours pas d'ItemCode, on ne peut pas créer la ligne
            if not item_code:
                logger.error(f"Impossible de créer la ligne pour {reference or description}")
                continue

            sap_line = {
                "ItemCode": item_code,
                "ItemDescription": description or item_code,
                "Quantity": quantity
            }

            if unit_price:
                sap_line["UnitPrice"] = unit_price

            sap_lines.append(sap_line)

        # 3. Créer le devis
        if not sap_lines:
            raise HTTPException(
                status_code=400,
                detail="Aucune ligne de devis n'a pu être créée. Vérifiez que des articles existent dans SAP."
            )

        comments = f"Devis généré automatiquement depuis email {email_id}\n"
        if extracted_data.get("notes"):
            comments += f"\nNotes: {extracted_data['notes']}"

        doc_entry = await sap_service.create_quotation(
            card_code=card_code,
            lines=sap_lines,
            comments=comments,
            reference=email_id
        )

        if not doc_entry:
            raise HTTPException(status_code=500, detail="Échec de la création du devis dans SAP")

        return {
            "success": True,
            "doc_entry": doc_entry,
            "card_code": card_code,
            "lines_count": len(sap_lines),
            "message": f"Devis {doc_entry} créé avec succès pour {client_name}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create quotation from email failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
