# managers/product_manager.py
"""
ProductManager - Gestionnaire dédié aux produits
Extrait et optimisé depuis DevisWorkflow
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio

from services.mcp_connector import MCPConnector
from services.suggestion_engine import SuggestionEngine
from utils.common_utils import ResponseBuilder, ErrorHandler
from models.data_models import ProductData, StockInfo

logger = logging.getLogger(__name__)

class ProductManager:
    """Gestionnaire dédié aux opérations produits"""
    
    def __init__(self):
        self.mcp_connector = MCPConnector()
        self.suggestion_engine = SuggestionEngine()
        self.response_builder = ResponseBuilder()
        self.error_handler = ErrorHandler()
        
        # Cache pour les produits
        self.product_cache = {}
        self.cache_ttl = 180  # 3 minutes (plus court car stock change)
    
    async def find_products(self, product_codes: List[str]) -> List[Dict[str, Any]]:
        """
        Recherche des produits par codes
        
        Args:
            product_codes: Liste des codes produits à rechercher
            
        Returns:
            Liste des produits trouvés avec suggestions si nécessaire
        """
        try:
            logger.info(f"🔍 Recherche produits: {product_codes}")
            
            # Traitement parallèle des produits
            tasks = [self._find_single_product(code) for code in product_codes]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Traitement des résultats
            products = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Erreur produit {product_codes[i]}: {result}")
                    products.append({
                        "code": product_codes[i],
                        "found": False,
                        "error": str(result)
                    })
                else:
                    products.append(result)
            
            return products
            
        except Exception as e:
            logger.exception(f"Erreur recherche produits: {str(e)}")
            return [{"code": code, "found": False, "error": str(e)} for code in product_codes]
    
    async def _find_single_product(self, product_code: str) -> Dict[str, Any]:
        """Recherche d'un produit unique"""
        try:
            # Vérifier le cache
            cache_key = f"product_{product_code.upper()}"
            if cache_key in self.product_cache:
                cached_data = self.product_cache[cache_key]
                if (datetime.now() - cached_data['timestamp']).seconds < self.cache_ttl:
                    logger.info(f"✅ Produit {product_code} trouvé dans le cache")
                    return cached_data['data']
            
            # Recherche dans SAP
            result = await self.mcp_connector.call_sap_mcp("sap_get_product_details", {
                "item_code": product_code
            })
            
            if "error" not in result and result.get("ItemCode"):
                # Produit trouvé
                product_data = {
                    "code": result.get("ItemCode"),
                    "name": result.get("ItemName"),
                    "price": float(result.get("Price", 0)),
                    "stock": int(result.get("QuantityOnStock", 0)),
                    "available": result.get("InStock", False),
                    "found": True,
                    "source": "sap",
                    "raw_data": result
                }
                
                # Mise en cache
                self.product_cache[cache_key] = {
                    'data': product_data,
                    'timestamp': datetime.now()
                }
                
                return product_data
            else:
                # Produit non trouvé, générer des suggestions
                return await self._generate_product_suggestions(product_code)
                
        except Exception as e:
            logger.exception(f"Erreur recherche produit {product_code}: {str(e)}")
            return {
                "code": product_code,
                "found": False,
                "error": str(e)
            }
    async def _search_sap_product(self, product_code: str, product_name: str = "") -> Dict[str, Any]:
        """Recherche produit SAP pour EnhancedDevisWorkflow"""
        try:
            # Utiliser la fonction existante _find_single_product
            result = await self._find_single_product(product_code)
            
            if result.get("found"):
                return {"found": True, "data": result}
            else:
                return {"found": False, "error": result.get("error", "Produit non trouvé")}
        except Exception as e:
            return {"found": False, "error": str(e)}    
    async def _generate_product_suggestions(self, product_code: str) -> Dict[str, Any]:
        """Génération de suggestions pour produit non trouvé"""
        try:
            # Récupération de tous les produits pour suggestions
            all_products = await self._get_all_products()
            
            # Génération des suggestions
            suggestions = await self.suggestion_engine.suggest_product(product_code, all_products)
            
            return {
                "code": product_code,
                "found": False,
                "suggestions": suggestions.to_dict() if suggestions.has_suggestions else None,
                "message": f"Produit '{product_code}' non trouvé",
                "actions": [
                    {"action": "search_similar", "label": "Rechercher des produits similaires"},
                    {"action": "browse_catalog", "label": "Parcourir le catalogue"},
                    {"action": "contact_support", "label": "Contacter le support"}
                ]
            }
            
        except Exception as e:
            logger.exception(f"Erreur génération suggestions produit: {str(e)}")
            return {
                "code": product_code,
                "found": False,
                "error": str(e),
                "message": f"Produit '{product_code}' non trouvé"
            }
    
    async def validate_stock(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validation du stock pour les produits
        
        Args:
            products: Liste des produits avec quantités demandées
            
        Returns:
            Dict avec validation du stock
        """
        try:
            logger.info(f"📦 Validation stock pour {len(products)} produits")
            
            stock_validation = {
                "all_available": True,
                "products": [],
                "warnings": [],
                "total_value": 0.0
            }
            
            for product in products:
                if not product.get("found"):
                    continue
                
                requested_qty = product.get("quantity", 1)
                available_stock = product.get("stock", 0)
                unit_price = product.get("price", 0)
                
                product_validation = {
                    "code": product.get("code"),
                    "name": product.get("name"),
                    "requested_quantity": requested_qty,
                    "available_stock": available_stock,
                    "unit_price": unit_price,
                    "line_total": requested_qty * unit_price,
                    "stock_sufficient": available_stock >= requested_qty
                }
                
                if not product_validation["stock_sufficient"]:
                    stock_validation["all_available"] = False
                    stock_validation["warnings"].append(
                        f"Stock insuffisant pour {product.get('code')}: "
                        f"{available_stock} disponible, {requested_qty} demandé"
                    )
                    
                    # Proposer des alternatives
                    alternatives = await self._find_alternative_products(product.get("code"))
                    product_validation["alternatives"] = alternatives
                
                stock_validation["products"].append(product_validation)
                stock_validation["total_value"] += product_validation["line_total"]
            
            return stock_validation
            
        except Exception as e:
            logger.exception(f"Erreur validation stock: {str(e)}")
            return {
                "all_available": False,
                "products": [],
                "warnings": [f"Erreur validation stock: {str(e)}"],
                "total_value": 0.0
            }
    
    async def _find_alternative_products(self, product_code: str) -> List[Dict[str, Any]]:
        """Recherche de produits alternatifs"""
        try:
            # Récupération des produits de la même catégorie
            result = await self.mcp_connector.call_sap_mcp("sap_read", {
                "endpoint": "/Items?$filter=ItemsGroupCode eq 'SAME_CATEGORY'&$top=5",
                "method": "GET"
            })
            
            if "error" not in result and result.get("value"):
                return [
                    {
                        "code": item.get("ItemCode"),
                        "name": item.get("ItemName"),
                        "price": float(item.get("Price", 0)),
                        "stock": int(item.get("QuantityOnStock", 0)),
                        "available": item.get("InStock", False)
                    }
                    for item in result["value"][:3]  # Limiter à 3 alternatives
                ]
            
            return []
            
        except Exception as e:
            logger.warning(f"Erreur recherche alternatives: {str(e)}")
            return []
    
    async def _get_all_products(self) -> List[Dict[str, Any]]:
        """Récupération de tous les produits pour suggestions"""
        try:
            result = await self.mcp_connector.call_sap_mcp("sap_read", {
                "endpoint": "/Items?$top=500&$orderby=ItemCode",
                "method": "GET"
            })
            
            if "error" not in result and result.get("value"):
                return result["value"]
            
            return []
            
        except Exception as e:
            logger.warning(f"Erreur récupération produits: {str(e)}")
            return []
    
    async def get_product_catalog(self, category: str = None, limit: int = 100) -> Dict[str, Any]:
        """
        Récupération du catalogue produits
        
        Args:
            category: Catégorie de produits (optionnel)
            limit: Nombre maximum de produits
            
        Returns:
            Dict avec le catalogue
        """
        try:
            logger.info(f"📋 Récupération catalogue (catégorie: {category}, limit: {limit})")
            
            # Construction de la requête
            endpoint = f"/Items?$top={limit}&$orderby=ItemName"
            if category:
                endpoint += f"&$filter=ItemsGroupCode eq '{category}'"
            
            result = await self.mcp_connector.call_sap_mcp("sap_read", {
                "endpoint": endpoint,
                "method": "GET"
            })
            
            if "error" not in result and result.get("value"):
                products = []
                for item in result["value"]:
                    products.append({
                        "code": item.get("ItemCode"),
                        "name": item.get("ItemName"),
                        "price": float(item.get("Price", 0)),
                        "stock": int(item.get("QuantityOnStock", 0)),
                        "available": item.get("InStock", False),
                        "category": item.get("ItemsGroupCode"),
                        "description": item.get("User_Text", "")
                    })
                
                return {
                    "success": True,
                    "products": products,
                    "count": len(products),
                    "category": category
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Aucun produit trouvé"),
                    "products": [],
                    "count": 0
                }
                
        except Exception as e:
            logger.exception(f"Erreur récupération catalogue: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "products": [],
                "count": 0
            }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Statistiques du cache produits"""
        return {
            "cache_size": len(self.product_cache),
            "cache_keys": list(self.product_cache.keys()),
            "cache_ttl": self.cache_ttl
        }
    
    def clear_cache(self) -> None:
        """Vider le cache produits"""
        self.product_cache.clear()
        logger.info("Cache produits vidé")