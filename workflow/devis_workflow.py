# workflow/devis_workflow.py - VERSION COMPLÈTE CORRIGÉE

import sys
import io
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Configuration de l'encodage
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Configuration des logs
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/workflow_devis.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)
logger = logging.getLogger('workflow_devis')

from services.llm_extractor import LLMExtractor
from services.mcp_connector import MCPConnector

class DevisWorkflow:
    """Coordinateur du workflow de devis entre Claude, Salesforce et SAP - VERSION PRODUCTION COMPLÈTE"""
    
    def __init__(self):
        self.context = {}
        logger.info("Initialisation du workflow de devis - MODE PRODUCTION COMPLET")
    
    async def process_prompt(self, prompt: str) -> Dict[str, Any]:
        """Traite une demande en langage naturel et orchestre le workflow complet"""
        logger.info(f"=== DÉBUT DU WORKFLOW RÉEL COMPLET ===")
        logger.info(f"Demande: {prompt}")
        
        try:
            # Étape 1: Extraction des informations avec fallback robuste
            extracted_info = await self._extract_info_from_prompt(prompt)
            self.context["extracted_info"] = extracted_info
            logger.info(f"Étape 1 - Extraction: {extracted_info}")
            
            if not extracted_info.get("client") and not extracted_info.get("products"):
                return self._build_error_response("Impossible d'extraire les informations du prompt", "Client ou produits manquants")
            
            # Étape 2: Validation et enrichissement du client Salesforce
            client_info = await self._validate_client(extracted_info.get("client"))
            self.context["client_info"] = client_info
            logger.info(f"Étape 2 - Client Salesforce: {'Trouvé' if client_info.get('found') else 'Non trouvé'}")
            
            if not client_info.get("found"):
                return self._build_error_response("Client non trouvé", client_info.get("error"))
            
            # Étape 3: Récupération et vérification des produits SAP
            products_info = await self._get_products_info(extracted_info.get("products", []))
            self.context["products_info"] = products_info
            logger.info(f"Étape 3 - Produits: {len([p for p in products_info if 'error' not in p])}/{len(products_info)} trouvés")
            
            # Étape 4: Vérification de la disponibilité et alternatives
            availability = await self._check_availability(products_info)
            self.context["availability"] = availability
            
            # Étape 5: Préparation des données du devis
            quote_data = await self._prepare_quote_data()
            self.context["quote_data"] = quote_data
            
            # Étape 6: Création/Vérification du client dans SAP avec TOUTES les données
            sap_client = await self._create_sap_client_if_needed(client_info)
            self.context["sap_client"] = sap_client
            logger.info(f"Étape 6 - Client SAP: {'Créé/Trouvé' if sap_client.get('created') is not None else 'Erreur'}")
            
            # Étape 7: Création RÉELLE du devis dans Salesforce ET SAP
            quote_result = await self._create_quote_in_salesforce()
            self.context["quote_result"] = quote_result
            logger.info(f"Étape 7 - Création devis: {'Succès' if quote_result.get('success') else 'Erreur'}")
            
            # Construire la réponse finale
            response = self._build_response()
            logger.info(f"=== WORKFLOW TERMINÉ ===")
            return response
            
        except Exception as e:
            logger.exception(f"Erreur critique dans le workflow: {str(e)}")
            return self._build_error_response("Erreur système", str(e))
    
    async def _extract_info_from_prompt(self, prompt: str) -> Dict[str, Any]:
        """Extraction des informations avec fallback robuste"""
        try:
            # Tenter extraction via LLM
            extracted_info = await LLMExtractor.extract_quote_info(prompt)
            if "error" not in extracted_info:
                logger.info("Extraction LLM réussie")
                return extracted_info
        except Exception as e:
            logger.warning(f"Échec extraction LLM: {str(e)}")
        
        # Fallback vers extraction manuelle robuste
        return await self._extract_info_basic(prompt)
    
    async def _extract_info_basic(self, prompt: str) -> Dict[str, Any]:
        """Méthode d'extraction basique en cas d'échec du LLM - RESTAURÉE"""
        logger.info("Extraction basique des informations du prompt")
        
        extracted = {"client": None, "products": []}
        prompt_lower = prompt.lower()
        words = prompt.split()
        
        # Recherche du client avec différentes variantes
        client_patterns = ["client", "pour le client", "pour l'entreprise", "pour la société"]
        for pattern in client_patterns:
            if pattern in prompt_lower:
                idx = prompt_lower.find(pattern)
                client_part = prompt[idx + len(pattern):].strip()
                # Nettoyer et extraire le nom du client
                potential_names = client_part.split()[:3]  # Maximum 3 mots
                if potential_names:
                    client_name = " ".join(potential_names).strip(",.;")
                    if len(client_name) > 2:
                        extracted["client"] = client_name
                        break
        
        # Recherche des produits avec quantité - Logique améliorée
        for i, word in enumerate(words):
            if word.isdigit():
                quantity = int(word)
                # Chercher la référence dans les mots suivants
                for j in range(i+1, min(i+5, len(words))):
                    if words[j].lower() in ["ref", "référence", "reference"]:
                        if j+1 < len(words):
                            product_code = words[j+1].strip(",.;")
                            extracted["products"].append({"code": product_code, "quantity": quantity})
                            break
                    # Ou directement après un nombre si les mots "produit", "article" sont proches
                    elif any(kw in prompt_lower for kw in ["produit", "article", "fourniture"]):
                        product_code = words[j].strip(",.;")
                        # Filtrer les mots courants qui ne sont pas des codes produits
                        if not words[j].lower() in ["de", "pour", "du", "le", "la", "les", "client"]:
                            extracted["products"].append({"code": product_code, "quantity": quantity})
                            break
        
        logger.info(f"Extraction basique: {extracted}")
        return extracted
    
    async def _validate_client(self, client_name: Optional[str]) -> Dict[str, Any]:
        """Valide l'existence du client dans Salesforce - AMÉLIORÉE"""
        if not client_name:
            logger.warning("Aucun client spécifié")
            return {"found": False, "error": "Aucun client spécifié"}
        
        logger.info(f"Validation du client: {client_name}")
        
        try:
            # Requête enrichie pour récupérer TOUTES les informations nécessaires
            detailed_query = f"""
            SELECT Id, Name, AccountNumber, 
                   BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry,
                   ShippingStreet, ShippingCity, ShippingState, ShippingPostalCode, ShippingCountry,
                   Phone, Fax, Website, Industry, AnnualRevenue, NumberOfEmployees,
                   Description, Type, OwnerId, CreatedDate, LastModifiedDate
            FROM Account 
            WHERE Name LIKE '%{client_name}%' 
            LIMIT 1
            """
            
            result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": detailed_query})
            
            if "error" in result:
                logger.error(f"Erreur requête Salesforce: {result['error']}")
                return {"found": False, "error": result["error"]}
            
            if result.get("totalSize", 0) > 0:
                client_data = result["records"][0]
                logger.info(f"Client Salesforce trouvé et enrichi: {client_data['Name']} (ID: {client_data['Id']})")
                return {"found": True, "data": client_data}
            else:
                return {"found": False, "error": f"Client '{client_name}' non trouvé dans Salesforce"}
                
        except Exception as e:
            logger.exception(f"Erreur validation client: {str(e)}")
            return {"found": False, "error": str(e)}
    
    async def _get_products_info(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Récupère les informations produits depuis SAP - VERSION CORRIGÉE POUR LES PRIX"""
        if not products:
            logger.warning("Aucun produit spécifié")
            return []
        
        logger.info(f"Récupération des informations pour {len(products)} produits")
        
        enriched_products = []
        
        for product in products:
            try:
                # Appel MCP pour récupérer les détails du produit
                product_details = await MCPConnector.call_sap_mcp("sap_get_product_details", {
                    "item_code": product["code"]
                })
                
                if "error" in product_details:
                    logger.error(f"Erreur produit {product['code']}: {product_details['error']}")
                    # Vérifier si malgré l'erreur, nous avons des informations utiles
                    if product_details.get("ItemName") is not None:
                        enriched_product = {
                            "code": product["code"],
                            "quantity": product["quantity"],
                            "name": product_details.get("ItemName", "Unknown"),
                            "unit_price": float(product_details.get("Price", 0.0)),
                            "stock": product_details.get("stock", {}).get("total", 0),
                            "details": product_details,
                            "salesforce_id": await self._find_product_in_salesforce(product["code"])
                        }
                        enriched_products.append(enriched_product)
                    else:
                        enriched_products.append({
                            "code": product["code"],
                            "quantity": product["quantity"],
                            "error": product_details["error"]
                        })
                    continue
                
                # CORRECTION PRINCIPALE: Récupérer le prix depuis la structure retournée par sap_mcp.py
                unit_price = 0.0
                
                # 1. Le prix est maintenant dans la clé "Price" directement (enrichi par sap_mcp.py)
                if "Price" in product_details:
                    unit_price = float(product_details.get("Price", 0.0))
                    logger.info(f"Prix trouvé via 'Price': {unit_price}")
                
                # 2. Si pas de prix direct, essayer dans price_details (nouveau format)
                elif "price_details" in product_details and product_details["price_details"].get("price"):
                    unit_price = float(product_details["price_details"]["price"])
                    logger.info(f"Prix trouvé via 'price_details': {unit_price}")
                
                # 3. Fallback sur ItemPrices[0].Price (format SAP natif)
                elif "ItemPrices" in product_details and len(product_details["ItemPrices"]) > 0:
                    unit_price = float(product_details["ItemPrices"][0].get("Price", 0.0))
                    logger.info(f"Prix trouvé via 'ItemPrices[0]': {unit_price}")
                
                # 4. Autres fallbacks
                elif "LastPurchasePrice" in product_details:
                    unit_price = float(product_details.get("LastPurchasePrice", 0.0))
                    logger.info(f"Prix trouvé via 'LastPurchasePrice': {unit_price}")
                
                # Si toujours aucun prix trouvé, utiliser une valeur par défaut
                if unit_price == 0.0:
                    logger.warning(f"⚠️ Aucun prix trouvé pour {product['code']}, utilisation d'un prix par défaut")
                    unit_price = 100.0  # Prix par défaut de 100€
                    
                # Enrichir le produit avec ID Salesforce
                salesforce_id = await self._find_product_in_salesforce(product["code"])
                
                # Calculer le stock total depuis la nouvelle structure sap_mcp.py
                total_stock = 0
                if "stock" in product_details and isinstance(product_details["stock"], dict):
                    # Nouvelle structure avec stock.total
                    total_stock = float(product_details["stock"].get("total", 0))
                    logger.info(f"Stock trouvé via 'stock.total': {total_stock}")
                elif "QuantityOnStock" in product_details:
                    # Structure SAP native
                    total_stock = float(product_details.get("QuantityOnStock", 0))
                    logger.info(f"Stock trouvé via 'QuantityOnStock': {total_stock}")
                elif "OnHand" in product_details:
                    # Fallback sur OnHand
                    total_stock = float(product_details.get("OnHand", 0))
                    logger.info(f"Stock trouvé via 'OnHand': {total_stock}")
                
                enriched_product = {
                    "code": product["code"],
                    "quantity": product["quantity"],
                    "name": product_details.get("ItemName", "Unknown"),
                    "unit_price": unit_price,
                    "stock": total_stock,
                    "line_total": product["quantity"] * unit_price,  # CORRECTION: Calculer le total de ligne
                    "details": product_details,
                    "salesforce_id": salesforce_id
                }
                
                enriched_products.append(enriched_product)
                logger.info(f"Produit enrichi: {product['code']} - Prix: {unit_price}€ - Stock: {total_stock}")
                
            except Exception as e:
                logger.error(f"Erreur récupération produit {product['code']}: {str(e)}")
                enriched_products.append({
                    "code": product["code"],
                    "quantity": product["quantity"],
                    "error": str(e)
                })
        
        return enriched_products
    
    async def _find_product_in_salesforce(self, product_code: str) -> Optional[str]:
        """Trouve l'ID Salesforce correspondant au code produit SAP - RESTAURÉE"""
        try:
            query = f"SELECT Id, Name, ProductCode FROM Product2 WHERE ProductCode = '{product_code}' LIMIT 1"
            result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            if "error" not in result and result.get("totalSize", 0) > 0:
                return result["records"][0]["Id"]
            
            logger.info(f"Produit {product_code} non trouvé dans Salesforce")
            return None
            
        except Exception as e:
            logger.warning(f"Erreur recherche produit Salesforce {product_code}: {str(e)}")
            return None
    
    async def _check_availability(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Vérifie la disponibilité des produits"""
        logger.info("Vérification de la disponibilité des produits")
        
        availability_status = {
            "all_available": True,
            "unavailable_products": [],
            "alternatives": {}
        }
        
        for product in products:
            if "error" in product:
                availability_status["all_available"] = False
                availability_status["unavailable_products"].append({
                    "code": product["code"],
                    "reason": "Produit non trouvé",
                    "details": product["error"]
                })
                continue
            
            if product.get("stock", 0) < product.get("quantity", 0):
                logger.warning(f"Produit {product['code']} insuffisant en stock: {product['stock']} < {product['quantity']}")
                availability_status["all_available"] = False
                
                unavailable_item = {
                    "code": product["code"],
                    "name": product.get("name", ""),
                    "quantity_requested": product.get("quantity", 0),
                    "quantity_available": product.get("stock", 0),
                    "reason": "Stock insuffisant"
                }
                availability_status["unavailable_products"].append(unavailable_item)
                
                # Rechercher des alternatives via SAP MCP
                try:
                    alternatives_result = await MCPConnector.call_sap_mcp("sap_find_alternatives", {
                        "item_code": product["code"]
                    })
                    
                    if "error" not in alternatives_result and alternatives_result.get("alternatives"):
                        availability_status["alternatives"][product["code"]] = alternatives_result["alternatives"]
                        logger.info(f"Alternatives trouvées pour {product['code']}: {len(alternatives_result['alternatives'])}")
                        
                except Exception as e:
                    logger.error(f"Erreur recherche alternatives {product['code']}: {str(e)}")
        
        return availability_status
    
    async def _prepare_quote_data(self) -> Dict[str, Any]:
        """Prépare les données du devis"""
        logger.info("Préparation des données du devis")
        
        products = self.context.get("products_info", [])
        client = self.context.get("client_info", {}).get("data", {})
        
        # Calculer le montant total
        total_amount = sum(
            product.get("quantity", 0) * product.get("unit_price", 0)
            for product in products
            if "error" not in product
        )
        
        # Préparer les lignes du devis
        quote_lines = []
        for product in products:
            if "error" not in product:
                line = {
                    "product_code": product["code"],
                    "product_name": product.get("name", ""),
                    "quantity": product.get("quantity", 0),
                    "unit_price": product.get("unit_price", 0),
                    "line_total": product.get("quantity", 0) * product.get("unit_price", 0),
                    "salesforce_id": product.get("salesforce_id")
                }
                quote_lines.append(line)
        
        quote_data = {
            "client": {
                "id": client.get("Id", ""),
                "name": client.get("Name", ""),
                "account_number": client.get("AccountNumber", ""),
                "full_data": client  # Garder toutes les données client
            },
            "quote_lines": quote_lines,
            "total_amount": total_amount,
            "currency": "EUR",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "Draft"
        }
        
        logger.info(f"Données du devis préparées: {len(quote_lines)} lignes, total: {total_amount} EUR")
        return quote_data
    
    async def _create_sap_client_if_needed(self, client_info: Dict[str, Any]) -> Dict[str, Any]:
        """Crée le client dans SAP s'il n'existe pas déjà - AVEC TOUTES LES DONNÉES"""
        logger.info(f"Vérification/création client SAP: {client_info.get('data', {}).get('Name')}")
        
        if not client_info.get('found', False) or not client_info.get('data'):
            return {"created": False, "error": "Données client Salesforce incomplètes"}
        
        sf_client = client_info.get('data', {})
        client_name = sf_client.get('Name')
        client_id = sf_client.get('Id')
        
        try:
            # Vérifier si le client existe dans SAP par nom
            client_search = await MCPConnector.call_sap_mcp("sap_search", {
                "query": client_name,
                "entity_type": "BusinessPartners",
                "limit": 1
            })
            
            if "error" not in client_search and client_search.get("count", 0) > 0:
                # Client trouvé
                sap_client = client_search.get("results", [])[0]
                logger.info(f"Client SAP existant trouvé: {sap_client.get('CardCode')} - {sap_client.get('CardName')}")
                return {"created": False, "data": sap_client}
            
            # Client non trouvé, le créer avec TOUTES les données Salesforce
            logger.info(f"Client non trouvé dans SAP, création avec données complètes...")
            
            # Générer un CardCode unique
            import re
            import time
            
            # Nettoyer le nom pour le CardCode
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', client_name)[:8]
            timestamp = str(int(time.time()))[-4:]
            card_code = f"C{clean_name}{timestamp}".upper()[:15]
            
            # Préparer les données complètes pour SAP
            sap_client_data = {
                "CardCode": card_code,
                "CardName": client_name,
                "CardType": "cCustomer",
                "GroupCode": 100,
                
                # Adresse de facturation
                "BillToStreet": sf_client.get("BillingStreet", "")[:254] if sf_client.get("BillingStreet") else "",
                "BillToCity": sf_client.get("BillingCity", "")[:100] if sf_client.get("BillingCity") else "",
                "BillToState": sf_client.get("BillingState", "")[:100] if sf_client.get("BillingState") else "",
                "BillToZipCode": sf_client.get("BillingPostalCode", "")[:20] if sf_client.get("BillingPostalCode") else "",
                "BillToCountry": sf_client.get("BillingCountry", "")[:3] if sf_client.get("BillingCountry") else "",
                
                # Adresse de livraison
                "ShipToStreet": sf_client.get("ShippingStreet") or sf_client.get("BillingStreet", ""),
                "ShipToCity": sf_client.get("ShippingCity") or sf_client.get("BillingCity", ""),
                "ShipToState": sf_client.get("ShippingState") or sf_client.get("BillingState", ""),
                "ShipToZipCode": sf_client.get("ShippingPostalCode") or sf_client.get("BillingPostalCode", ""),
                "ShipToCountry": sf_client.get("ShippingCountry") or sf_client.get("BillingCountry", ""),
                
                # Informations de contact
                "Phone1": sf_client.get("Phone", "")[:20] if sf_client.get("Phone") else "",
                "Fax": sf_client.get("Fax", "")[:20] if sf_client.get("Fax") else "",
                "Website": sf_client.get("Website", "")[:100] if sf_client.get("Website") else "",
                
                # Informations métier
                "Industry": sf_client.get("Industry", "")[:30] if sf_client.get("Industry") else "",
                "Notes": sf_client.get("Description", "")[:254] if sf_client.get("Description") else "",
                
                # Référence croisée Salesforce
                "FederalTaxID": client_id[:32] if client_id else "",
                
                # Paramètres par défaut
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO"
            }
            
            logger.info(f"Création client SAP avec données: {json.dumps(sap_client_data, indent=2)}")
            
            # Utiliser la nouvelle méthode MCP pour créer le client
            create_result = await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
                "customer_data": sap_client_data
            })
            
            if not create_result.get("success", False):
                logger.error(f"Erreur création client SAP: {create_result.get('error', 'Erreur inconnue')}")
                return {"created": False, "error": create_result.get('error', 'Erreur inconnue')}
            
            logger.info(f"✅ Client SAP créé avec succès: {card_code}")
            return {"created": True, "data": create_result.get("data", {"CardCode": card_code, "CardName": client_name})}
            
        except Exception as e:
            logger.exception(f"Erreur création client SAP: {str(e)}")
            return {"created": False, "error": str(e)}
    
    async def _create_quote_in_salesforce(self) -> Dict[str, Any]:
        """Crée le devis dans Salesforce ET SAP - MÉTHODE COMPLÈTE RESTAURÉE"""
        logger.info("Création du devis dans Salesforce et SAP")
        
        quote_data = self.context.get("quote_data", {})
        availability = self.context.get("availability", {})
        client_info = self.context.get("client_info", {})
        sap_client = self.context.get("sap_client", {})
        products_info = self.context.get("products_info", [])
        
        try:
            # 1. Créer le devis dans SAP si un client SAP est disponible
            sap_quote = None
            if sap_client.get("data") and sap_client["data"].get("CardCode"):
                logger.info("Création du devis dans SAP...")
                
                # Filtrer les produits valides
                valid_products = [p for p in products_info if "error" not in p]
                
                if valid_products:
                    # Préparer les lignes pour SAP
                    document_lines = []
                    for product in valid_products:
                        line = {
                            "ItemCode": product["code"],
                            "Quantity": product["quantity"],
                            "Price": product["unit_price"],
                            "DiscountPercent": 0.0,
                            "TaxCode": "S1"
                        }
                        document_lines.append(line)
                    
                    # Données du devis SAP
                    quotation_data = {
                        "CardCode": sap_client["data"]["CardCode"],
                        "DocDate": datetime.now().strftime("%Y-%m-%d"),
                        "DocDueDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                        "DocCurrency": "EUR",
                        "Comments": f"Devis créé automatiquement via NOVA Middleware le {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                        "SalesPersonCode": -1,
                        "DocumentLines": document_lines
                    }
                    
                    # Créer le devis dans SAP
                    sap_result = await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {
                        "quotation_data": quotation_data
                    })
                    
                    if sap_result.get("success"):
                        sap_quote = sap_result
                        logger.info(f"✅ Devis SAP créé: DocNum {sap_result.get('doc_num')}")
                    else:
                        logger.error(f"❌ Erreur création devis SAP: {sap_result.get('error')}")
            
            # 2. Créer/Synchroniser avec Salesforce (optionnel mais recommandé)
            salesforce_quote = await self._create_salesforce_quote(quote_data, sap_quote)
            
            # Construire la réponse
            success = sap_quote and sap_quote.get("success", False)
            
            result = {
                "success": success,
                "quote_id": f"SAP-{sap_quote.get('doc_num', 'DRAFT')}" if sap_quote else f"DRAFT-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "sap_doc_entry": sap_quote.get("doc_entry") if sap_quote else None,
                "sap_doc_num": sap_quote.get("doc_num") if sap_quote else None,
                "salesforce_quote_id": salesforce_quote.get("id") if salesforce_quote and salesforce_quote.get("success") else None,
                "status": "Created" if success else "Draft",
                "message": f"Devis créé avec succès dans SAP (DocNum: {sap_quote.get('doc_num')})" if success else "Devis en brouillon",
                "sap_result": sap_quote,
                "salesforce_result": salesforce_quote
            }
            
            logger.info(f"Création devis terminée: {result['status']}")
            return result
            
        except Exception as e:
            logger.exception(f"Erreur lors de la création du devis: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    

    async def _create_salesforce_quote(self, quote_data: Dict[str, Any], sap_quote: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Crée RÉELLEMENT le devis dans Salesforce avec tous les détails"""
        try:
            logger.info("=== CRÉATION RÉELLE DU DEVIS DANS SALESFORCE ===")
            
            # Référence SAP si disponible
            sap_ref = f" (SAP DocNum: {sap_quote.get('doc_num')})" if sap_quote and sap_quote.get('doc_num') else ""
            
            # 1. Préparer les données de l'opportunité (devis)
            opportunity_data = {
                'Name': f'NOVA-{datetime.now().strftime("%Y%m%d-%H%M%S")}',
                'AccountId': quote_data.get("client", {}).get("id", ""),
                'StageName': 'Proposal/Price Quote',
                'CloseDate': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'Amount': quote_data.get("total_amount", 0),
                'Description': f'Devis généré automatiquement via NOVA Middleware{sap_ref}',
                'LeadSource': 'NOVA Middleware',
                'Type': 'New Customer',
                'Probability': 50
            }
            
            logger.info(f"Données opportunité préparées: {json.dumps(opportunity_data, indent=2)}")
            
            # 2. Créer l'opportunité
            opportunity_result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                "sobject": "Opportunity",
                "data": opportunity_data
            })
            
            if "error" in opportunity_result or not opportunity_result.get("success"):
                logger.error(f"❌ Erreur création opportunité: {opportunity_result.get('error', 'Erreur inconnue')}")
                return {"success": False, "error": opportunity_result.get("error", "Échec création opportunité")}
            
            opportunity_id = opportunity_result.get("id")
            logger.info(f"✅ Opportunité créée dans Salesforce: {opportunity_id}")
            
            # 3. Récupérer le Pricebook standard
            pricebook_result = await MCPConnector.call_salesforce_mcp("salesforce_get_standard_pricebook", {})
            
            if "error" in pricebook_result or not pricebook_result.get("success"):
                logger.warning("⚠️ Impossible de récupérer le Pricebook standard, utilisation d'un ID par défaut")
                # Tenter de récupérer manuellement
                pricebook_query_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                    "query": "SELECT Id, Name FROM Pricebook2 WHERE IsStandard = TRUE LIMIT 1"
                })
                
                if "error" not in pricebook_query_result and pricebook_query_result.get("totalSize", 0) > 0:
                    pricebook_id = pricebook_query_result["records"][0]["Id"]
                    logger.info(f"Pricebook standard trouvé manuellement: {pricebook_id}")
                else:
                    logger.error("❌ Impossible de trouver le Pricebook standard")
                    return {"success": False, "error": "Pricebook standard non trouvé"}
            else:
                pricebook_id = pricebook_result["pricebook_id"]
                logger.info(f"✅ Pricebook standard récupéré: {pricebook_id}")
            
            # 4. Traiter chaque ligne de devis
            line_items_created = []
            products_created = []
            
            for i, line in enumerate(quote_data.get("quote_lines", [])):
                logger.info(f"--- Traitement ligne {i+1}: {line.get('product_code')} ---")
                
                try:
                    product_id = None
                    pricebook_entry_id = None
                    
                    # 4.1. Vérifier si le produit existe dans Salesforce
                    if line.get("salesforce_id"):
                        product_id = line["salesforce_id"]
                        logger.info(f"Produit existant utilisé: {product_id}")
                    else:
                        # Chercher le produit par code
                        product_search = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                            "query": f"SELECT Id FROM Product2 WHERE ProductCode = '{line.get('product_code')}' LIMIT 1"
                        })
                        
                        if "error" not in product_search and product_search.get("totalSize", 0) > 0:
                            product_id = product_search["records"][0]["Id"]
                            logger.info(f"Produit trouvé par code: {product_id}")
                        else:
                            # 4.2. Créer le produit s'il n'existe pas
                            logger.info(f"Création du produit {line.get('product_code')} dans Salesforce...")
                            
                            product_data = {
                                "Name": line.get("product_name", f"Produit {line.get('product_code')}"),
                                "ProductCode": line.get("product_code"),
                                "Description": f"Produit importé depuis SAP - Code: {line.get('product_code')}",
                                "IsActive": True,
                                "Family": "Hardware"  # Famille par défaut
                            }
                            
                            product_create_result = await MCPConnector.call_salesforce_mcp("salesforce_create_product_complete", {
                                "product_data": product_data,
                                "unit_price": line.get("unit_price", 0)
                            })
                            
                            if product_create_result.get("success"):
                                product_id = product_create_result["product_id"]
                                pricebook_entry_id = product_create_result.get("pricebook_entry_id")
                                products_created.append(product_id)
                                logger.info(f"✅ Produit créé: {product_id}")
                            else:
                                logger.error(f"❌ Échec création produit {line.get('product_code')}: {product_create_result.get('error')}")
                                continue
                    
                    # 4.3. Récupérer l'entrée Pricebook si pas déjà récupérée
                    if not pricebook_entry_id:
                        pricebook_entry_search = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                            "query": f"SELECT Id FROM PricebookEntry WHERE Product2Id = '{product_id}' AND Pricebook2Id = '{pricebook_id}' LIMIT 1"
                        })
                        
                        if "error" not in pricebook_entry_search and pricebook_entry_search.get("totalSize", 0) > 0:
                            pricebook_entry_id = pricebook_entry_search["records"][0]["Id"]
                            logger.info(f"Entrée Pricebook trouvée: {pricebook_entry_id}")
                        else:
                            # Créer l'entrée Pricebook si elle n'existe pas
                            logger.info("Création de l'entrée Pricebook...")
                            
                            pricebook_entry_data = {
                                "Pricebook2Id": pricebook_id,
                                "Product2Id": product_id,
                                "UnitPrice": line.get("unit_price", 0),
                                "IsActive": True
                            }
                            
                            pricebook_entry_result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                                "sobject": "PricebookEntry",
                                "data": pricebook_entry_data
                            })
                            
                            if pricebook_entry_result.get("success"):
                                pricebook_entry_id = pricebook_entry_result["id"]
                                logger.info(f"✅ Entrée Pricebook créée: {pricebook_entry_id}")
                            else:
                                logger.error(f"❌ Échec création entrée Pricebook: {pricebook_entry_result.get('error')}")
                                continue
                    
                    # 4.4. Créer la ligne d'opportunité
                    line_item_data = {
                        "OpportunityId": opportunity_id,
                        "PricebookEntryId": pricebook_entry_id,
                        "Quantity": line.get("quantity", 1),
                        "UnitPrice": line.get("unit_price", 0),
                        "Description": f"Ligne de devis - Ref SAP: {line.get('product_code')}"
                    }
                    
                    logger.info(f"Création ligne opportunité: {json.dumps(line_item_data, indent=2)}")
                    
                    line_result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                        "sobject": "OpportunityLineItem", 
                        "data": line_item_data
                    })
                    
                    if line_result.get("success"):
                        line_item_id = line_result["id"]
                        line_items_created.append({
                            "id": line_item_id,
                            "product_code": line.get("product_code"),
                            "product_id": product_id,
                            "quantity": line.get("quantity"),
                            "unit_price": line.get("unit_price"),
                            "line_total": line.get("line_total")
                        })
                        logger.info(f"✅ Ligne opportunité créée: {line_item_id}")
                    else:
                        logger.error(f"❌ Échec création ligne opportunité: {line_result.get('error')}")
                        
                except Exception as e:
                    logger.exception(f"❌ Erreur lors du traitement de la ligne {i+1}: {str(e)}")
                    continue
            
            # 5. Mettre à jour l'opportunité avec le montant total calculé
            if line_items_created:
                calculated_amount = sum(item["line_total"] for item in line_items_created)
                
                update_data = {
                    "Amount": calculated_amount
                }
                
                update_result = await MCPConnector.call_salesforce_mcp("salesforce_update_record", {
                    "sobject": "Opportunity",
                    "record_id": opportunity_id,
                    "data": update_data
                })
                
                if update_result.get("success"):
                    logger.info(f"✅ Montant opportunité mis à jour: {calculated_amount}")
                else:
                    logger.warning(f"⚠️ Échec mise à jour montant: {update_result.get('error')}")
            
            # 6. Construire la réponse finale
            success_message = f"Devis Salesforce créé avec succès: {len(line_items_created)} lignes sur {len(quote_data.get('quote_lines', []))}"
            if products_created:
                success_message += f", {len(products_created)} produits créés"
            
            result = {
                "success": True,
                "id": opportunity_id,
                "opportunity_id": opportunity_id,
                "lines_created": len(line_items_created),
                "products_created": len(products_created),
                "line_items": line_items_created,
                "created_products": products_created,
                "total_amount": sum(item["line_total"] for item in line_items_created) if line_items_created else 0,
                "message": success_message
            }
            
            logger.info(f"=== DEVIS SALESFORCE CRÉÉ AVEC SUCCÈS ===")
            logger.info(f"Opportunité ID: {opportunity_id}")
            logger.info(f"Lignes créées: {len(line_items_created)}")
            logger.info(f"Produits créés: {len(products_created)}")
            logger.info(f"Montant total: {result['total_amount']}")
            
            return result
            
        except Exception as e:
            logger.exception(f"❌ Erreur critique lors de la création du devis Salesforce: {str(e)}")
            return {
                "success": False, 
                "error": str(e),
                "message": "Erreur lors de la création du devis dans Salesforce"
            }
    
    async def debug_test(self, prompt: str) -> Dict[str, Any]:
        """Méthode de débogage pour tester le workflow étape par étape - RESTAURÉE"""
        logger.info(f"=== MODE DEBUG ===")
        logger.info(f"Débogage du workflow avec prompt: {prompt}")
        
        debug_results = {}
        
        try:
            # Étape 1: Extraction
            extracted_info = await self._extract_info_from_prompt(prompt)
            debug_results["extraction"] = extracted_info
            logger.info(f"DEBUG - Extraction: {extracted_info}")
            
            # Étape 2: Validation du client
            if extracted_info.get("client"):
                client_info = await self._validate_client(extracted_info.get("client"))
                debug_results["client_validation"] = client_info
                logger.info(f"DEBUG - Client: {client_info}")
            else:
                debug_results["client_validation"] = {"found": False, "error": "Aucun client dans l'extraction"}
            
            # Étape 3: Produits
            if extracted_info.get("products"):
                products_info = await self._get_products_info(extracted_info.get("products", []))
                debug_results["products_info"] = products_info
                logger.info(f"DEBUG - Produits: {len(products_info)} produits traités")
            else:
                debug_results["products_info"] = []
                
            # Étape 4: Disponibilité
            if debug_results.get("products_info"):
                availability = await self._check_availability(debug_results["products_info"])
                debug_results["availability"] = availability
                logger.info(f"DEBUG - Disponibilité: {availability}")
            
            debug_results["status"] = "debug_complete"
            return debug_results
            
        except Exception as e:
            logger.exception(f"Erreur lors du débogage: {str(e)}")
            debug_results["error"] = str(e)
            debug_results["status"] = "debug_error"
            return debug_results
    
    def _build_response(self) -> Dict[str, Any]:
        """Construit la réponse finale pour le commercial"""
        logger.info("Construction de la réponse finale")
        
        client_info = self.context.get("client_info", {})
        quote_data = self.context.get("quote_data", {})
        availability = self.context.get("availability", {})
        quote_result = self.context.get("quote_result", {})
        sap_client = self.context.get("sap_client", {})
        
        if not client_info.get("found", False):
            return {
                "status": "error",
                "message": f"Client non trouvé: {client_info.get('error', 'Erreur inconnue')}",
                "next_steps": "Veuillez vérifier le nom du client et réessayer."
            }
        
        if not quote_result.get("success", False):
            return {
                "status": "error",
                "message": f"Échec de la création du devis: {quote_result.get('error', 'Erreur inconnue')}",
                "next_steps": "Veuillez contacter le support technique."
            }
        
        # Construire une réponse détaillée avec toutes les informations
        response = {
            "status": "success",
            "quote_id": quote_result.get("quote_id", ""),
            "sap_doc_entry": quote_result.get("sap_doc_entry"),
            "sap_doc_num": quote_result.get("sap_doc_num"),
            "salesforce_quote_id": quote_result.get("salesforce_quote_id"),
            "quote_status": quote_result.get("status", ""),
            "client": {
                "name": quote_data.get("client", {}).get("name", ""),
                "salesforce_id": quote_data.get("client", {}).get("id", ""),
                "sap_card_code": sap_client.get("data", {}).get("CardCode", "") if sap_client.get("data") else "",
                "account_number": quote_data.get("client", {}).get("account_number", "")
            },
            "products": [
                {
                    "code": line.get("product_code", ""),
                    "name": line.get("product_name", ""),
                    "quantity": line.get("quantity", 0),
                    "unit_price": line.get("unit_price", 0),
                    "line_total": line.get("line_total", 0),
                    "salesforce_id": line.get("salesforce_id")
                }
                for line in quote_data.get("quote_lines", [])
            ],
            "total_amount": quote_data.get("total_amount", 0),
            "currency": quote_data.get("currency", "EUR"),
            "date": quote_data.get("date", ""),
            "message": quote_result.get("message", ""),
            "all_products_available": availability.get("all_available", True)
        }
        
        # Ajouter les informations sur les produits indisponibles
        if not availability.get("all_available", True):
            response["unavailable_products"] = availability.get("unavailable_products", [])
            response["alternatives"] = availability.get("alternatives", {})
            response["next_steps"] = "Veuillez vérifier les produits indisponibles et leurs alternatives proposées."
        
        # Ajouter les références système pour traçabilité
        response["system_references"] = {
            "sap_client_created": sap_client.get("created", False) if sap_client else False,
            "sap_client_card_code": sap_client.get("data", {}).get("CardCode") if sap_client and sap_client.get("data") else None,
            "quote_creation_timestamp": datetime.now().isoformat()
        }
        
        logger.info("Réponse finale construite avec succès")
        return response
    
    def _build_error_response(self, message: str, error_details: str = None) -> Dict[str, Any]:
        """Construit une réponse d'erreur"""
        return {
            "status": "error",
            "message": message,
            "error_details": error_details,
            "timestamp": datetime.now().isoformat(),
            "context": {
                "extracted_info": self.context.get("extracted_info"),
                "client_found": self.context.get("client_info", {}).get("found", False),
                "products_count": len(self.context.get("products_info", []))
            }
        }