# routes/routes_products.py
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import logging
from services.mcp_connector import MCPConnector

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/search_products_advanced")
async def search_products_advanced(
    q: Optional[str] = Query(None, description="Terme de recherche (nom ou référence)"),
    limit: int = Query(20, description="Nombre max de résultats", le=100),
    adaptive_limit: bool = Query(True, description="Limite adaptative basée sur le total")
):
    """
    Recherche avancée de produits dans SAP avec limite adaptative
    """
    try:
        logger.info(f"Recherche produits SAP: q='{q}', limit={limit}, adaptive={adaptive_limit}")
        
        results = {
            "success": False,
            "products": [],
            "total_found": 0,
            "search_term": q,
            "limit_used": limit,
            "adaptive_info": {}
        }
        
        # Si pas de terme de recherche, récupérer un échantillon global
        if not q or q.strip() == "":
            logger.info("Aucun terme de recherche - récupération d'un échantillon")
            
            if adaptive_limit:
                # Première requête pour compter le total
                count_result = await MCPConnector.call_sap_mcp("sap_read", {
                    "endpoint": "/Items?$filter=ItemType eq 'itItems'&$select=ItemCode&$inlinecount=allpages&$top=1",
                    "method": "GET"
                })
                
                if "error" not in count_result and "value" in count_result:
                    # Extraire le nombre total depuis les métadonnées OData
                    total_count = count_result.get("odata.count", 0)
                    if total_count == 0:
                        # Fallback si odata.count n'est pas disponible
                        total_count = len(count_result.get("value", [])) if count_result.get("value") else 0
                    
                    # Calculer 20% du total, minimum 10, maximum 50
                    adaptive_limit_calc = max(10, min(50, int(total_count * 0.2)))
                    limit = adaptive_limit_calc
                    
                    results["adaptive_info"] = {
                        "total_products_sap": total_count,
                        "percentage_shown": 20,
                        "calculated_limit": adaptive_limit_calc
                    }
                    
                    logger.info(f"Limite adaptative: {total_count} produits total -> affichage de {limit}")
            
            # Récupérer l'échantillon de produits
            sample_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$filter=ItemType eq 'itItems'&$orderby=ItemCode&$top={limit}",
                "method": "GET"
            })
            
        else:
            # Recherche par terme
            logger.info(f"Recherche par terme: {q}")
            sample_result = await MCPConnector.call_sap_mcp("sap_search", {
                "query": q.strip(),
                "entity_type": "Items",
                "limit": limit
            })
        
        # Traitement des résultats
        if "error" in sample_result:
            logger.error(f"Erreur SAP: {sample_result['error']}")
            results["error"] = sample_result["error"]
            return results
        
        # Extraire les produits selon le format de réponse
        raw_products = []
        if "results" in sample_result:  # Format de sap_search
            raw_products = sample_result["results"]
            results["total_found"] = sample_result.get("count", len(raw_products))
        elif "value" in sample_result:  # Format de sap_read
            raw_products = sample_result["value"]
            results["total_found"] = len(raw_products)
        
        # Formater les produits pour l'interface
        formatted_products = []
        for product in raw_products:
            try:
                # Normaliser les champs selon les différents formats SAP
                item_code = product.get("ItemCode", "")
                item_name = product.get("ItemName", product.get("ItemDescription", "Sans nom"))
                
                # Stock - plusieurs sources possibles
                stock = 0
                if "QuantityOnStock" in product:
                    stock = float(product["QuantityOnStock"] or 0)
                elif "OnHand" in product:
                    stock = float(product["OnHand"] or 0)
                elif "InStock" in product:
                    stock = float(product["InStock"] or 0)
                
                # Prix - plusieurs sources possibles  
                price = 0
                if "Price" in product:
                    price = float(product["Price"] or 0)
                elif "ItemPrices" in product and product["ItemPrices"]:
                    price = float(product["ItemPrices"][0].get("Price", 0))
                
                # Unité
                unit = product.get("SalesUnit", product.get("InventoryUOM", "UN"))
                
                # Statut de disponibilité
                availability_status = "available" if stock > 0 else "out_of_stock"
                availability_color = "#10b981" if stock > 0 else "#ef4444"
                availability_text = f"{stock:.0f} en stock" if stock > 0 else "Rupture"
                
                formatted_product = {
                    "item_code": item_code,
                    "item_name": item_name,
                    "stock": stock,
                    "price": price,
                    "unit": unit,
                    "availability_status": availability_status,
                    "availability_color": availability_color,
                    "availability_text": availability_text,
                    "display_text": f"{item_code} - {item_name}",
                    "price_display": f"{price:.2f}€ HT" if price > 0 else "Prix non défini"
                }
                
                formatted_products.append(formatted_product)
                
            except Exception as e:
                logger.warning(f"Erreur formatage produit {product.get('ItemCode', 'UNKNOWN')}: {e}")
                continue
        
        results["success"] = True
        results["products"] = formatted_products
        results["limit_used"] = limit
        
        logger.info(f"✅ {len(formatted_products)} produits formatés retournés")
        return results
        
    except Exception as e:
        logger.exception(f"Erreur lors de la recherche de produits: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")

@router.get("/product_details/{item_code}")
async def get_product_details(item_code: str):
    """
    Récupère les détails complets d'un produit SAP
    """
    try:
        logger.info(f"Récupération détails produit: {item_code}")
        
        result = await MCPConnector.call_sap_mcp("sap_get_product_details", {
            "item_code": item_code
        })
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=f"Produit {item_code} non trouvé")
        
        return {
            "success": True,
            "product": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur détails produit {item_code}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {str(e)}")