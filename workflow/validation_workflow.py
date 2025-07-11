# workflow/validation_workflow.py
import logging
from typing import Dict, List, Any, Optional, Tuple
from services.cache_manager import referential_cache, get_cached_client_or_fetch, get_cached_products_or_fetch

logger = logging.getLogger(__name__)

class SequentialValidator:
    """Validateur séquentiel pour la logique client → produit → quantité"""
    
    def __init__(self, mcp_connector, llm_extractor):
        self.mcp_connector = mcp_connector
        self.llm_extractor = llm_extractor
        
    async def validate_quote_request(self, extracted_info: Dict) -> Dict:
        """
        Point d'entrée principal - Validation séquentielle complète
        
        Retourne :
        - {"status": "ready", "data": {...}} si tout est validé
        - {"status": "user_input_required", "step": "...", "message": "...", "options": [...]} si interaction nécessaire
        - {"status": "error", "message": "..."} en cas d'erreur
        """
        
        logger.info("🔍 Début validation séquentielle")
        
        try:
            # ÉTAPE 1 : Validation Client
            client_validation = await self._validate_client_step(extracted_info.get("client"))
            
            if client_validation["status"] != "validated":
                return client_validation
                
            # ÉTAPE 2 : Validation Produits  
            product_validation = await self._validate_products_step(extracted_info.get("products", []))
            
            if product_validation["status"] != "validated":
                return product_validation
                
            # ÉTAPE 3 : Validation Quantités/Stocks
            quantity_validation = await self._validate_quantities_step(
                product_validation["validated_products"],
                client_validation["validated_client"]
            )
            
            if quantity_validation["status"] != "validated":
                return quantity_validation
            
            # TOUT EST VALIDÉ ✅
            return {
                "status": "ready",
                "data": {
                    "client": client_validation["validated_client"],
                    "products": quantity_validation["validated_products"],
                    "total_estimated": quantity_validation.get("total_estimated", 0),
                    "validation_summary": {
                        "client_source": client_validation.get("source", "unknown"),
                        "products_resolved": len(quantity_validation["validated_products"]),
                        "cache_hits": await self._get_cache_efficiency()
                    }
                }
            }
            
        except Exception as e:
            logger.exception(f"Erreur validation séquentielle: {str(e)}")
            return {
                "status": "error",
                "message": f"Erreur système lors de la validation: {str(e)}"
            }
    
    # ================== ÉTAPE 1: VALIDATION CLIENT ==================
    
    async def _validate_client_step(self, client_name: Optional[str]) -> Dict:
        """
        Étape 1 : Validation du client avec logique séquentielle
        """
        
        if not client_name or not client_name.strip():
            return {
                "status": "user_input_required",
                "step": "client_identification",
                "message": "❌ Je ne trouve pas de nom de client dans votre demande.",
                "question": "Pouvez-vous me préciser le nom de la société ?",
                "input_type": "text",
                "placeholder": "Nom de l'entreprise"
            }
        
        logger.info(f"🔍 Validation client: {client_name}")
        
        # Recherche client (cache puis MCP)
        client_result = await get_cached_client_or_fetch(client_name, self.mcp_connector)
        
        if client_result.get("found"):
            # CLIENT TROUVÉ ✅
            logger.info(f"✅ Client trouvé: {client_name}")
            return {
                "status": "validated",
                "validated_client": client_result["data"],
                "source": client_result.get("source", "unknown"),
                "message": f"✅ Client confirmé : **{client_result['data']['Name']}**"
            }
        
        elif client_result.get("suggestions"):
            # SUGGESTIONS DISPONIBLES 🔍
            suggestions_formatted = []
            for i, suggestion in enumerate(client_result["suggestions"], 1):
                suggestions_formatted.append({
                    "id": suggestion["Id"],
                    "label": f"{i}. {suggestion['Name']} ({suggestion.get('AccountNumber', 'N/A')})",
                    "value": suggestion["Name"],
                    "data": suggestion
                })
            
            return {
                "status": "user_input_required", 
                "step": "client_selection",
                "message": f"❓ Client '**{client_name}**' non trouvé dans notre base.",
                "question": "Voici les clients les plus proches. Voulez-vous utiliser l'un d'eux ?",
                "options": suggestions_formatted + [{
                    "id": "new_client",
                    "label": f"➕ Créer un nouveau client : {client_name}",
                    "value": "new_client",
                    "data": {"name": client_name}
                }],
                "input_type": "selection"
            }
        
        else:
            # AUCUN CLIENT SIMILAIRE - CRÉATION NÉCESSAIRE
            return {
                "status": "user_input_required",
                "step": "client_creation",
                "message": f"❓ Client '**{client_name}**' non trouvé.",
                "question": "Est-ce un nouveau client à créer ?",
                "options": [
                    {
                        "id": "create_yes",
                        "label": "✅ Oui, créer ce nouveau client",
                        "value": "create_client",
                        "data": {"name": client_name}
                    },
                    {
                        "id": "create_no", 
                        "label": "❌ Non, corriger le nom du client",
                        "value": "retry_client",
                        "data": {}
                    }
                ],
                "input_type": "selection"
            }
    
    # ================== ÉTAPE 2: VALIDATION PRODUITS ==================
    
    async def _validate_products_step(self, products_list: List[Dict]) -> Dict:
        """
        Étape 2 : Validation des produits avec résolution intelligente
        """
        
        if not products_list:
            return {
                "status": "user_input_required",
                "step": "product_identification", 
                "message": "❌ Je ne trouve pas de produit dans votre demande.",
                "question": "Pouvez-vous m'aider en précisant le nom du produit ou sa référence ?",
                "input_type": "text",
                "placeholder": "Ex: Imprimante HP LaserJet ou ref A00001"
            }
        
        logger.info(f"🔍 Validation de {len(products_list)} produit(s)")
        
        validated_products = []
        unresolved_products = []
        
        for product in products_list:
            product_code = product.get("code", "").strip()
            quantity = product.get("quantity", 1)
            
            # 1. Recherche exacte par code produit
            exact_product = await referential_cache.get_product_by_code(product_code)
            
            if exact_product:
                # PRODUIT TROUVÉ DIRECTEMENT ✅
                validated_products.append({
                    "product_data": exact_product,
                    "requested_quantity": quantity,
                    "resolution_type": "exact_match"
                })
                logger.info(f"✅ Produit trouvé: {product_code}")
                continue
            
            # 2. Recherche par caractéristiques si pas de code exact
            product_suggestions = await get_cached_products_or_fetch(product_code, self.mcp_connector)
            
            if len(product_suggestions) == 1:
                # UNE SEULE CORRESPONDANCE - VALIDATION AUTOMATIQUE ✅
                validated_products.append({
                    "product_data": product_suggestions[0],
                    "requested_quantity": quantity,
                    "resolution_type": "auto_resolved"
                })
                logger.info(f"✅ Produit auto-résolu: {product_code}")
                
            elif len(product_suggestions) > 1:
                # PLUSIEURS CORRESPONDANCES - INTERACTION UTILISATEUR NÉCESSAIRE 🔍
                unresolved_products.append({
                    "original_request": product_code,
                    "quantity": quantity,
                    "suggestions": product_suggestions
                })
                
            else:
                # AUCUNE CORRESPONDANCE - PRODUIT INTROUVABLE ❌
                unresolved_products.append({
                    "original_request": product_code,
                    "quantity": quantity,
                    "suggestions": [],
                    "error": "not_found"
                })
        
        # Si tous les produits sont résolus
        if not unresolved_products:
            return {
                "status": "validated",
                "validated_products": validated_products,
                "message": f"✅ {len(validated_products)} produit(s) confirmé(s)"
            }
        
        # Si des produits nécessitent une interaction
        return await self._build_product_selection_response(unresolved_products, validated_products)
    
    async def _build_product_selection_response(self, unresolved_products: List[Dict], validated_products: List[Dict]) -> Dict:
        """Construit la réponse pour la sélection de produits"""
        
        first_unresolved = unresolved_products[0]
        
        if first_unresolved.get("error") == "not_found":
            return {
                "status": "user_input_required",
                "step": "product_not_found",
                "message": f"❌ Produit '**{first_unresolved['original_request']}**' introuvable.",
                "question": "Pouvez-vous préciser la référence exacte ou une description plus détaillée ?",
                "input_type": "text",
                "placeholder": "Ex: REF123 ou imprimante laser couleur",
                "context": {
                    "unresolved_products": unresolved_products,
                    "validated_products": validated_products
                }
            }
        
        elif first_unresolved.get("suggestions"):
            # Formater les suggestions
            options = []
            for i, suggestion in enumerate(first_unresolved["suggestions"][:5], 1):
                options.append({
                    "id": suggestion.get("ItemCode", f"option_{i}"),
                    "label": f"{i}. **{suggestion.get('ItemName', 'N/A')}** (Ref: {suggestion.get('ItemCode', 'N/A')}) - {suggestion.get('Price', 'Prix NC')}€",
                    "value": suggestion.get("ItemCode"),
                    "data": suggestion
                })
            
            return {
                "status": "user_input_required",
                "step": "product_selection",
                "message": f"🔍 J'ai trouvé plusieurs produits pour '**{first_unresolved['original_request']}**' (Qté: {first_unresolved['quantity']}).",
                "question": "Veuillez sélectionner le produit souhaité :",
                "options": options,
                "input_type": "selection",
                "context": {
                    "current_product_index": 0,
                    "unresolved_products": unresolved_products,
                    "validated_products": validated_products
                }
            }
    
    # ================== ÉTAPE 3: VALIDATION QUANTITÉS ==================
    
    async def _validate_quantities_step(self, validated_products: List[Dict], client_data: Dict) -> Dict:
        """
        Étape 3 : Validation des quantités et vérification des stocks
        """
        
        logger.info(f"🔍 Validation quantités pour {len(validated_products)} produit(s)")
        
        final_products = []
        warnings = []
        total_estimated = 0.0
        
        for product_item in validated_products:
            product_data = product_item["product_data"]
            requested_qty = product_item["requested_quantity"]
            
            # Vérifications stock et disponibilité
            stock_check = await self._check_product_availability(product_data, requested_qty)
            
            if stock_check["available"]:
                unit_price = float(product_data.get("Price", 0))
                line_total = unit_price * requested_qty
                
                final_products.append({
                    "ItemCode": product_data.get("ItemCode"),
                    "ItemName": product_data.get("ItemName"),
                    "Quantity": requested_qty,
                    "UnitPrice": unit_price,
                    "LineTotal": line_total,
                    "StockLevel": stock_check.get("stock_level", "N/A"),
                    "availability_status": "available"
                })
                
                total_estimated += line_total
                
            else:
                # Stock insuffisant - proposer alternatives ou quantité réduite
                if stock_check.get("available_quantity", 0) > 0:
                    warnings.append(f"⚠️ Stock limité pour {product_data.get('ItemName')}: {stock_check['available_quantity']} disponible(s) sur {requested_qty} demandé(s)")
                else:
                    warnings.append(f"❌ {product_data.get('ItemName')} en rupture de stock")
        
        if warnings:
            return {
                "status": "user_input_required",
                "step": "quantity_adjustment",
                "message": "⚠️ Problèmes de disponibilité détectés :",
                "warnings": warnings,
                "question": "Voulez-vous continuer avec les quantités disponibles ou modifier votre demande ?",
                "options": [
                    {"id": "continue", "label": "✅ Continuer avec les quantités disponibles", "value": "proceed"},
                    {"id": "modify", "label": "✏️ Modifier les quantités", "value": "modify"},
                    {"id": "cancel", "label": "❌ Annuler cette demande", "value": "cancel"}
                ],
                "input_type": "selection",
                "context": {
                    "final_products": final_products,
                    "warnings": warnings
                }
            }
        
        return {
            "status": "validated",
            "validated_products": final_products,
            "total_estimated": total_estimated,
            "message": f"✅ Validation complète : {len(final_products)} produit(s), Total estimé: {total_estimated:.2f}€"
        }
    
    async def _check_product_availability(self, product_data: Dict, requested_qty: int) -> Dict:
        """Vérifie la disponibilité d'un produit"""
        
        try:
            # Appel SAP pour vérifier stock en temps réel
            stock_info = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "get_item_stock",
                {"item_code": product_data.get("ItemCode")}
            )
            
            if stock_info.get("success"):
                available_stock = stock_info.get("data", {}).get("OnHand", 0)
                return {
                    "available": available_stock >= requested_qty,
                    "stock_level": available_stock,
                    "available_quantity": min(available_stock, requested_qty)
                }
            
        except Exception as e:
            logger.warning(f"Erreur vérification stock: {str(e)}")
        
        # Par défaut, considérer comme disponible si impossible de vérifier
        return {
            "available": True,
            "stock_level": "Unknown",
            "available_quantity": requested_qty
        }
    
    # ================== UTILITAIRES ==================
    
    async def _get_cache_efficiency(self) -> Dict:
        """Retourne les statistiques de performance du cache"""
        return referential_cache.get_cache_stats()

# ================== INTÉGRATION DANS LE WORKFLOW PRINCIPAL ==================

async def integrate_sequential_validation(workflow_instance, extracted_info: Dict) -> Dict:
    """
    Fonction d'intégration pour remplacer la validation actuelle
    """
    
    validator = SequentialValidator(workflow_instance.mcp_connector, workflow_instance.llm_extractor)
    
    # Lancer la validation séquentielle
    validation_result = await validator.validate_quote_request(extracted_info)
    
    if validation_result["status"] == "ready":
        # Continuer avec le workflow normal
        workflow_instance.context["client_info"] = {"data": validation_result["data"]["client"], "found": True}
        workflow_instance.context["products_info"] = validation_result["data"]["products"]
        
        return {
            "continue_workflow": True,
            "validation_summary": validation_result["data"]["validation_summary"]
        }
        
    elif validation_result["status"] == "user_input_required":
        # Interrompre pour interaction utilisateur
        return {
            "continue_workflow": False,
            "user_interaction": validation_result
        }
        
    else:
        # Erreur
        return {
            "continue_workflow": False,
            "error": validation_result.get("message", "Erreur de validation")
        }