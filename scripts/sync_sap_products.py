# scripts/sync_sap_products.py
# Script de synchronisation produits SAP vers PostgreSQL

import os
import sys
import asyncio
import httpx
import logging
from datetime import datetime
from typing import Dict, List, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sap_sync.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('sap_sync')

# Chargement configuration
load_dotenv()

class SAPProductSyncer:
    """Synchroniseur produits SAP vers PostgreSQL"""
    
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.sap_url = os.getenv("SAP_REST_BASE_URL")
        self.sap_user = os.getenv("SAP_USER")
        self.sap_password = os.getenv("SAP_CLIENT_PASSWORD")
        self.sap_client = os.getenv("SAP_CLIENT")
        
        # Configuration SAP session
        self.session_id = None
        self.http_client = httpx.AsyncClient(timeout=30.0, verify=False, http2=False)
        
        # Configuration PostgreSQL
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    async def sap_login(self) -> bool:
        """Authentification SAP Business One"""
        try:
            login_data = {
                "UserName": self.sap_user,
                "Password": self.sap_password,
                "CompanyDB": self.sap_client
            }
            
            response = await self.http_client.post(
                f"{self.sap_url}/Login",
                json=login_data
            )
            
            if response.status_code == 200:
                self.session_id = response.json().get("SessionId")
                logger.info("✅ Connexion SAP établie")
                return True
            
            logger.error(f"❌ Échec login SAP: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Erreur login SAP: {str(e)}")
            return False
    
    async def fetch_all_products(self, limit: int = 10000) -> List[Dict[str, Any]]:
        """Récupération complète des produits SAP"""
        
        if not await self.sap_login():
            raise Exception("Impossible de se connecter à SAP")
        
        all_products = []
        skip = 0
        batch_size = 100
        
        try:
            while skip < limit:
                logger.info(f"🔄 Récupération produits {skip}-{skip+batch_size}")
                
                response = await self.http_client.get(
                    f"{self.sap_url}/Items",
                    params={
                        "$skip": skip,
                        "$top": batch_size,
                        "$filter": "Valid eq 'Y'"
                    },
                    headers={"Cookie": f"B1SESSION={self.session_id}"}
                )
                
                if response.status_code != 200:
                    logger.error(f"❌ Erreur récupération: {response.status_code}")
                    break
                
                data = response.json()
                products_batch = data.get("value", [])
                
                if not products_batch:
                    logger.info("✅ Fin de récupération - pas d'autres produits")
                    break
                
                # Récupération des prix pour chaque produit
                for product in products_batch:
                    price = await self._get_product_price(product["ItemCode"])
                    product["AvgPrice"] = price
                
                all_products.extend(products_batch)
                skip += batch_size
                
                # Pause pour éviter surcharge SAP
                await asyncio.sleep(0.1)
        
        except Exception as e:
            logger.error(f"❌ Erreur fetch_all_products: {str(e)}")
            raise
        
        logger.info(f"✅ {len(all_products)} produits récupérés depuis SAP")
        return all_products
    
    async def _get_product_price(self, item_code: str) -> float:
        """Récupération prix produit via API SAP"""
        try:
            response = await self.http_client.get(
                f"{self.sap_url}/Items('{item_code}')/ItemPrices",
                headers={"Cookie": f"B1SESSION={self.session_id}"}
            )
            
            if response.status_code == 200:
                prices = response.json().get("value", [])
                if prices:
                    return float(prices[0].get("Price", 0))
            
        except Exception as e:
            logger.warning(f"⚠️ Prix non récupéré pour {item_code}: {str(e)}")
        
        return 0.0
    
    def sync_products_to_database(self, products: List[Dict[str, Any]]) -> int:
        """Synchronisation produits vers PostgreSQL"""
        
        with self.SessionLocal() as session:
            try:
                # Truncate et réinsertion complète pour éviter doublons
                session.execute(text("TRUNCATE TABLE produits_sap RESTART IDENTITY"))
                
                insert_count = 0
                for product in products:
                    # Normalisation données
                    normalized_product = {
                        'item_code': product.get('ItemCode', ''),
                        'item_name': product.get('ItemName', ''),
                        'u_description': product.get('U_Description', ''),
                        'avg_price': float(product.get('AvgPrice', 0)),
                        'on_hand': int(product.get('QuantityOnStock', 0)),
                        'items_group_code': product.get('ItemsGroupCode', ''),
                        'manufacturer': product.get('Manufacturer', ''),
                        'bar_code': product.get('BarCode', ''),
                        'valid': product.get('Valid') == 'Y',
                        'sales_unit': product.get('SalesUnit', 'UN')
                    }
                    
                    # Insertion
                    session.execute(
                        text("""
                        INSERT INTO produits_sap (
                            item_code, item_name, u_description, avg_price, on_hand,
                            items_group_code, manufacturer, bar_code, valid, sales_unit
                        ) VALUES (
                            :item_code, :item_name, :u_description, :avg_price, :on_hand,
                            :items_group_code, :manufacturer, :bar_code, :valid, :sales_unit
                        )
                        """),
                        normalized_product
                    )
                    insert_count += 1
                
                session.commit()
                logger.info(f"✅ {insert_count} produits synchronisés en base")
                return insert_count
                
            except Exception as e:
                session.rollback()
                logger.error(f"❌ Erreur sync database: {str(e)}")
                raise
    
    async def run_full_sync(self):
        """Synchronisation complète SAP -> PostgreSQL"""
        start_time = datetime.now()
        logger.info("🚀 Début synchronisation produits SAP")
        
        try:
            # Récupération depuis SAP
            products = await self.fetch_all_products()
            
            # Synchronisation vers PostgreSQL
            count = self.sync_products_to_database(products)
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"🎉 Synchronisation terminée: {count} produits en {duration:.1f}s")
            
            return {"success": True, "products_synced": count, "duration_seconds": duration}
            
        except Exception as e:
            logger.error(f"❌ Échec synchronisation: {str(e)}")
            return {"success": False, "error": str(e)}
        
        finally:
            await self.http_client.aclose()

if __name__ == "__main__":
    syncer = SAPProductSyncer()
    result = asyncio.run(syncer.run_full_sync())
    print(f"Résultat: {result}")