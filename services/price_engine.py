# services/price_engine.py
import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PriceEngineService:
    def __init__(self):
        self.base_url = os.getenv("SAP_REST_BASE_URL", "https://51.91.130.136:50000/b1s/v1")
        self.login_url = f"{self.base_url}/Login"
        self.price_url = f"{self.base_url}/CompanyService_GetItemPrice"
        self.session_cookie = None
        
    async def authenticate(self):
        """Authentification SAP pour Price Engine"""
        auth_data = {
            "CompanyDB": os.getenv("SAP_CLIENT", "SBODemoFR"),
            "UserName": os.getenv("SAP_USER", "manager"),
            "Password": os.getenv("SAP_CLIENT_PASSWORD", "spirit")
        }
        
        try:
            response = requests.post(
                self.login_url,
                json=auth_data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                verify=False
            )
            response.raise_for_status()
            
            # Récupérer session depuis cookies ET JSON
            session_data = response.json()
            self.session_cookie = session_data.get("SessionId")

            # Stocker aussi les cookies complets pour les requêtes
            self.session_cookies = response.cookies
            logger.info(f"✅ Price Engine authentifié: {self.session_cookie}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur auth Price Engine: {e}")
            return False
    
    async def get_item_price(self, card_code: str, item_code: str, quantity: int, date: str = None) -> Dict[str, Any]:
        """Calcule le prix d'un produit avec remises"""
        if not self.session_cookie:
            if not await self.authenticate():
                return {"error": "Authentification échouée"}
        
        price_params = {
            "ItemPriceParams": {
                "CardCode": card_code,
                "ItemCode": item_code,
                "InventoryQuantity": quantity,
                "Date": date or "2025-07-21"
            }
        }
        
        try:
            response = requests.post(
                self.price_url,
                json=price_params,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Cookie": f"B1SESSION={self.session_cookie}"
                },
                cookies=self.session_cookies,
                verify=False
            )
            response.raise_for_status()
            
            price_data = response.json()
            
            # Calculs selon le PDF
            total_price = price_data.get("Price", 0)
            discount = price_data.get("Discount", 0)
            unit_price_before = total_price / quantity
            unit_price_after = unit_price_before * (1 - discount/100)
            
            return {
                "success": True,
                "total_price": total_price,
                "unit_price_before_discount": unit_price_before,
                "unit_price_after_discount": unit_price_after,
                "discount_percent": discount,
                "currency": price_data.get("Currency", "EUR"),
                "quantity": quantity
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur Price Engine pour {item_code}: {e}")
            return {"error": str(e)}

# Instance globale
price_engine = PriceEngineService()
