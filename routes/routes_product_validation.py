"""
Routes API pour la validation et création de produits.
Gère les mappings externes → SAP et la création d'articles.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from services.product_mapping_db import get_product_mapping_db
from services.sap_product_creator import get_sap_product_creator

router = APIRouter(prefix="/api/products", tags=["Product Validation"])
logger = logging.getLogger(__name__)


# ===== MODÈLES PYDANTIC =====

class ProductMappingResponse(BaseModel):
    external_code: str
    external_description: Optional[str]
    supplier_card_code: str
    supplier_name: Optional[str] = None
    matched_item_code: Optional[str]
    match_method: Optional[str]
    confidence_score: float
    status: str
    created_at: str
    use_count: int = 0


class ValidateMappingRequest(BaseModel):
    external_code: str
    supplier_card_code: str
    matched_item_code: str


class CreateProductRequest(BaseModel):
    external_code: str
    external_description: str
    supplier_card_code: str
    new_item_code: Optional[str] = None  # Si None, auto-généré
    item_name: str
    item_group: str = "100"
    purchase_item: bool = True
    sales_item: bool = True
    inventory_item: bool = True


class BulkCreateRequest(BaseModel):
    supplier_card_code: str
    prefix: str = "RONDOT"
    auto_generate_codes: bool = True


# ===== ENDPOINTS =====

@router.get("/pending")
async def get_pending_products(
    limit: int = Query(default=100, le=500),
    supplier: Optional[str] = None
) -> List[ProductMappingResponse]:
    """
    Récupère la liste des produits en attente de validation.

    Args:
        limit: Nombre max de résultats
        supplier: Filtrer par CardCode fournisseur (optionnel)

    Returns:
        Liste des mappings PENDING
    """
    mapping_db = get_product_mapping_db()

    try:
        # Si filtre fournisseur, requête custom
        if supplier:
            import sqlite3
            conn = sqlite3.connect(mapping_db.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM product_code_mapping
                WHERE status = 'PENDING'
                AND supplier_card_code = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (supplier, limit))

            rows = cursor.fetchall()
            conn.close()
            pending = [dict(row) for row in rows]
        else:
            pending = mapping_db.get_pending_mappings(limit=limit)

        # Convertir en modèles Pydantic
        return [
            ProductMappingResponse(
                external_code=p["external_code"],
                external_description=p.get("external_description"),
                supplier_card_code=p["supplier_card_code"],
                matched_item_code=p.get("matched_item_code"),
                match_method=p.get("match_method"),
                confidence_score=p.get("confidence_score", 0.0),
                status=p["status"],
                created_at=p["created_at"],
                use_count=p.get("use_count", 0)
            )
            for p in pending
        ]

    except Exception as e:
        logger.error(f"Erreur récupération produits pending: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_mapping(request: ValidateMappingRequest) -> Dict[str, Any]:
    """
    Valide manuellement un mapping externe → SAP existant.

    Args:
        request: external_code, supplier_card_code, matched_item_code

    Returns:
        {"success": true, "message": "..."}
    """
    mapping_db = get_product_mapping_db()

    try:
        mapping_db.validate_mapping(
            external_code=request.external_code,
            supplier_card_code=request.supplier_card_code,
            matched_item_code=request.matched_item_code
        )

        return {
            "success": True,
            "message": f"Mapping validé: {request.external_code} → {request.matched_item_code}"
        }

    except Exception as e:
        logger.error(f"Erreur validation mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_product_in_sap(request: CreateProductRequest) -> Dict[str, Any]:
    """
    Crée un nouveau produit dans SAP B1 et valide le mapping.

    Args:
        request: Données produit (code, nom, groupe, etc.)

    Returns:
        {"success": true, "item_code": "...", "message": "..."}
    """
    creator = get_sap_product_creator()

    try:
        # Générer code SAP si non fourni
        item_code = request.new_item_code
        if not item_code:
            item_code = creator.generate_item_code(request.external_code)

        # Créer dans SAP
        result = await creator.create_product(
            item_code=item_code,
            item_name=request.item_name,
            item_group=request.item_group,
            purchase_item=request.purchase_item,
            sales_item=request.sales_item,
            inventory_item=request.inventory_item,
            external_code=request.external_code,
            external_description=request.external_description,
            supplier_card_code=request.supplier_card_code
        )

        if result["success"]:
            return {
                "success": True,
                "item_code": result["item_code"],
                "message": f"Produit {result['item_code']} créé avec succès dans SAP et mapping validé"
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur création produit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-create")
async def bulk_create_products(request: BulkCreateRequest) -> Dict[str, Any]:
    """
    Crée en masse les produits PENDING pour un fournisseur.

    Args:
        request: supplier_card_code, prefix, auto_generate_codes

    Returns:
        {"total": X, "created": Y, "failed": Z, "details": [...]}
    """
    creator = get_sap_product_creator()

    try:
        result = await creator.bulk_create_from_pending(
            supplier_card_code=request.supplier_card_code,
            prefix=request.prefix,
            auto_generate_codes=request.auto_generate_codes
        )

        return result

    except Exception as e:
        logger.error(f"Erreur création en masse: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mapping/statistics")
async def get_mapping_statistics() -> Dict[str, int]:
    """
    Retourne les statistiques des mappings.

    Returns:
        {"total": X, "validated": Y, "pending": Z, ...}
    """
    mapping_db = get_product_mapping_db()

    try:
        stats = mapping_db.get_statistics()
        return stats

    except Exception as e:
        logger.error(f"Erreur récupération statistiques: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mapping/{external_code}")
async def delete_mapping(
    external_code: str,
    supplier_card_code: str = Query(...)
) -> Dict[str, Any]:
    """
    Supprime un mapping (rejeter un produit).

    Args:
        external_code: Code externe à supprimer
        supplier_card_code: CardCode fournisseur

    Returns:
        {"success": true, "message": "..."}
    """
    mapping_db = get_product_mapping_db()

    try:
        import sqlite3
        conn = sqlite3.connect(mapping_db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM product_code_mapping
            WHERE external_code = ?
            AND supplier_card_code = ?
        """, (external_code, supplier_card_code))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            return {
                "success": True,
                "message": f"Mapping {external_code} supprimé"
            }
        else:
            raise HTTPException(status_code=404, detail="Mapping non trouvé")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_sap_products(
    query: str = Query(..., min_length=2),
    limit: int = Query(default=20, le=100)
) -> List[Dict[str, str]]:
    """
    Recherche des produits SAP existants par code ou nom.

    Args:
        query: Texte de recherche
        limit: Nombre max de résultats

    Returns:
        Liste de produits SAP matchant la recherche
    """
    try:
        from services.sap_cache_db import get_sap_cache_db
        cache_db = get_sap_cache_db()

        import sqlite3
        conn = sqlite3.connect(cache_db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Recherche par code ou nom
        cursor.execute("""
            SELECT ItemCode, ItemName, ItemGroup
            FROM sap_items
            WHERE ItemCode LIKE ?
            OR ItemName LIKE ?
            ORDER BY ItemCode
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "item_code": row["ItemCode"],
                "item_name": row["ItemName"] or "",
                "item_group": str(row["ItemGroup"]) if row["ItemGroup"] else ""
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Erreur recherche produits: {e}")
        raise HTTPException(status_code=500, detail=str(e))
