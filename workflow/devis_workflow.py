# workflow/devis_workflow.py

import os
import json
import datetime
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from services.llm_extractor import LLMExtractor
from services.mcp_connector import MCPConnector

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
    
    async def _extract_info_basic(self, prompt: str) -> Dict[str, Any]:
        """Méthode d'extraction basique en cas d'échec du LLM"""
        logger.info("Extraction basique des informations du prompt")
        
        # Logique améliorée d'extraction
        extracted = {
            "client": None,
            "products": []
        }
        
        # Recherche du client
        prompt_lower = prompt.lower()
        if "client" in prompt_lower:
            client_index = prompt_lower.find("client")
            if client_index != -1:
                # Extraire tout après "client " jusqu'à la fin ou un séparateur
                client_start = client_index + 7  # "client " = 7 caractères
                client_text = prompt[client_start:].strip()
                
                # Si le client est à la fin de la phrase, prendre tout
                if client_text and not any(sep in client_text for sep in ['.', ',', ';']):
                    extracted["client"] = client_text
                else:
                    # Sinon prendre jusqu'au premier séparateur
                    for sep in ['.', ',', ';']:
                        if sep in client_text:
                            extracted["client"] = client_text.split(sep)[0].strip()
                            break
        
        # Recherche des produits et quantités améliorée
        words = prompt.split()
        for i, word in enumerate(words):
            if word.isdigit() and i + 1 < len(words):
                quantity = int(word)
                
                # Chercher une référence après le nombre
                if i + 2 < len(words) and (words[i+1].lower() in ["ref", "référence", "reference"]):
                    product_code = words[i+2].strip()
                    extracted["products"].append({"code": product_code, "quantity": quantity})
                # Ou directement après un nombre si les mots "produit", "article" sont proches
                elif i > 0 and any(kw in prompt_lower for kw in ["produit", "article", "fourniture"]):
                    # Chercher la référence dans les 3 prochains mots
                    for j in range(1, 4):
                        if i + j < len(words):
                            product_code = words[i+j].strip()
                            # Filtrer les mots courants qui ne sont pas des codes produits
                            if not product_code.lower() in ["de", "pour", "du", "le", "la", "les", "client"]:
                                extracted["products"].append({"code": product_code, "quantity": quantity})
                                break
        
        logger.info(f"Informations extraites en mode basique: {extracted}")
        return extracted


    async def _extract_info_from_prompt(self, prompt: str) -> Dict[str, Any]:
        """Extrait les informations clés du prompt via LLM"""
        try:
            # Tenter extraction via LLM
            extracted_info = await LLMExtractor.extract_quote_info(prompt)
            if "error" in extracted_info:
                # Fallback vers méthode basique
                return await self._extract_info_basic(prompt)
            return extracted_info
        except Exception as e:
            logger.error(f"Erreur extraction LLM: {str(e)}")
            return await self._extract_info_basic(prompt)
    
    async def _validate_client(self, client_name: Optional[str]) -> Dict[str, Any]:
        """Valide l'existence du client dans Salesforce"""
        if not client_name:
            logger.warning("Aucun client spécifié")
            return {"found": False, "error": "Aucun client spécifié"}
        
        logger.info(f"Validation du client: {client_name}")
        
        # AMÉLIORATION: Extraire le nom complet du client de manière plus intelligente
        client_name_original = client_name
        client_name_upper = client_name.upper()
        
        try:
            # Stratégie 1: Tenter avec LIKE d'abord (plus flexible)
            query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 1"
            logger.info(f"Requête SOQL (1/3): {query}")
            result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            # Stratégie 2: Si échec, essayer avec LIKE sur le nom en majuscules
            if "error" not in result and result.get("totalSize", 0) == 0:
                query = f"SELECT Id, Name, AccountNumber FROM Account WHERE UPPER(Name) LIKE '%{client_name_upper}%' LIMIT 1"
                logger.info(f"Requête SOQL (2/3): {query}")
                result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            # Stratégie 3: Si toujours rien, essayer une correspondance exacte
            if "error" not in result and result.get("totalSize", 0) == 0:
                query = f"SELECT Id, Name, AccountNumber FROM Account WHERE Name = '{client_name_original}' LIMIT 1"
                logger.info(f"Requête SOQL (3/3): {query}")
                result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": query})
            
            # Vérification et journalisation du résultat
            logger.info(f"Résultat brut de la requête Salesforce: {json.dumps(result) if isinstance(result, dict) else result}")
            
            if "error" in result:
                logger.error(f"Erreur lors de la requête Salesforce: {result['error']}")
                return {"found": False, "error": result["error"]}
            
            if result.get("totalSize", 0) > 0:
                client_data = result["records"][0]
                logger.info(f"Client trouvé: {client_data['Name']} (ID: {client_data['Id']})")
                return {"found": True, "data": client_data}
            else:
                logger.warning(f"Client non trouvé: {client_name}")
                return {"found": False, "error": f"Client {client_name} non trouvé dans Salesforce"}
        except Exception as e:
            import traceback
            logger.error(f"Erreur lors de la validation du client: {str(e)}\n{traceback.format_exc()}")
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
            # Intégration avec SAP MCP via le connecteur
            try:
                # Appel MCP pour récupérer les détails du produit
                product_details = await MCPConnector.call_sap_mcp("sap_get_product_details", {
                    "item_code": product["code"]
                })
                
                if "error" in product_details:
                    logger.error(f"Erreur lors de la récupération des détails du produit {product['code']}: {product_details['error']}")
                    # Vérifier si malgré l'erreur, nous avons des informations utiles
                    if product_details.get("ItemName") is not None:
                        # Utiliser les données disponibles malgré l'erreur
                        enriched_product = {
                            "code": product["code"],
                            "quantity": product["quantity"],
                            "name": product_details.get("ItemName", "Unknown"),
                            "unit_price": product_details.get("Price", 0.0),
                            "stock": product_details.get("stock", {}).get("total", 0),
                            "details": product_details
                        }
                        enriched_products.append(enriched_product)
                        logger.info(f"Produit partiellement enrichi: {product['code']}")
                    else:
                        # Si vraiment aucune donnée utile, ajouter le produit avec l'erreur
                        enriched_products.append({
                            "code": product["code"],
                            "quantity": product["quantity"],
                            "error": product_details["error"]
                        })
                    continue
                
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
                
                # Rechercher des alternatives via SAP MCP
                try:
                    alternatives_result = await MCPConnector.call_sap_mcp("sap_find_alternatives", {
                        "item_code": product["code"]
                    })
                    
                    if "error" in alternatives_result:
                        logger.error(f"Erreur lors de la recherche d'alternatives pour {product['code']}: {alternatives_result['error']}")
                    elif alternatives_result.get("alternatives"):
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
            # Préparer les données au format attendu par Salesforce
            quote_sf_data = {
                "AccountId": quote_data.get("client", {}).get("id", ""),
                "Status": "Draft" if is_draft else "In Review",
                "ExpirationDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "Description": f"Devis généré automatiquement via NOVA Middleware",
                "LineItems": [
                    {
                        "ProductCode": line.get("product_code", ""),
                        "ProductName": line.get("product_name", ""),
                        "Quantity": line.get("quantity", 0),
                        "UnitPrice": line.get("unit_price", 0)
                    }
                    for line in quote_data.get("quote_lines", [])
                ]
            }
            
            # Dans un environnement réel, appel à Salesforce pour créer le devis
            # result = await MCPConnector.call_salesforce_mcp("salesforce_create_quote", quote_sf_data)
            
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
    async def debug_test(self, prompt: str) -> Dict[str, Any]:
        """Méthode de débogage pour tester le workflow étape par étape"""
        logger.info(f"Débogage du workflow avec prompt: {prompt}")
        
        # Étape 1: Extraction
        extracted_info = await self._extract_info_basic(prompt)
        logger.info(f"Information extraite: {extracted_info}")
        
        # Étape 2: Validation du client
        if extracted_info.get("client"):
            client_info = await self._validate_client(extracted_info.get("client"))
            logger.info(f"Validation du client: {client_info}")
        else:
            logger.warning("Aucun client trouvé dans l'extraction")
        
        # Retourner les résultats de débogage
        return {
            "extraction": extracted_info,
            "client_validation": client_info if 'client_info' in locals() else None
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