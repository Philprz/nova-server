# workflow/devis_workflow.py

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from services.llm_extractor import LLMExtractor

# Configuration des logs
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/workflow_devis.log'
)
logger = logging.getLogger("workflow_devis")

class DevisWorkflow:
    """Coordinateur du workflow de devis entre Claude, Salesforce et SAP"""
    
    def __init__(self):
        """Initialisation du workflow"""
        self.context = {}
        logger.info("Initialisation du workflow de devis")
    
    async def process_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Traite une demande en langage naturel et orchestre le workflow complet
        
        Args:
            prompt: Demande en langage naturel du commercial
            
        Returns:
            Résultat du workflow avec les étapes et données du devis
        """
        logger.info(f"Traitement de la demande: {prompt}")
        
        # Étape 1: Extraire les informations clés du prompt
        extracted_info = await self._extract_info_from_prompt(prompt)
        self.context["extracted_info"] = extracted_info
        
        # Étape 2: Valider le client dans Salesforce
        client_info = await self._validate_client(extracted_info.get("client"))
        self.context["client_info"] = client_info
        
        # Étape 3: Récupérer les informations produits depuis SAP
        products_info = await self._get_products_info(extracted_info.get("products", []))
        self.context["products_info"] = products_info
        
        # Étape 4: Vérifier la disponibilité des produits
        availability = await self._check_availability(products_info)
        self.context["availability"] = availability
        
        # Étape 5: Calculer le montant total et préparer le devis
        quote_data = await self._prepare_quote_data()
        self.context["quote_data"] = quote_data
        
        # Étape 6: Créer le devis dans Salesforce (ou en brouillon)
        quote_result = await self._create_quote_in_salesforce()
        self.context["quote_result"] = quote_result
        
        # Construire la réponse au commercial
        response = self._build_response()
        
        logger.info(f"Workflow terminé avec succès: {response.get('status')}")
        return response
    
    async def _extract_info_from_prompt(self, prompt: str) -> Dict[str, Any]:
        """Extrait les informations clés de la demande (client, produits, quantités)"""
        logger.info("Extraction des informations du prompt via LLM")
        
        # Utiliser le LLM pour extraire les informations
        extracted = await LLMExtractor.extract_quote_info(prompt)
        
        if "error" in extracted:
            logger.error(f"Erreur lors de l'extraction: {extracted['error']}")
            # Fallback à l'approche basique en cas d'erreur
            return await self._extract_info_basic(prompt)
        
        logger.info(f"Informations extraites par LLM: {extracted}")
        return extracted

    async def _extract_info_basic(self, prompt: str) -> Dict[str, Any]:
        """Méthode d'extraction basique en cas d'échec du LLM"""
        logger.info("Extraction basique des informations du prompt")
        
        # Logique simplifiée d'extraction (celle que nous avions avant)
        extracted = {
            "client": None,
            "products": []
        }
        
        # Recherche du client
        words = prompt.lower().split()
        if "client" in words:
            client_index = words.index("client")
            if client_index + 1 < len(words):
                extracted["client"] = words[client_index + 1].strip().upper()
        
        # Recherche des produits et quantités
        for i, word in enumerate(words):
            if word.isdigit() and i + 2 < len(words) and (words[i+1] == "ref" or words[i+1] == "référence"):
                quantity = int(word)
                product_code = words[i+2].strip()
                extracted["products"].append({"code": product_code, "quantity": quantity})
        
        logger.info(f"Informations extraites en mode basique: {extracted}")
        return extracted
    
    async def _validate_client(self, client_name: Optional[str]) -> Dict[str, Any]:
        """Valide l'existence du client dans Salesforce"""
        if not client_name:
            logger.warning("Aucun client spécifié")
            return {"found": False, "error": "Aucun client spécifié"}
        
        logger.info(f"Validation du client: {client_name}")
        
        # Intégration avec Salesforce MCP
        # Exemple d'appel à la fonction salesforce_query
        try:
            # À remplacer par un vrai appel MCP
            query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 1"
            result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            # Simuler un résultat pour le POC
            result = {
                "totalSize": 1,
                "records": [
                    {"Id": "001XXXXXXXXXXXX", "Name": client_name, "AccountNumber": "ACC-12345"}
                ]
            }
            
            if result["totalSize"] > 0:
                client_data = result["records"][0]
                logger.info(f"Client trouvé: {client_data['Name']}")
                return {"found": True, "data": client_data}
            else:
                logger.warning(f"Client non trouvé: {client_name}")
                return {"found": False, "error": f"Client {client_name} non trouvé dans Salesforce"}
        except Exception as e:
            logger.error(f"Erreur lors de la validation du client: {str(e)}")
            return {"found": False, "error": str(e)}
    
    async def _get_products_info(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Récupère les informations produits depuis SAP"""
        if not products:
            logger.warning("Aucun produit spécifié")
            return []
        
        logger.info(f"Récupération des informations pour {len(products)} produits")
        
        # Enrichir chaque produit avec les données SAP
        enriched_products = []
        
        for product in products:
            # Intégration avec SAP MCP
            # Exemple d'appel à la fonction sap_get_product_details
            try:
                # À remplacer par un vrai appel MCP
                # product_details = await sap_get_product_details(product["code"])
                
                # Simuler un résultat pour le POC
                product_details = {
                    "ItemCode": product["code"],
                    "ItemName": f"Produit {product['code']}",
                    "Price": 100.0,
                    "stock": {
                        "total": 1000,
                        "warehouses": [{"WarehouseCode": "WH01", "QuantityOnStock": 1000}]
                    }
                }
                
                # Enrichir le produit
                enriched_product = {
                    "code": product["code"],
                    "quantity": product["quantity"],
                    "name": product_details.get("ItemName", "Unknown"),
                    "unit_price": product_details.get("Price", 0.0),
                    "stock": product_details.get("stock", {}).get("total", 0),
                    "details": product_details
                }
                
                enriched_products.append(enriched_product)
                logger.info(f"Produit enrichi: {product['code']}")
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des informations pour le produit {product['code']}: {str(e)}")
                enriched_products.append({
                    "code": product["code"],
                    "quantity": product["quantity"],
                    "error": str(e)
                })
        
        return enriched_products
    
    async def _check_availability(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Vérifie la disponibilité des produits"""
        logger.info("Vérification de la disponibilité des produits")
        
        availability_status = {
            "all_available": True,
            "unavailable_products": [],
            "alternatives": {}
        }
        
        for product in products:
            # Vérifier si la quantité demandée est disponible
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
                
                # Rechercher des alternatives
                # Intégration avec SAP MCP
                try:
                    # À remplacer par un vrai appel MCP
                    # alternatives_result = await sap_find_alternatives(product["code"])
                    
                    # Simuler un résultat pour le POC
                    alternatives_result = {
                        "alternatives": [
                            {"ItemCode": f"{product['code']}-ALT1", "ItemName": f"Alternative 1 pour {product['code']}", "Price": 110.0, "Stock": 2000},
                            {"ItemCode": f"{product['code']}-ALT2", "ItemName": f"Alternative 2 pour {product['code']}", "Price": 95.0, "Stock": 1500}
                        ]
                    }
                    
                    if alternatives_result.get("alternatives"):
                        availability_status["alternatives"][product["code"]] = alternatives_result["alternatives"]
                        logger.info(f"Alternatives trouvées pour {product['code']}: {len(alternatives_result['alternatives'])}")
                except Exception as e:
                    logger.error(f"Erreur lors de la recherche d'alternatives pour {product['code']}: {str(e)}")
        
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
                    "line_total": product.get("quantity", 0) * product.get("unit_price", 0)
                }
                quote_lines.append(line)
        
        quote_data = {
            "client": {
                "id": client.get("Id", ""),
                "name": client.get("Name", ""),
                "account_number": client.get("AccountNumber", "")
            },
            "quote_lines": quote_lines,
            "total_amount": total_amount,
            "currency": "EUR",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "status": "Draft"
        }
        
        logger.info(f"Données du devis préparées: {len(quote_lines)} lignes, total: {total_amount} EUR")
        return quote_data
    
    async def _create_quote_in_salesforce(self) -> Dict[str, Any]:
        """Crée le devis dans Salesforce"""
        logger.info("Création du devis dans Salesforce")
        
        quote_data = self.context.get("quote_data", {})
        availability = self.context.get("availability", {})
        
        # Si tous les produits ne sont pas disponibles, créer en mode brouillon
        is_draft = not availability.get("all_available", True)
        
        try:
            # Intégration avec Salesforce MCP
            # Dans un système réel, appel à l'API Salesforce pour créer l'opportunité et le devis
            
            # Simuler un résultat pour le POC
            result = {
                "success": True,
                "quote_id": "Q-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
                "status": "Draft" if is_draft else "Ready",
                "message": "Devis créé avec succès" if not is_draft else "Devis créé en mode brouillon (certains produits indisponibles)"
            }
            
            logger.info(f"Devis créé: {result['quote_id']} - {result['status']}")
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la création du devis: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_response(self) -> Dict[str, Any]:
        """Construit la réponse pour le commercial"""
        logger.info("Construction de la réponse finale")
        
        client_info = self.context.get("client_info", {})
        quote_data = self.context.get("quote_data", {})
        availability = self.context.get("availability", {})
        quote_result = self.context.get("quote_result", {})
        
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
        
        # Construire une réponse détaillée
        response = {
            "status": "success",
            "quote_id": quote_result.get("quote_id", ""),
            "quote_status": quote_result.get("status", ""),
            "client": {
                "name": quote_data.get("client", {}).get("name", ""),
                "account_number": quote_data.get("client", {}).get("account_number", "")
            },
            "products": [
                {
                    "code": line.get("product_code", ""),
                    "name": line.get("product_name", ""),
                    "quantity": line.get("quantity", 0),
                    "unit_price": line.get("unit_price", 0),
                    "line_total": line.get("line_total", 0)
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
        
        logger.info("Réponse finale construite")
        return response