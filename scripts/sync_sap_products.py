# scripts/sync_sap_products.py
# Script de synchronisation produits SAP vers PostgreSQL

import os
import sys
from pathlib import Path

# Ajout répertoire parent au path Python
sys.path.append(str(Path(__file__).parent.parent))
import asyncio
import httpx
import logging
from datetime import datetime
from typing import Dict, List, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
# Import des modèles de données
from models.database_models import ProduitsSAP
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
        """Synchronisation produits vers PostgreSQL (purge + insert batch via ORM)"""
        from models.database_models import ProduitsSAP  # import local pour éviter les cycles

        def to_float(v, default=0.0):
            try:
                return float(v) if v is not None else default
            except (ValueError, TypeError):
                return default

        def to_int(v, default=0):
            try:
                # accepte "12", 12.0, "12.3" (tronqué)
                return int(float(v)) if v is not None else default
            except (ValueError, TypeError):
                return default

        now = datetime.now()
        products = products or []

        with self.SessionLocal() as session:
            try:
                # 1) Vérifier l’existence de la table
                table_check = session.execute(
                    text("SELECT to_regclass('public.produits_sap')")
                ).scalar()
                if table_check is None:
                    raise RuntimeError(
                        "Table produits_sap manquante - exécutez 'alembic upgrade head'"
                    )

                # 2) Purge (DELETE pour compatibilité FK)
                session.execute(text("DELETE FROM produits_sap"))

                # 3) Préparer le batch d’objets ORM
                batch = []
                for p in products:
                    normalized = {
                        "item_code":        (p.get("ItemCode") or "").strip(),
                        "item_name":        (p.get("ItemName") or "").strip(),
                        "u_description":    (p.get("U_Description") or "").strip(),
                        "avg_price":        to_float(p.get("AvgPrice"), 0.0),
                        "on_hand":          to_int(p.get("QuantityOnStock"), 0),
                        "items_group_code": (p.get("ItemsGroupCode") or "").strip(),
                        "manufacturer":     (p.get("Manufacturer") or "").strip(),
                        "bar_code":         (p.get("BarCode") or "").strip(),
                        "valid":            (p.get("Valid") in ("Y", "y", True)),
                        "sales_unit":       (p.get("SalesUnit") or "UN"),
                        "created_at":       now,
                        "updated_at":       now,
                    }
                    batch.append(ProduitsSAP(**normalized))

                # 4) Insertion en une passe
                insert_count = 0
                if batch:
                    session.bulk_save_objects(batch)
                    insert_count = len(batch)

                session.commit()
                logger.info(f"✅ {insert_count} produits synchronisés en base")
                return insert_count

            except Exception as e:
                session.rollback()
                logger.error(f"❌ Erreur sync database: {e}")
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