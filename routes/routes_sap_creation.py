"""
Routes API pour la création d'entités SAP (clients, produits)
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import Optional

from services.sap_creation_service import (
    get_sap_creation_service,
    NewClientData,
    NewProductData,
    CreationResult
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==========================================
# ENDPOINTS CRÉATION CLIENT
# ==========================================


@router.post("/clients/create", response_model=CreationResult)
async def create_new_client(client_data: NewClientData):
    """
    Crée un nouveau client dans SAP B1.

    Args:
        client_data: Données du client à créer

    Returns:
        CreationResult avec CardCode créé ou erreur

    Example:
        POST /api/sap/clients/create
        {
            "card_name": "NOUVEAU CLIENT SAS",
            "contact_email": "contact@nouveauclient.fr",
            "phone": "0123456789",
            "address": "10 rue de la Paix",
            "city": "Paris",
            "zip_code": "75001",
            "country": "FR",
            "siret": "12345678900012",
            "payment_terms": "30",
            "notes": "Client créé depuis email NOVA"
        }
    """
    try:
        logger.info(f"Demande création client: {client_data.card_name}")

        creation_service = get_sap_creation_service()
        result = await creation_service.create_client(client_data)

        if not result.success:
            # Log l'erreur mais ne pas lever d'exception HTTP
            # pour permettre au client de voir les détails
            logger.warning(f"Échec création client: {result.message}")

        return result

    except Exception as e:
        logger.error(f"Erreur endpoint création client: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la création du client: {str(e)}"
        )


@router.get("/clients/check-exists/{card_name}")
async def check_client_exists(card_name: str):
    """
    Vérifie si un client existe déjà dans SAP.

    Args:
        card_name: Nom du client à vérifier

    Returns:
        exists: bool, client_data si existe

    Example:
        GET /api/sap/clients/check-exists/SAVERGLASS
    """
    try:
        from services.sap import call_sap

        # Rechercher le client par nom
        result = await call_sap(
            endpoint="/BusinessPartners",
            params={
                "$filter": f"contains(CardName, '{card_name}')",
                "$select": "CardCode,CardName,EmailAddress,Phone1",
                "$top": 10
            }
        )

        clients = result.get("value", [])

        if clients:
            return {
                "exists": True,
                "count": len(clients),
                "clients": clients,
                "message": f"{len(clients)} client(s) trouvé(s) avec nom similaire"
            }
        else:
            return {
                "exists": False,
                "count": 0,
                "clients": [],
                "message": "Aucun client trouvé avec ce nom"
            }

    except Exception as e:
        logger.error(f"Erreur vérification client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ENDPOINTS CRÉATION PRODUIT
# ==========================================


@router.post("/products/create", response_model=CreationResult)
async def create_new_product(product_data: NewProductData):
    """
    Crée un nouveau produit dans SAP B1.

    Args:
        product_data: Données du produit à créer

    Returns:
        CreationResult avec ItemCode créé ou erreur

    Example:
        POST /api/sap/products/create
        {
            "item_code": "NOUVEAU-001",
            "item_name": "NOUVEAU PRODUIT TEST",
            "item_type": "itItems",
            "supplier_code": "FOURNISSEUR-01",
            "purchase_price": 50.00,
            "sale_price": 75.00,
            "manage_stock": true,
            "notes": "Produit créé depuis email NOVA"
        }
    """
    try:
        logger.info(f"Demande création produit: {product_data.item_code}")

        creation_service = get_sap_creation_service()
        result = await creation_service.create_product(product_data)

        if not result.success:
            logger.warning(f"Échec création produit: {result.message}")

        return result

    except Exception as e:
        logger.error(f"Erreur endpoint création produit: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la création du produit: {str(e)}"
        )


@router.get("/products/check-exists/{item_code}")
async def check_product_exists(item_code: str):
    """
    Vérifie si un produit existe déjà dans SAP.

    Args:
        item_code: Code article à vérifier

    Returns:
        exists: bool, product_data si existe

    Example:
        GET /api/sap/products/check-exists/2323060165
    """
    try:
        from services.sap import get_sap_service

        sap = get_sap_service()

        # Rechercher le produit par code
        result = await call_sap(
            endpoint=f"/Items('{item_code}')",
            params={"$select": "ItemCode,ItemName,SalesItem,PurchaseItem"}
        )

        if result and result.get("ItemCode"):
            return {
                "exists": True,
                "product": result,
                "message": f"Produit {item_code} existe déjà dans SAP"
            }
        else:
            return {
                "exists": False,
                "product": None,
                "message": "Produit non trouvé dans SAP"
            }

    except Exception as e:
        # Si erreur 404, produit n'existe pas
        if "404" in str(e) or "not found" in str(e).lower():
            return {
                "exists": False,
                "product": None,
                "message": "Produit non trouvé dans SAP"
            }

        logger.error(f"Erreur vérification produit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/check-supplier-files/{item_code}")
async def check_product_in_supplier_files(
    item_code: str,
    supplier_name: Optional[str] = None
):
    """
    Vérifie si un produit existe dans les fichiers fournisseurs.

    Args:
        item_code: Code article à rechercher
        supplier_name: Nom du fournisseur (optionnel)

    Returns:
        found: bool, supplier_data si trouvé

    Example:
        GET /api/sap/products/check-supplier-files/2323060165?supplier_name=SAVERGLASS
    """
    try:
        creation_service = get_sap_creation_service()

        result = await creation_service.check_product_in_supplier_files(
            item_code=item_code,
            supplier_name=supplier_name
        )

        if result:
            return {
                "found": True,
                "supplier_data": result,
                "message": f"Produit trouvé dans fichiers fournisseurs"
            }
        else:
            return {
                "found": False,
                "supplier_data": None,
                "message": "Produit non trouvé dans fichiers fournisseurs",
                "recommendation": "Création manuelle requise"
            }

    except Exception as e:
        logger.error(f"Erreur vérification fichiers fournisseurs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ENDPOINT WORKFLOW COMPLET
# ==========================================


@router.post("/workflow/check-and-create-if-needed")
async def workflow_check_and_create(
    entity_type: str,  # "client" ou "product"
    entity_data: dict
):
    """
    Workflow complet: vérifie existence et crée si nécessaire.

    Args:
        entity_type: "client" ou "product"
        entity_data: Données de l'entité

    Returns:
        Résultat avec action effectuée (exists/created/error)

    Example:
        POST /api/sap/workflow/check-and-create-if-needed
        {
            "entity_type": "client",
            "entity_data": {...}
        }
    """
    try:
        if entity_type not in ["client", "product"]:
            raise HTTPException(
                status_code=400,
                detail="entity_type doit être 'client' ou 'product'"
            )

        creation_service = get_sap_creation_service()

        # WORKFLOW CLIENT
        if entity_type == "client":
            card_name = entity_data.get("card_name")
            if not card_name:
                raise HTTPException(status_code=400, detail="card_name requis")

            # Vérifier si existe
            check_result = await check_client_exists(card_name)

            if check_result["exists"]:
                return {
                    "action": "already_exists",
                    "entity_code": check_result["clients"][0]["CardCode"],
                    "message": "Client existe déjà",
                    "existing_data": check_result["clients"][0]
                }

            # Créer le client
            client_data = NewClientData(**entity_data)
            creation_result = await creation_service.create_client(client_data)

            return {
                "action": "created" if creation_result.success else "error",
                "entity_code": creation_result.entity_code,
                "message": creation_result.message,
                "creation_result": creation_result.dict()
            }

        # WORKFLOW PRODUIT
        elif entity_type == "product":
            item_code = entity_data.get("item_code")
            if not item_code:
                raise HTTPException(status_code=400, detail="item_code requis")

            # 1. Vérifier si existe dans SAP
            check_sap = await check_product_exists(item_code)

            if check_sap["exists"]:
                return {
                    "action": "already_exists_sap",
                    "entity_code": item_code,
                    "message": "Produit existe déjà dans SAP",
                    "existing_data": check_sap["product"]
                }

            # 2. Vérifier dans fichiers fournisseurs
            supplier_name = entity_data.get("supplier_name")
            check_supplier = await creation_service.check_product_in_supplier_files(
                item_code=item_code,
                supplier_name=supplier_name
            )

            if check_supplier:
                # Enrichir avec données fournisseur
                entity_data["item_name"] = entity_data.get("item_name") or check_supplier["description"]
                entity_data["purchase_price"] = check_supplier["unit_price"]
                entity_data["supplier_code"] = check_supplier["supplier_name"]

                message_suffix = " (données enrichies depuis fichiers fournisseurs)"
            else:
                message_suffix = " (création manuelle - non trouvé dans fichiers fournisseurs)"

            # 3. Créer le produit
            product_data = NewProductData(**entity_data)
            creation_result = await creation_service.create_product(product_data)

            return {
                "action": "created" if creation_result.success else "error",
                "entity_code": creation_result.entity_code,
                "message": creation_result.message + message_suffix,
                "enriched_from_supplier": check_supplier is not None,
                "creation_result": creation_result.dict()
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur workflow création: {e}")
        raise HTTPException(status_code=500, detail=str(e))
