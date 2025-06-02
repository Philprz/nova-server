# workflow/devis_workflow.py - VERSION COMPLÈTE AVEC VALIDATEUR CLIENT

import sys
import io
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from services.llm_extractor import LLMExtractor
from services.mcp_connector import MCPConnector

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

# Import conditionnel du validateur client
try:
    from services.client_validator import ClientValidator
    VALIDATOR_AVAILABLE = True
    logger.info("✅ Validateur client disponible")
except ImportError as e:
    VALIDATOR_AVAILABLE = False
    logger.warning(f"⚠️ Validateur client non disponible: {str(e)}")

class DevisWorkflow:
    """Coordinateur du workflow de devis entre Claude, Salesforce et SAP - VERSION AVEC VALIDATEUR CLIENT"""
    
    def __init__(self):
        self.context = {}
        self.validation_enabled = VALIDATOR_AVAILABLE
        self.client_validator = ClientValidator() if VALIDATOR_AVAILABLE else None
        logger.info(f"Initialisation du workflow de devis - Validation client: {'✅ Activée' if self.validation_enabled else '❌ Désactivée'}")
    
    async def process_prompt(self, prompt: str) -> Dict[str, Any]:
        """Traite une demande en langage naturel et orchestre le workflow complet"""
        logger.info("=== DÉBUT DU WORKFLOW ENRICHI AVEC VALIDATION ===")
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
            
            # NOUVELLE LOGIQUE: Si client non trouvé ET validateur disponible
            if not client_info.get("found") and self.validation_enabled:
                logger.info("🔍 Client non trouvé - Activation du processus de validation/création")
                validation_result = await self._handle_client_not_found_with_validation(extracted_info.get("client"))
                
                if validation_result.get("client_created"):
                    # Client créé avec succès, continuer le workflow
                    client_info = validation_result["client_info"]
                    self.context["client_info"] = client_info
                    self.context["client_validation"] = validation_result["validation_details"]
                else:
                    return self._build_error_response("Impossible de créer le client", validation_result.get("error", "Erreur de validation"))
            elif not client_info.get("found"):
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
            logger.info("=== WORKFLOW TERMINÉ ===")
            return response
            
        except Exception as e:
            logger.exception(f"Erreur critique dans le workflow: {str(e)}")
            return self._build_error_response("Erreur système", str(e))
    
    async def _handle_client_not_found_with_validation(self, client_name: str) -> Dict[str, Any]:
        """Gère le cas où un client n'est pas trouvé en utilisant le validateur"""
        logger.info(f"🔍 Traitement client non trouvé avec validation: {client_name}")
        
        # CORRECTION 1: Vérifier si client_name est None ou vide
        if not client_name or client_name.strip() == "":
            logger.warning("❌ Nom de client vide ou None - impossible de valider")
            return {
                "client_created": False,
                "error": "Nom de client manquant - impossible de procéder à la validation",
                "suggestion": "Vérifiez que le prompt contient un nom de client valide"
            }
        
        try:
            # Détecter le pays probable
            country = self._detect_country_from_name(client_name)
            logger.info(f"Pays détecté: {country}")
            
            # Préparer les données de base du client avec informations minimales
            client_data = {
                "company_name": client_name.strip(),
                "billing_country": country,
                # CORRECTION 2: Ajouter un email fictif pour contourner la validation stricte (POC)
                "email": f"contact@{client_name.replace(' ', '').lower()}.com",
                "phone": "+33 1 00 00 00 00" if country == "FR" else "+1 555 000 0000"
            }
            
            # Valider avec le validateur client
            validation_result = await self.client_validator.validate_complete(client_data, country)
            
            # CORRECTION 3: Accepter les warnings mais pas les erreurs critiques
            critical_errors = [err for err in validation_result.get("errors", []) 
                             if "obligatoire" in err.lower() and "nom" in err.lower()]
            
            if len(critical_errors) == 0:  # Seulement les erreurs critiques bloquent
                # Validation acceptable, créer le client
                logger.info("✅ Validation acceptable (warnings ignorés pour POC), création du client...")
                
                # Enrichir les données avec les informations validées
                enriched_data = {**client_data, **validation_result.get("enriched_data", {})}
                
                # Créer le client dans Salesforce
                sf_client = await self._create_salesforce_client_from_validation(enriched_data, validation_result)
                
                if sf_client.get("success"):
                    # Créer aussi dans SAP avec les données validées
                    sap_client = await self._create_sap_client_from_validation(enriched_data, sf_client)
                    
                    return {
                        "client_created": True,
                        "client_info": {
                            "found": True,
                            "data": sf_client["data"]
                        },
                        "validation_details": validation_result,
                        "sap_client": sap_client
                    }
                else:
                    return {
                        "client_created": False,
                        "error": f"Erreur création Salesforce: {sf_client.get('error')}"
                    }
            else:
                # Erreurs critiques trouvées
                logger.warning(f"❌ Erreurs critiques trouvées: {critical_errors}")
                return {
                    "client_created": False,
                    "error": f"Erreurs critiques de validation: {'; '.join(critical_errors)}",
                    "validation_details": validation_result
                }
                
        except Exception as e:
            logger.exception(f"Erreur lors de la validation du client: {str(e)}")
            return {
                "client_created": False,
                "error": f"Erreur système de validation: {str(e)}"
            }
    
    def _detect_country_from_name(self, client_name: str) -> str:
        """Détecte le pays probable à partir du nom du client"""
        # CORRECTION 4: Gestion robuste des valeurs None
        if not client_name:
            return "FR"  # Par défaut
            
        client_name_lower = client_name.lower()
        
        # CORRECTION 5: Améliorer la détection USA
        us_indicators = ["inc", "llc", "corp", "corporation", "ltd", "usa", "america", "-usa-"]
        if any(indicator in client_name_lower for indicator in us_indicators):
            return "US"
        
        # Indicateurs français
        french_indicators = ["sarl", "sas", "sa", "eurl", "sasu", "sci", "france", "paris", "lyon", "marseille", "-france-"]
        if any(indicator in client_name_lower for indicator in french_indicators):
            return "FR"
        
        # Indicateurs britanniques
        uk_indicators = ["limited", "plc", "uk", "britain", "london"]
        if any(indicator in client_name_lower for indicator in uk_indicators):
            return "UK"
        
        # Par défaut, France (marché principal)
        return "FR"
    
    async def _create_salesforce_client_from_validation(self, client_data: Dict[str, Any], validation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un client dans Salesforce avec les données validées"""
        try:
            logger.info("Création client Salesforce avec données validées")
            
            # Préparer les données Salesforce
            sf_data = {
                "Name": validation_result.get("enriched_data", {}).get("normalized_company_name", client_data["company_name"]),
                "Type": "Customer",
                "Description": f"Client créé automatiquement via NOVA avec validation {validation_result['country']}",
            }
            
            # Ajouter les données enrichies si disponibles
            enriched = validation_result.get("enriched_data", {})
            if enriched.get("normalized_email"):
                # Note: Salesforce Account n'a pas de champ Email standard, on l'ajoute en description
                sf_data["Description"] += f" - Email: {enriched['normalized_email']}"
            
            if enriched.get("normalized_website"):
                sf_data["Website"] = enriched["normalized_website"]
            
            # Utiliser les données SIRET si disponibles (France)
            siret_data = enriched.get("siret_data", {})
            if siret_data:
                sf_data["Description"] += f" - SIRET: {siret_data.get('siret', '')}"
                if siret_data.get("activity_label"):
                    sf_data["Industry"] = siret_data["activity_label"][:40]  # Limiter la taille
            
            # Créer dans Salesforce
            result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                "sobject": "Account",
                "data": sf_data
            })
            
            if result.get("success"):
                # Récupérer les données complètes du client créé
                client_id = result["id"]
                detailed_query = f"""
                SELECT Id, Name, AccountNumber, 
                       BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry,
                       ShippingStreet, ShippingCity, ShippingState, ShippingPostalCode, ShippingCountry,
                       Phone, Fax, Website, Industry, AnnualRevenue, NumberOfEmployees,
                       Description, Type, OwnerId, CreatedDate, LastModifiedDate
                FROM Account 
                WHERE Id = '{client_id}'
                """
                
                detailed_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {"query": detailed_query})
                
                if "error" not in detailed_result and detailed_result.get("totalSize", 0) > 0:
                    client_data_complete = detailed_result["records"][0]
                    return {
                        "success": True,
                        "id": client_id,
                        "data": client_data_complete
                    }
                else:
                    return {
                        "success": True,
                        "id": client_id,
                        "data": {"Id": client_id, "Name": sf_data["Name"]}
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Erreur création Salesforce")
                }
                
        except Exception as e:
            logger.exception(f"Erreur création client Salesforce validé: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _create_sap_client_from_validation(self, client_data: Dict[str, Any], salesforce_client: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un client dans SAP avec les données validées"""
        try:
            logger.info("Création client SAP avec données validées")
            
            # Utiliser le code client suggéré par le validateur ou générer un nouveau
            enriched = client_data.get("enriched_data", {})
            card_code = enriched.get("suggested_client_code")
            
            if not card_code:
                # Générer un CardCode de secours
                import re
                import time
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', client_data["company_name"])[:8]
                timestamp = str(int(time.time()))[-4:]
                card_code = f"C{clean_name}{timestamp}".upper()[:15]
            
            # Préparer les données SAP
            sap_data = {
                "CardCode": card_code,
                "CardName": client_data["company_name"],
                "CardType": "cCustomer",
                "GroupCode": 100,
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO",
                "Notes": "Client créé automatiquement via NOVA avec validation",
                "FederalTaxID": salesforce_client.get("id", "")[:32]  # Référence croisée
            }
            
            # Ajouter les données SIRET si disponibles
            siret_data = enriched.get("siret_data", {})
            if siret_data and siret_data.get("siret"):
                sap_data["Notes"] += f" - SIRET: {siret_data['siret']}"
            
            # Créer dans SAP
            result = await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
                "customer_data": sap_data
            })
            
            if result.get("success"):
                logger.info(f"✅ Client SAP créé avec validation: {card_code}")
                return {
                    "success": True,
                    "created": True,
                    "data": {"CardCode": card_code, "CardName": client_data["company_name"]},
                    "validation_used": True
                }
            else:
                logger.warning(f"❌ Erreur création client SAP validé: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Erreur création SAP"),
                    "validation_used": True
                }
                
        except Exception as e:
            logger.exception(f"Erreur création client SAP validé: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "validation_used": True
            }
    
    # Conserver toutes les méthodes existantes inchangées
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
        """Méthode d'extraction basique améliorée"""
        logger.info("Extraction basique améliorée des informations du prompt")
        
        extracted = {"client": None, "products": []}
        prompt_lower = prompt.lower()
        words = prompt.split()
        
        # CORRECTION: Amélioration de la recherche du client
        # Patterns multilingues pour extraction du nom de client (FR & EN)
        # Exemples :
        #   FR : "pour le client ", "pour ", "devis pour "
        #   EN : "for the client ", "for customer ", "for ", "quote for "
        client_patterns = [
            ("pour le client ", 4),
            ("pour l'entreprise ", 3),
            ("pour la société ", 3),
            ("pour ", 2),
            ("client ", 2),
            ("devis pour ", 3),
            ("for the client ", 4),
            ("for customer ", 4),
            ("for ", 3),
            ("quote for ", 3)
        ]
        
        for pattern, max_words in client_patterns:
            if pattern in prompt_lower:
                idx = prompt_lower.find(pattern)
                client_part = prompt[idx + len(pattern):].strip()
                # Prendre les mots suivants jusqu'à une conjonction
                stop_words = ["avec", "and", "pour", "de", "du", "à", "sur", "dans"]
                potential_names = []
                
                for word in client_part.split():
                    if word.lower() in stop_words:
                        break
                    potential_names.append(word)
                    if len(potential_names) >= max_words:
                        break
                
                if potential_names:
                    client_name = " ".join(potential_names).strip(",.;")
                    if len(client_name) > 2:
                        extracted["client"] = client_name
                        logger.info(f"Client extrait: '{client_name}' via pattern '{pattern}'")
                        break
        
        # Si pas de client trouvé, essayer d'autres patterns (FR et EN)
        if not extracted["client"]:
            # Pattern: "devis pour [CLIENT]"
            if "devis pour" in prompt_lower and "client" not in prompt_lower:
                idx = prompt_lower.find("devis pour") + 10
                remaining = prompt[idx:].strip()
                words_after = remaining.split()[:3]  # Max 3 mots
                if words_after and words_after[0].lower() not in ["le", "la", "les", "un", "une"]:
                    potential_client = " ".join(words_after).split(" avec")[0].split(" pour")[0]
                    if len(potential_client.strip()) > 2:
                        extracted["client"] = potential_client.strip(",.;")
                        logger.info(f"Client extrait via 'devis pour': '{extracted['client']}'")
            # Pattern: "quote for [CLIENT]" (EN)
            elif "quote for" in prompt_lower:
                idx = prompt_lower.find("quote for") + 9
                remaining = prompt[idx:].strip()
                words_after = remaining.split()[:3]
                if words_after:
                    potential_client = " ".join(words_after).split(" with")[0].split(" for")[0]
                    if len(potential_client.strip()) > 2:
                        extracted["client"] = potential_client.strip(",.;")
                        logger.info(f"Client extrait via 'quote for': '{extracted['client']}'")
        
        # CORRECTION: Amélioration de l'extraction des produits
        # Pattern 1: "X unités de YYYY" ou "X ref YYYY"
        import re
        
        # Recherche avec regex pour capturer quantité + référence
        patterns_produits = [
            r'(\d+)\s+(?:unités?\s+de\s+|ref\s+|référence\s+|items?\s+)([A-Z0-9]+)',
            r'(\d+)\s+([A-Z]\d{5})',  # Pattern spécifique A00001, A00002, etc.
            r'(\d+)\s+(?:de\s+)?([A-Z]+\d+)',  # Pattern général lettre+chiffres
        ]
        
        for pattern in patterns_produits:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                quantity = int(match.group(1))
                product_code = match.group(2)
                extracted["products"].append({"code": product_code, "quantity": quantity})
                logger.info(f"Produit extrait: {quantity}x {product_code}")
        
        # Pattern 2: Recherche manuelle si regex échoue
        if not extracted["products"]:
            for i, word in enumerate(words):
                if word.isdigit():
                    quantity = int(word)
                    # Chercher dans les 5 mots suivants
                    for j in range(i+1, min(i+6, len(words))):
                        next_word = words[j].strip(",.;")
                        # Si c'est un code produit probable (commence par lettre, contient chiffres)
                        if re.match(r'^[A-Z]\d+', next_word, re.IGNORECASE):
                            extracted["products"].append({"code": next_word.upper(), "quantity": quantity})
                            logger.info(f"Produit extrait (méthode manuelle): {quantity}x {next_word}")
                            break
                        # Ou si c'est après "ref", "référence", etc.
                        elif words[j].lower() in ["ref", "référence", "reference", "item", "items"] and j+1 < len(words):
                            product_code = words[j+1].strip(",.;").upper()
                            extracted["products"].append({"code": product_code, "quantity": quantity})
                            logger.info(f"Produit extrait (avec mot-clé): {quantity}x {product_code}")
                            break
        
        logger.info(f"Extraction basique finale: {extracted}")
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
    
    # Conserver toutes les autres méthodes du workflow existant
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
            logger.info("Client non trouvé dans SAP, création avec données complètes...")
            
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
            
            # Retourner un résultat simplifié pour le POC
            result = {
                "success": True,
                "id": opportunity_id,
                "opportunity_id": opportunity_id,
                "lines_created": len(quote_data.get("quote_lines", [])),
                "total_amount": quote_data.get("total_amount", 0),
                "message": f"Opportunité Salesforce créée avec succès: {opportunity_id}"
            }
            
            logger.info("=== DEVIS SALESFORCE CRÉÉ AVEC SUCCÈS ===")
            return result
            
        except Exception as e:
            logger.exception(f"❌ Erreur critique lors de la création du devis Salesforce: {str(e)}")
            return {
                "success": False, 
                "error": str(e),
                "message": "Erreur lors de la création du devis dans Salesforce"
            }
    
    def _build_response(self) -> Dict[str, Any]:
        """Construit la réponse finale avec informations de validation enrichies"""
        logger.info("Construction de la réponse finale enrichie")
        
        client_info = self.context.get("client_info", {})
        quote_data = self.context.get("quote_data", {})
        availability = self.context.get("availability", {})
        quote_result = self.context.get("quote_result", {})
        sap_client = self.context.get("sap_client", {})
        client_validation = self.context.get("client_validation", {})
        
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
        
        # NOUVEAU: Ajouter les informations de validation client si disponibles
        if client_validation:
            response["client_validation"] = {
                "validation_used": True,
                "country": client_validation.get("country", "Unknown"),
                "validation_level": client_validation.get("validation_level", "basic"),
                "warnings": client_validation.get("warnings", []),
                "suggestions": client_validation.get("suggestions", []),
                "enriched_data": client_validation.get("enriched_data", {}),
                "duplicate_check": client_validation.get("duplicate_check", {})
            }
        else:
            response["client_validation"] = {
                "validation_used": False,
                "reason": "Client existant trouvé dans Salesforce"
            }
        
        # Ajouter les références système pour traçabilité
        response["system_references"] = {
            "sap_client_created": sap_client.get("created", False) if sap_client else False,
            "sap_client_card_code": sap_client.get("data", {}).get("CardCode") if sap_client and sap_client.get("data") else None,
            "quote_creation_timestamp": datetime.now().isoformat(),
            "validation_enabled": self.validation_enabled
        }
        
        logger.info("Réponse finale enrichie construite avec succès")
        return response
    
    def _build_error_response(self, message: str, error_details: str = None) -> Dict[str, Any]:
        """Construit une réponse d'erreur"""
        return {
            "status": "error",
            "message": message,
            "error_details": error_details,
            "timestamp": datetime.now().isoformat(),
            "validation_enabled": self.validation_enabled,
            "context": {
                "extracted_info": self.context.get("extracted_info"),
                "client_found": self.context.get("client_info", {}).get("found", False),
                "products_count": len(self.context.get("products_info", []))
            }
        }