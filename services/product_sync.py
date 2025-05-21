# services/product_sync.py
import asyncio
import logging
from services.mcp_connector import MCPConnector
from services.salesforce import sf

logger = logging.getLogger("product_sync")

async def sync_product_from_sap_to_salesforce(item_code):
    """
    Synchronise un produit de SAP vers Salesforce
    
    Args:
        item_code: Code du produit SAP à synchroniser
        
    Returns:
        ID du produit dans Salesforce
    """
    try:
        # 1. Récupérer les détails du produit depuis SAP
        product_details = await MCPConnector.call_sap_mcp("sap_get_product_details", {
            "item_code": item_code
        })
        
        if "error" in product_details:
            logger.error(f"Erreur lors de la récupération des détails du produit SAP {item_code}: {product_details['error']}")
            return None
        
        # 2. Vérifier si le produit existe déjà dans Salesforce
        query_result = sf.query(f"SELECT Id FROM Product2 WHERE ProductCode = '{item_code}' LIMIT 1")
        
        if query_result.get("totalSize", 0) > 0:
            # Le produit existe, mettre à jour ses informations
            product_id = query_result["records"][0]["Id"]
            
            # Mise à jour du produit
            sf.Product2.update(product_id, {
                "Name": product_details.get("ItemName", ""),
                "Description": product_details.get("ItemName", ""),
                "ProductCode": item_code,
                "IsActive": True,
                "StockKeepingUnit": item_code
            })
            
            # Mise à jour du prix
            price_result = sf.query(f"SELECT Id FROM PricebookEntry WHERE Product2Id = '{product_id}' AND Pricebook2.IsStandard = TRUE LIMIT 1")
            
            if price_result.get("totalSize", 0) > 0:
                price_entry_id = price_result["records"][0]["Id"]
                sf.PricebookEntry.update(price_entry_id, {
                    "UnitPrice": product_details.get("Price", 0.0)
                })
            else:
                # Créer une entrée de prix si elle n'existe pas
                standard_pricebook_id = '01s0t000000XXXXXXX'  # À remplacer par l'ID réel du catalogue de prix standard
                sf.PricebookEntry.create({
                    "Pricebook2Id": standard_pricebook_id,
                    "Product2Id": product_id,
                    "UnitPrice": product_details.get("Price", 0.0),
                    "IsActive": True
                })
            
            logger.info(f"Produit {item_code} mis à jour dans Salesforce, ID: {product_id}")
            return product_id
        else:
            # Le produit n'existe pas, le créer
            product_data = {
                "Name": product_details.get("ItemName", ""),
                "Description": product_details.get("ItemName", ""),
                "ProductCode": item_code,
                "IsActive": True,
                "StockKeepingUnit": item_code
            }
            
            create_result = sf.Product2.create(product_data)
            product_id = create_result.get("id")
            
            # Créer une entrée de prix pour le nouveau produit
            standard_pricebook_id = '01s0t000000XXXXXXX'  # À remplacer par l'ID réel du catalogue de prix standard
            sf.PricebookEntry.create({
                "Pricebook2Id": standard_pricebook_id,
                "Product2Id": product_id,
                "UnitPrice": product_details.get("Price", 0.0),
                "IsActive": True
            })
            
            logger.info(f"Produit {item_code} créé dans Salesforce, ID: {product_id}")
            return product_id
    
    except Exception as e:
        logger.error(f"Erreur lors de la synchronisation du produit {item_code}: {str(e)}")
        return None