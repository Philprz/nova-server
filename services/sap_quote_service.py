"""
Service direct pour récupérer les détails complets des devis SAP
Contourne les serveurs MCP pour un accès direct aux données
"""

import httpx
import os
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SAPQuoteService:
    """Service pour récupérer les détails complets des devis SAP Business One"""
    
    def __init__(self):
        self.base_url = os.getenv("SAP_REST_BASE_URL")
        self.username = os.getenv("SAP_USER")
        self.company_db = os.getenv("SAP_CLIENT")
        self.password = os.getenv("SAP_CLIENT_PASSWORD")
        self.session_id = None
        
    async def login(self) -> bool:
        """Connexion à SAP Business One via API REST"""
        
        try:
            login_data = {
                "CompanyDB": self.company_db,
                "UserName": self.username,
                "Password": self.password
            }
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(
                    f"{self.base_url}/Login",
                    json=login_data,
                    timeout=30.0
                )
            
            if response.status_code == 200:
                result = response.json()
                self.session_id = result.get("SessionId")
                logger.info("Connexion SAP réussie")
                return True
            else:
                logger.error(f"Échec connexion SAP: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur connexion SAP: {str(e)}")
            return False
    
    async def get_quote_details(self, doc_entry: int) -> Dict[str, Any]:
        """
        Récupère les détails complets d'un devis SAP
        
        Args:
            doc_entry: DocEntry du devis SAP
            
        Returns:
            Dict contenant toutes les données du devis pour édition
        """
        
        try:
            # Connexion si nécessaire
            if not self.session_id:
                if not await self.login():
                    return {
                        "success": False,
                        "error": "Impossible de se connecter à SAP"
                    }
            
            # Récupération du devis avec ses lignes
            url = f"{self.base_url}/Quotations({doc_entry})?$expand=DocumentLines"
            
            headers = {
                "Cookie": f"B1SESSION={self.session_id}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(url, headers=headers, timeout=30.0)
            
            if response.status_code == 404:
                return {
                    "success": False,
                    "error": f"Devis {doc_entry} non trouvé dans SAP"
                }
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Erreur SAP {response.status_code}: {response.text}"
                }
            
            quote_data = response.json()
            
            # Récupération des informations client
            customer_data = {}
            if "CardCode" in quote_data:
                customer_data = await self._get_customer_info(quote_data["CardCode"])
            
            # Structure les données pour l'édition
            editable_quote = await self._structure_for_editing(quote_data, customer_data)
            
            return {
                "success": True,
                "quote": editable_quote,
                "raw_data": quote_data,  # Données brutes pour debug
                "metadata": {
                    "retrieved_at": datetime.now().isoformat(),
                    "doc_entry": doc_entry,
                    "lines_count": len(quote_data.get("DocumentLines", []))
                }
            }
            
        except httpx.TimeoutException:
            logger.error(f"Timeout lors de la récupération du devis {doc_entry}")
            return {
                "success": False,
                "error": f"Timeout lors de la récupération du devis {doc_entry}"
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération devis {doc_entry}: {str(e)}")
            return {
                "success": False,
                "error": f"Erreur interne: {str(e)}"
            }
    
    async def _get_customer_info(self, card_code: str) -> Dict[str, Any]:
        """Récupère les informations complètes du client"""
        
        try:
            url = f"{self.base_url}/BusinessPartners('{card_code}')"
            headers = {
                "Cookie": f"B1SESSION={self.session_id}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(url, headers=headers, timeout=15.0)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Client {card_code} non trouvé: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Erreur récupération client {card_code}: {str(e)}")
            return {}
    
    async def _structure_for_editing(self, quote_data: Dict[str, Any], customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Structure les données SAP pour l'interface d'édition"""
        
        # Informations header du devis
        header = {
            "doc_entry": quote_data.get("DocEntry"),
            "doc_num": quote_data.get("DocNum"),
            "doc_date": quote_data.get("DocDate"),
            "doc_due_date": quote_data.get("DocDueDate"),
            "valid_until": quote_data.get("ValidUntil"),
            "card_code": quote_data.get("CardCode"),
            "card_name": quote_data.get("CardName"),
            "comments": quote_data.get("Comments", ""),
            "reference": quote_data.get("NumAtCard", ""),
            "sales_person": quote_data.get("SalesPersonCode"),
            "payment_terms": quote_data.get("PaymentGroupCode"),
            "document_status": quote_data.get("DocumentStatus")
        }
        
        # Informations client détaillées
        customer = {}
        if customer_data:
            customer = {
                "card_code": customer_data.get("CardCode"),
                "card_name": customer_data.get("CardName"),
                "phone": customer_data.get("Phone1"),
                "email": customer_data.get("EmailAddress"),
                "website": customer_data.get("Website"),
                "billing_address": {
                    "street": customer_data.get("BillToState"),
                    "city": customer_data.get("BillToCity"),
                    "zip_code": customer_data.get("BillToZipCode"),
                    "country": customer_data.get("BillToCountry")
                },
                "shipping_address": {
                    "street": customer_data.get("ShipToState"),
                    "city": customer_data.get("ShipToCity"),
                    "zip_code": customer_data.get("ShipToZipCode"),
                    "country": customer_data.get("ShipToCountry")
                }
            }
        
        # Lignes de produits
        lines = []
        for line_data in quote_data.get("DocumentLines", []):
            line = {
                "line_num": line_data.get("LineNum"),
                "item_code": line_data.get("ItemCode"),
                "item_description": line_data.get("ItemDescription"),
                "quantity": line_data.get("Quantity", 1),
                "unit_price": line_data.get("UnitPrice", 0),
                "price_after_vat": line_data.get("PriceAfterVAT", 0),
                "discount_percent": line_data.get("DiscountPercent", 0),
                "line_total": line_data.get("LineTotal", 0),
                "line_total_with_vat": line_data.get("LineTotalSys", 0),
                "tax_code": line_data.get("TaxCode"),
                "tax_percent": line_data.get("TaxPercentagePerRow", 0),
                "warehouse_code": line_data.get("WarehouseCode"),
                "currency": line_data.get("Currency", "EUR"),
                "free_text": line_data.get("FreeText", ""),
                
                # Métadonnées d'édition
                "editable_fields": [
                    "quantity", "unit_price", "discount_percent",
                    "item_description", "warehouse_code", "free_text"
                ],
                "validation": {
                    "min_quantity": 1,
                    "max_quantity": 999999,
                    "min_price": 0.01,
                    "max_discount": 100,
                    "step_quantity": 1,
                    "step_price": 0.01,
                    "step_discount": 0.01
                }
            }
            lines.append(line)
        
        # Totaux
        totals = {
            "subtotal": quote_data.get("DocTotal", 0),
            "total_before_discount": quote_data.get("TotalDiscount", 0),
            "discount_total": quote_data.get("TotalDiscountFC", 0),
            "tax_total": quote_data.get("VatSum", 0),
            "total_with_tax": (quote_data.get("DocTotal", 0) + quote_data.get("VatSum", 0)),
            "currency": quote_data.get("DocCurrency", "EUR"),
            "rounding": quote_data.get("RoundingDiffAmount", 0)
        }
        
        # Structure finale pour l'édition
        editable_structure = {
            "quote_id": f"SAP-{quote_data.get('DocEntry')}",
            "source_system": "SAP Business One",
            "last_updated": quote_data.get("UpdateDate"),
            "editable": True,
            
            "header": header,
            "customer": customer,
            "lines": lines,
            "totals": totals,
            
            # Règles de validation globales
            "validation_rules": {
                "can_modify_header": True,
                "can_modify_lines": True,
                "can_add_lines": True,
                "can_remove_lines": True,
                "can_modify_customer": False,  # Généralement non modifiable
                "required_fields": ["DocDate", "CardCode"],
                "business_rules": {
                    "auto_recalculate_totals": True,
                    "validate_stock_availability": True,
                    "apply_customer_discounts": True
                }
            }
        }
        
        return editable_structure
    
    async def logout(self) -> bool:
        """Déconnexion de SAP Business One"""
        
        if not self.session_id:
            return True
            
        try:
            headers = {
                "Cookie": f"B1SESSION={self.session_id}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(
                    f"{self.base_url}/Logout",
                    headers=headers,
                    timeout=10.0
                )
                
                if response.status_code == 200 or response.status_code == 204:
                    self.session_id = None
                    logger.info("Déconnexion SAP réussie")
                    return True
                else:
                    logger.warning(f"Déconnexion SAP: Code de statut inattendu {response.status_code}")
                    # On réinitialise quand même la session côté client
                    self.session_id = None
                    return False
            
        except Exception as e:
            logger.error(f"Erreur déconnexion SAP: {str(e)}")
            return False


# Instance globale pour réutilisation des sessions
_sap_service = None

async def get_sap_service() -> SAPQuoteService:
    """Factory function pour obtenir le service SAP"""
    global _sap_service
    if _sap_service is None:
        _sap_service = SAPQuoteService()
    return _sap_service