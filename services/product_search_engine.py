# services/product_search_engine.py

import logging
from typing import Dict, List, Any
from services.mcp_connector import MCPConnector

logger = logging.getLogger("product_search_engine")

class ProductSearchEngine:
    """
    Moteur de recherche de produits par caractéristiques
    """
    
    def __init__(self):
        self.mcp_connector = MCPConnector()
    
    async def search_products_by_characteristics(self, search_criteria: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recherche des produits dans SAP selon les caractéristiques demandées
        """
        logger.info(f"Recherche produits avec critères: {search_criteria}")
        
        try:
            # Construire la requête de recherche SAP
            category = search_criteria.get("category", "")
            characteristics = search_criteria.get("characteristics", [])
            specifications = search_criteria.get("specifications", {})
            
            # Recherche dans le catalogue SAP
            # Adapter selon la structure réelle de votre SAP
            search_query = self._build_sap_search_query(category, characteristics, specifications)
            
            products_result = await self.mcp_connector.call_sap_mcp("sap_read", {
                "endpoint": f"/Items?$filter={search_query}",
                "method": "GET"
            })
            
            if "error" in products_result:
                return {"error": f"Erreur recherche SAP: {products_result['error']}"}
            
            # Analyser et scorer les résultats
            matched_products = self._analyze_and_score_products(
                products_result.get("value", []), 
                search_criteria
            )
            
            return {
                "success": True,
                "search_criteria": search_criteria,
                "matched_products": matched_products,
                "total_found": len(matched_products),
                "message": f"{len(matched_products)} produit(s) trouvé(s) correspondant à vos critères"
            }
            
        except Exception as e:
            logger.error(f"Erreur recherche produits: {str(e)}")
            return {"error": f"Erreur lors de la recherche: {str(e)}"}
    
    def _build_sap_search_query(self, category: str, characteristics: List[str], specifications: Dict[str, Any]) -> str:
        """
        Construit la requête de recherche SAP OData
        """
        conditions = []
        
        # Recherche par catégorie
        if category:
            conditions.append(f"contains(tolower(ItemName), '{category.lower()}')")
        
        # Recherche par caractéristiques
        for char in characteristics:
            conditions.append(f"contains(tolower(ItemName), '{char.lower()}')")
        
        # Recherche par spécifications (dans la description ou nom)
        for spec_key, spec_value in specifications.items():
            if isinstance(spec_value, str):
                conditions.append(f"contains(tolower(ItemName), '{spec_value.lower()}')")
            elif isinstance(spec_value, list):
                for value in spec_value:
                    conditions.append(f"contains(tolower(ItemName), '{value.lower()}')")
        
        return " and ".join(conditions) if conditions else "ItemCode ne ''"
    
    def _analyze_and_score_products(self, products: List[Dict], search_criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyse et score les produits selon leur correspondance aux critères
        """
        scored_products = []
        
        for product in products:
            score = self._calculate_match_score(product, search_criteria)
            if score > 0:  # Garder seulement les produits avec un score > 0
                scored_products.append({
                    "product": product,
                    "match_score": score,
                    "match_details": self._get_match_details(product, search_criteria),
                    "code": product.get("ItemCode", ""),
                    "name": product.get("ItemName", ""),
                    "price": product.get("Price", 0),
                    "stock": product.get("QuantityOnStock", 0)
                })
        
        # Trier par score décroissant
        scored_products.sort(key=lambda x: x["match_score"], reverse=True)
        return scored_products[:10]  # Top 10 résultats
    
    def _calculate_match_score(self, product: Dict[str, Any], search_criteria: Dict[str, Any]) -> float:
        """
        Calcule un score de correspondance entre 0 et 1
        """
        score = 0.0
        max_score = 0.0
        
        product_name = product.get("ItemName", "").lower()
        product_description = product.get("Description", "").lower()
        
        # Score pour catégorie
        category = search_criteria.get("category", "").lower()
        if category and category in product_name:
            score += 0.3
        max_score += 0.3
        
        # Score pour caractéristiques
        characteristics = search_criteria.get("characteristics", [])
        for char in characteristics:
            if char.lower() in product_name or char.lower() in product_description:
                score += 0.2
            max_score += 0.2
        
        # Score pour spécifications
        specifications = search_criteria.get("specifications", {})
        for spec_value in specifications.values():
            if isinstance(spec_value, str) and spec_value.lower() in product_name:
                score += 0.1
            elif isinstance(spec_value, list):
                for value in spec_value:
                    if value.lower() in product_name:
                        score += 0.1
            max_score += 0.1
        
        return score / max_score if max_score > 0 else 0.0
    
    def _get_match_details(self, product: Dict[str, Any], search_criteria: Dict[str, Any]) -> Dict[str, Any]:
        """
        Détaille pourquoi ce produit correspond aux critères
        """
        details = {
            "category_match": False,
            "characteristics_found": [],
            "specifications_found": []
        }
        
        product_name = product.get("ItemName", "").lower()
        
        # Vérifier correspondance catégorie
        category = search_criteria.get("category", "").lower()
        if category and category in product_name:
            details["category_match"] = True
        
        # Vérifier caractéristiques trouvées
        for char in search_criteria.get("characteristics", []):
            if char.lower() in product_name:
                details["characteristics_found"].append(char)
        
        # Vérifier spécifications trouvées
        for spec_key, spec_value in search_criteria.get("specifications", {}).items():
            if isinstance(spec_value, str) and spec_value.lower() in product_name:
                details["specifications_found"].append(f"{spec_key}: {spec_value}")
            elif isinstance(spec_value, list):
                for value in spec_value:
                    if value.lower() in product_name:
                        details["specifications_found"].append(f"{spec_key}: {value}")
        
        return details