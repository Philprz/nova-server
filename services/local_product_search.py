# services/local_product_search.py
# Service de recherche locale produits avec LLM

import os
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from services.llm_extractor import LLMExtractor

logger = logging.getLogger('local_product_search')
load_dotenv()

class LocalProductSearchService:
    """Service de recherche locale dans produits_sap avec assistance LLM"""
    
    def __init__(self):
        db_url = os.getenv("DATABASE_URL")
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.llm_extractor = LLMExtractor()
    
    async def search_products(self, product_name: str, product_code: str = "") -> Dict[str, Any]:
        """Recherche produits locale - Format compatible _smart_product_search"""
        
        try:
            # 1. Recherche exacte par code si fourni
            if product_code:
                exact_match = self._search_by_exact_code(product_code)
                if exact_match:
                    return {"found": True, "products": [exact_match], "method": "exact_code_local"}
            
            # 2. Recherche intelligente par nom
            if product_name:
                smart_results = await self._intelligent_name_search(product_name)
                if smart_results:
                    return {"found": True, "products": smart_results, "method": "intelligent_local"}
            
            # 3. Recherche fuzzy en dernier recours
            fuzzy_results = self._fuzzy_search(product_name)
            if fuzzy_results:
                return {"found": True, "products": fuzzy_results, "method": "fuzzy_local"}
            
            return {"found": False, "products": [], "method": "no_match_local"}
            
        except Exception as e:
            logger.error(f"❌ Erreur search_products: {str(e)}")
            return {"found": False, "products": [], "method": "error_local", "error": str(e)}
    
    def _search_by_exact_code(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Recherche exacte par ItemCode"""
        
        with self.SessionLocal() as session:
            try:
                result = session.execute(
                    text("""
                    SELECT item_code, item_name, u_description, avg_price, on_hand,
                           items_group_code, manufacturer, sales_unit
                    FROM produits_sap 
                    WHERE item_code = :code AND valid = true
                    """),
                    {"code": item_code}
                ).fetchone()
                
                if result:
                    return self._format_product_result(result)
                
            except Exception as e:
                logger.error(f"❌ Erreur recherche exacte: {str(e)}")
        
        return None
    
    async def _intelligent_name_search(self, product_name: str) -> List[Dict[str, Any]]:
        """Recherche intelligente guidée par LLM"""
        
        try:
            # Extraction caractéristiques via LLM
            keywords = await self._extract_search_keywords(product_name)
            
            # Construction requête SQL intelligente
            search_query = self._build_intelligent_sql(keywords)
            
            with self.SessionLocal() as session:
                results = session.execute(
                    text(search_query),
                    {"search_term": f"%{product_name.lower()}%", **keywords}
                ).fetchall()
                
                if results:
                    return [self._format_product_result(row) for row in results[:5]]
            
        except Exception as e:
            logger.error(f"❌ Erreur recherche intelligente: {str(e)}")
        
        return []
    
    async def _extract_search_keywords(self, product_name: str) -> Dict[str, str]:
        """Extraction mots-clés via LLM pour recherche optimisée"""
        
        try:
            prompt = f"""
            Extrait les caractéristiques techniques principales de ce produit pour recherche en base:
            Produit: "{product_name}"
            
            Retourne JSON avec:
            - category: type principal (imprimante/ordinateur/écran/autre)
            - tech_keywords: caractéristiques techniques séparées par |
            - brand_hint: marque probable si détectable
            - specs_hint: spécifications numériques si présentes
            
            Exemple: {{"category":"imprimante","tech_keywords":"laser|recto-verso|réseau","brand_hint":"hp","specs_hint":"50 ppm"}}
            """
            
            response = await self.llm_extractor.extract_with_claude(prompt)
            
            if response and "category" in response:
                return {
                    "category": response.get("category", "autre"),
                    "tech_keywords": response.get("tech_keywords", ""),
                    "brand_hint": response.get("brand_hint", ""),
                    "specs_hint": response.get("specs_hint", "")
                }
                
        except Exception as e:
            logger.warning(f"⚠️ LLM extraction échouée: {str(e)}")
        
        # Fallback simple
        return {
            "category": "autre",
            "tech_keywords": product_name.lower(),
            "brand_hint": "",
            "specs_hint": ""
        }
    
    def _build_intelligent_sql(self, keywords: Dict[str, str]) -> str:
        """Construction requête SQL intelligente basée sur les mots-clés LLM"""
        
        base_query = """
        SELECT item_code, item_name, u_description, avg_price, on_hand,
               items_group_code, manufacturer, sales_unit,
               (
                 CASE 
                   WHEN LOWER(item_name) LIKE :search_term THEN 100
                   WHEN LOWER(u_description) LIKE :search_term THEN 80
                   WHEN :tech_keywords != '' AND (
                     LOWER(item_name) LIKE '%' || :tech_keywords || '%' OR
                     LOWER(u_description) LIKE '%' || :tech_keywords || '%'
                   ) THEN 60
                   WHEN :brand_hint != '' AND (
                     LOWER(manufacturer) LIKE '%' || :brand_hint || '%'
                   ) THEN 40
                   ELSE 20
                 END
               ) as relevance_score
        FROM produits_sap 
        WHERE valid = true
          AND (
            LOWER(item_name) LIKE :search_term OR
            LOWER(u_description) LIKE :search_term OR
            (:tech_keywords != '' AND (
              LOWER(item_name) LIKE '%' || :tech_keywords || '%' OR
              LOWER(u_description) LIKE '%' || :tech_keywords || '%'
            )) OR
            (:brand_hint != '' AND LOWER(manufacturer) LIKE '%' || :brand_hint || '%')
          )
        ORDER BY relevance_score DESC, on_hand DESC
        LIMIT 10
        """
        
        return base_query
    
    def _fuzzy_search(self, product_name: str) -> List[Dict[str, Any]]:
        """Recherche fuzzy en dernier recours"""
        
        with self.SessionLocal() as session:
            try:
                # Recherche avec similarity PostgreSQL
                results = session.execute(
                    text("""
                    SELECT item_code, item_name, u_description, avg_price, on_hand,
                           items_group_code, manufacturer, sales_unit,
                           similarity(item_name, :name) as sim_score
                    FROM produits_sap 
                    WHERE valid = true 
                      AND similarity(item_name, :name) > 0.3
                    ORDER BY sim_score DESC, on_hand DESC
                    LIMIT 5
                    """),
                    {"name": product_name}
                ).fetchall()
                
                if results:
                    return [self._format_product_result(row) for row in results]
                    
            except Exception as e:
                logger.error(f"❌ Erreur fuzzy search: {str(e)}")
        
        return []
    
    def _format_product_result(self, row) -> Dict[str, Any]:
        """Formatage résultat compatible avec format SAP existant"""
        
        return {
            "ItemCode": row.item_code,
            "ItemName": row.item_name,
            "U_Description": row.u_description or "",
            "AvgPrice": float(row.avg_price or 0),
            "OnHand": int(row.on_hand or 0),
            "QuantityOnStock": int(row.on_hand or 0),  # Alias pour compatibilité
            "ItemsGroupCode": row.items_group_code or "",
            "Manufacturer": row.manufacturer or "",
            "SalesUnit": row.sales_unit or "UN",
            "source": "local_db"
        }

# Fonction utilitaire pour tests
async def test_local_search():
    """Test du service de recherche locale"""
    service = LocalProductSearchService()
    
    test_searches = [
        "imprimante laser",
        "HP LaserJet",
        "A00025"
    ]
    
    for search in test_searches:
        print(f"\n🔍 Test recherche: {search}")
        result = await service.search_products(search)
        print(f"Résultat: {result['found']} - {len(result['products'])} produits")

if __name__ == "__main__":
    asyncio.run(test_local_search())