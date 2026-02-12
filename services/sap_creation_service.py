"""
SAP Creation Service - NOVA-SERVER
Gère la création de nouveaux clients et produits dans SAP B1.
"""

import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from services.sap import call_sap

logger = logging.getLogger(__name__)


# ==========================================
# MODÈLES PYDANTIC
# ==========================================


class NewClientData(BaseModel):
    """Données pour créer un nouveau client dans SAP."""

    card_name: str = Field(..., min_length=2, max_length=100, description="Nom du client")
    contact_email: Optional[str] = Field(None, description="Email de contact")
    phone: Optional[str] = Field(None, description="Téléphone")
    address: Optional[str] = Field(None, description="Adresse")
    city: Optional[str] = Field(None, description="Ville")
    zip_code: Optional[str] = Field(None, description="Code postal")
    country: str = Field(default="FR", description="Code pays (FR, BE, etc.)")

    # Infos complémentaires
    siret: Optional[str] = Field(None, description="Numéro SIRET")
    vat_number: Optional[str] = Field(None, description="Numéro TVA")
    payment_terms: str = Field(default="30", description="Conditions de paiement (jours)")

    # Métadonnées
    notes: Optional[str] = Field(None, description="Notes internes")
    source: str = Field(default="NOVA_EMAIL", description="Source de création")

    @validator('card_name')
    def validate_card_name(cls, v):
        """Valide le nom du client."""
        if not v or v.strip() == "":
            raise ValueError("Le nom du client est obligatoire")
        return v.strip().upper()

    @validator('contact_email')
    def validate_email(cls, v):
        """Valide le format email."""
        if v and '@' not in v:
            raise ValueError("Format email invalide")
        return v.lower() if v else None


class NewProductData(BaseModel):
    """Données pour créer un nouveau produit dans SAP."""

    item_code: str = Field(..., min_length=3, max_length=50, description="Code article")
    item_name: str = Field(..., min_length=3, max_length=200, description="Nom article")

    # Classification
    item_type: str = Field(default="itItems", description="Type article (itItems=stock)")
    item_group: Optional[int] = Field(None, description="Groupe article")

    # Prix et coûts
    supplier_code: Optional[str] = Field(None, description="Code fournisseur")
    supplier_item_code: Optional[str] = Field(None, description="Référence fournisseur")
    purchase_price: Optional[float] = Field(None, ge=0, description="Prix d'achat")
    sale_price: Optional[float] = Field(None, ge=0, description="Prix de vente")

    # Stock
    manage_stock: bool = Field(default=True, description="Gérer le stock")
    default_warehouse: str = Field(default="01", description="Entrepôt par défaut")

    # Métadonnées
    notes: Optional[str] = Field(None, description="Notes internes")
    source: str = Field(default="NOVA_EMAIL", description="Source de création")

    @validator('item_code')
    def validate_item_code(cls, v):
        """Valide le code article."""
        if not v or v.strip() == "":
            raise ValueError("Le code article est obligatoire")
        # Supprimer espaces et caractères spéciaux
        return v.strip().upper().replace(" ", "")


class CreationResult(BaseModel):
    """Résultat d'une création SAP."""
    success: bool
    entity_code: Optional[str] = None  # CardCode ou ItemCode créé
    entity_name: Optional[str] = None
    message: str
    sap_doc_entry: Optional[int] = None
    error_details: Optional[str] = None
    requires_manual_creation: bool = False


# ==========================================
# SERVICE CRÉATION SAP
# ==========================================


class SapCreationService:
    """Service de création d'entités dans SAP B1."""

    def __init__(self):
        """Initialise le service."""
        logger.info("SapCreationService initialisé")

    async def create_client(self, client_data: NewClientData) -> CreationResult:
        """
        Crée un nouveau client (Business Partner) dans SAP.

        Args:
            client_data: Données du client à créer

        Returns:
            CreationResult avec CardCode créé ou erreur
        """
        try:
            # Vérifier que SAP est connecté
            if not await self._check_sap_connection():
                return CreationResult(
                    success=False,
                    message="Connexion SAP indisponible",
                    error_details="Impossible de se connecter à SAP B1"
                )

            # Construire le payload SAP
            payload = {
                "CardType": "cCustomer",  # Type client
                "CardName": client_data.card_name,
                "CardForeignName": client_data.card_name,  # Nom alternatif
                "GroupCode": 100,  # Groupe client par défaut (à adapter)
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO",

                # Contact principal
                "EmailAddress": client_data.contact_email or "",
                "Phone1": client_data.phone or "",

                # Adresse
                "Address": client_data.address or "",
                "ZipCode": client_data.zip_code or "",
                "City": client_data.city or "",
                "Country": client_data.country,

                # Infos comptables
                "FederalTaxID": client_data.siret or "",  # SIRET
                "AdditionalID": client_data.vat_number or "",  # TVA
                "PayTermsGrpCode": int(client_data.payment_terms) if client_data.payment_terms.isdigit() else -1,

                # Métadonnées
                "U_NOVA_SOURCE": client_data.source,
                "U_NOVA_NOTES": client_data.notes or "",
            }

            # Nettoyer les valeurs vides
            payload = {k: v for k, v in payload.items() if v not in [None, "", []]}

            # Appeler l'API SAP pour créer le Business Partner
            logger.info(f"Création client SAP: {client_data.card_name}")

            result = await call_sap(
                endpoint="/BusinessPartners",
                method="POST",
                data=payload
            )

            # Récupérer le CardCode créé
            card_code = result.get("CardCode")

            if card_code:
                logger.info(f"✅ Client créé avec succès: {card_code}")
                return CreationResult(
                    success=True,
                    entity_code=card_code,
                    entity_name=client_data.card_name,
                    message=f"Client {client_data.card_name} créé avec CardCode {card_code}",
                    sap_doc_entry=result.get("DocEntry")
                )
            else:
                logger.error(f"CardCode non retourné par SAP: {result}")
                return CreationResult(
                    success=False,
                    message="Erreur lors de la création: CardCode non retourné",
                    error_details=str(result)
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Erreur création client SAP: {error_msg}")

            # Vérifier si c'est une erreur de doublon
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                return CreationResult(
                    success=False,
                    message=f"Client {client_data.card_name} existe déjà dans SAP",
                    error_details=error_msg
                )

            return CreationResult(
                success=False,
                message=f"Erreur lors de la création du client",
                error_details=error_msg
            )

    async def create_product(self, product_data: NewProductData) -> CreationResult:
        """
        Crée un nouveau produit (Item) dans SAP.

        Args:
            product_data: Données du produit à créer

        Returns:
            CreationResult avec ItemCode créé ou erreur
        """
        try:
            # Vérifier que SAP est connecté
            if not await self._check_sap_connection():
                return CreationResult(
                    success=False,
                    message="Connexion SAP indisponible",
                    error_details="Impossible de se connecter à SAP B1"
                )

            # Construire le payload SAP
            payload = {
                "ItemCode": product_data.item_code,
                "ItemName": product_data.item_name,
                "ItemType": product_data.item_type,
                "ManageSerialNumbers": "tNO",
                "ManageBatchNumbers": "tNO",
                "Valid": "tYES",
                "Frozen": "tNO",
                "PurchaseItem": "tYES",
                "SalesItem": "tYES",
                "InventoryItem": "tYES" if product_data.manage_stock else "tNO",

                # Classification
                "ItemsGroupCode": product_data.item_group or 100,

                # Prix
                "ItemPrices": []
            }

            # Ajouter le prix de vente si fourni
            if product_data.sale_price and product_data.sale_price > 0:
                payload["ItemPrices"].append({
                    "PriceList": 1,  # Liste de prix par défaut
                    "Price": product_data.sale_price,
                    "Currency": "EUR"
                })

            # Informations fournisseur
            if product_data.supplier_code:
                payload["PreferredVendor"] = product_data.supplier_code
                payload["SupplierCatalogNo"] = product_data.supplier_item_code or ""

            # Entrepôt par défaut
            if product_data.manage_stock:
                payload["DefaultWarehouse"] = product_data.default_warehouse

            # Métadonnées
            payload["U_NOVA_SOURCE"] = product_data.source
            if product_data.notes:
                payload["U_NOVA_NOTES"] = product_data.notes

            # Nettoyer les valeurs vides
            payload = {k: v for k, v in payload.items() if v not in [None, "", []]}

            # Appeler l'API SAP pour créer l'Item
            logger.info(f"Création produit SAP: {product_data.item_code} - {product_data.item_name}")

            result = await call_sap(
                endpoint="/Items",
                method="POST",
                data=payload
            )

            # Récupérer l'ItemCode créé
            item_code = result.get("ItemCode")

            if item_code:
                logger.info(f"✅ Produit créé avec succès: {item_code}")
                return CreationResult(
                    success=True,
                    entity_code=item_code,
                    entity_name=product_data.item_name,
                    message=f"Produit {product_data.item_name} créé avec ItemCode {item_code}",
                    sap_doc_entry=result.get("DocEntry")
                )
            else:
                logger.error(f"ItemCode non retourné par SAP: {result}")
                return CreationResult(
                    success=False,
                    message="Erreur lors de la création: ItemCode non retourné",
                    error_details=str(result)
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Erreur création produit SAP: {error_msg}")

            # Vérifier si c'est une erreur de doublon
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                return CreationResult(
                    success=False,
                    message=f"Produit {product_data.item_code} existe déjà dans SAP",
                    error_details=error_msg
                )

            return CreationResult(
                success=False,
                message=f"Erreur lors de la création du produit",
                error_details=error_msg
            )

    async def check_product_in_supplier_files(
        self,
        item_code: str,
        supplier_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Vérifie si un produit existe dans les fichiers fournisseurs.

        Args:
            item_code: Code article à rechercher
            supplier_name: Nom du fournisseur (optionnel)

        Returns:
            Dictionnaire avec les données fournisseur si trouvé, None sinon
        """
        try:
            from services.supplier_tariffs_db import get_supplier_tariffs_db

            db = get_supplier_tariffs_db()

            # Rechercher dans la base des tarifs fournisseurs
            tariffs = db.search_tariffs(
                supplier_name=supplier_name,
                item_code=item_code,
                limit=1
            )

            if tariffs:
                logger.info(f"✅ Produit {item_code} trouvé dans fichiers fournisseurs")
                return {
                    "found": True,
                    "supplier_name": tariffs[0]["supplier_name"],
                    "item_code": tariffs[0]["item_code"],
                    "description": tariffs[0]["description"],
                    "unit_price": tariffs[0]["unit_price"],
                    "currency": tariffs[0]["currency"],
                    "last_update": tariffs[0]["last_update"]
                }

            logger.info(f"ℹ️ Produit {item_code} NON trouvé dans fichiers fournisseurs")
            return None

        except Exception as e:
            logger.error(f"Erreur recherche fichiers fournisseurs: {e}")
            return None

    async def _check_sap_connection(self) -> bool:
        """Vérifie que la connexion SAP est disponible."""
        try:
            # Tenter une requête simple pour vérifier la connexion
            await call_sap("/Companies")
            return True
        except Exception as e:
            logger.error(f"Connexion SAP indisponible: {e}")
            return False


# ==========================================
# SINGLETON
# ==========================================

_sap_creation_service: Optional[SapCreationService] = None


def get_sap_creation_service() -> SapCreationService:
    """Retourne l'instance singleton du service de création SAP."""
    global _sap_creation_service
    if _sap_creation_service is None:
        _sap_creation_service = SapCreationService()
    return _sap_creation_service
