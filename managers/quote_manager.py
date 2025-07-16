# managers/quote_manager.py
"""
QuoteManager - Orchestrateur principal des devis
Version simplifiée et optimisée du DevisWorkflow
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

from managers.client_manager import ClientManager
from managers.product_manager import ProductManager
from services.llm_extractor import LLMExtractor
from services.progress_tracker import progress_tracker, QuoteTask
from utils.common_utils import ResponseBuilder, ErrorHandler
from models.data_models import QuoteData, ClientData, ProductData

logger = logging.getLogger(__name__)

class QuoteManager:
    """Orchestrateur principal pour la génération de devis"""
    
    def __init__(self, draft_mode: bool = False):
        self.client_manager = ClientManager()
        self.product_manager = ProductManager()
        self.llm_extractor = LLMExtractor()
        self.response_builder = ResponseBuilder()
        self.error_handler = ErrorHandler()
        self.draft_mode = draft_mode
        
        # Tracking des tâches
        self.current_task: Optional[QuoteTask] = None
        self.task_id: Optional[str] = None
    
    async def generate_quote(self, user_prompt: str, task_id: str = None) -> Dict[str, Any]:
        """
        Génération de devis principale - Version simplifiée
        
        Args:
            user_prompt: Demande utilisateur en langage naturel
            task_id: ID de tâche existant (optionnel)
            
        Returns:
            Dict avec le devis généré ou les erreurs
        """
        try:
            logger.info(f"🚀 Génération devis (draft: {self.draft_mode})")
            
            # Initialisation du tracking
            self.task_id = task_id or self._initialize_task_tracking(user_prompt)
            
            # ========== PHASE 1: EXTRACTION ==========
            self._track_step_start("extraction", "Analyse de votre demande...")
            
            extracted_info = await self.llm_extractor.extract_quote_info(user_prompt)
            
            if "error" in extracted_info:
                self._track_step_fail("extraction", extracted_info["error"])
                return self.error_handler.handle_extraction_error(extracted_info["error"])
            
            self._track_step_complete("extraction", "Demande analysée")
            
            # ========== PHASE 2: RECHERCHE PARALLÈLE ==========
            self._track_step_start("parallel_search", "Recherche client et produits...")
            
            # Extraction des informations
            client_name = extracted_info.get("client", "")
            product_codes = [p.get("code") for p in extracted_info.get("products", [])]
            
            if not client_name or not product_codes:
                return self.error_handler.handle_missing_info_error(client_name, product_codes)
            
            # Recherche parallèle client + produits
            client_task = self.client_manager.find_client(client_name)
            products_task = self.product_manager.find_products(product_codes)
            
            client_result, products_result = await asyncio.gather(
                client_task, products_task, return_exceptions=True
            )
            
            # Gestion des erreurs
            if isinstance(client_result, Exception):
                self._track_step_fail("parallel_search", f"Erreur client: {client_result}")
                return self.error_handler.handle_client_error(str(client_result))
            
            if isinstance(products_result, Exception):
                self._track_step_fail("parallel_search", f"Erreur produits: {products_result}")
                return self.error_handler.handle_products_error(str(products_result))
            
            self._track_step_complete("parallel_search", "Recherche terminée")
            
            # ========== PHASE 3: VALIDATION ==========
            self._track_step_start("validation", "Validation des données...")
            
            # Validation client
            if not client_result.get("found"):
                if client_result.get("suggestions"):
                    return self._handle_client_suggestions(client_result, extracted_info)
                else:
                    return self.error_handler.handle_client_not_found(client_name)
            
            # Validation produits
            products_not_found = [p for p in products_result if not p.get("found")]
            if products_not_found:
                return self._handle_products_not_found(products_not_found, products_result)
            
            # Validation stock
            stock_validation = await self.product_manager.validate_stock(products_result)
            if not stock_validation["all_available"]:
                return self._handle_stock_issues(stock_validation)
            
            self._track_step_complete("validation", "Données validées")
            
            # ========== PHASE 4: GÉNÉRATION ==========
            self._track_step_start("generation", "Génération du devis...")
            
            # Préparation des données
            quote_data = self._prepare_quote_data(
                client_result["data"], 
                products_result, 
                extracted_info
            )
            
            # Génération selon le mode
            if self.draft_mode:
                result = await self._generate_draft_quote(quote_data)
            else:
                result = await self._generate_final_quote(quote_data)
            
            self._track_step_complete("generation", "Devis généré")
            
            # Terminer la tâche
            if self.current_task:
                progress_tracker.complete_task(self.task_id, result)
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur génération devis: {str(e)}")
            if self.current_task:
                progress_tracker.fail_task(self.task_id, str(e))
            return self.error_handler.handle_generation_error(str(e))
    
    async def _generate_draft_quote(self, quote_data: QuoteData) -> Dict[str, Any]:
        """Génération d'un devis en mode draft (prévisualisation)"""
        try:
            logger.info("📝 Génération devis DRAFT")
            
            # Calculs
            total_amount = sum(p.price * p.quantity for p in quote_data.products)
            
            return self.response_builder.build_success_response({
                "mode": "draft",
                "quote_data": {
                    "client": quote_data.client.to_dict(),
                    "products": [p.to_dict() for p in quote_data.products],
                    "total_amount": total_amount,
                    "currency": "EUR",
                    "created_at": datetime.now().isoformat()
                },
                "actions": [
                    {"action": "confirm_quote", "label": "Confirmer le devis"},
                    {"action": "modify_quote", "label": "Modifier le devis"},
                    {"action": "cancel_quote", "label": "Annuler"}
                ]
            })
            
        except Exception as e:
            logger.exception(f"Erreur génération draft: {str(e)}")
            return self.error_handler.handle_draft_error(str(e))
    
    async def _generate_final_quote(self, quote_data: QuoteData) -> Dict[str, Any]:
        """Génération d'un devis final dans SAP/Salesforce"""
        try:
            logger.info("📄 Génération devis FINAL")
            
            # Génération parallèle SAP + Salesforce
            sap_task = self._create_sap_quote(quote_data)
            sf_task = self._create_salesforce_opportunity(quote_data)
            
            sap_result, sf_result = await asyncio.gather(
                sap_task, sf_task, return_exceptions=True
            )
            
            # Traitement des résultats
            success_count = 0
            results = {"sap": None, "salesforce": None}
            
            if not isinstance(sap_result, Exception) and sap_result.get("success"):
                results["sap"] = sap_result
                success_count += 1
            
            if not isinstance(sf_result, Exception) and sf_result.get("success"):
                results["salesforce"] = sf_result
                success_count += 1
            
            # Évaluation du succès
            if success_count == 2:
                status = "complete_success"
                message = "Devis créé avec succès dans SAP et Salesforce"
            elif success_count == 1:
                status = "partial_success"
                message = "Devis créé partiellement"
            else:
                status = "failure"
                message = "Échec de création du devis"
            
            return self.response_builder.build_success_response({
                "mode": "final",
                "status": status,
                "message": message,
                "quote_data": quote_data.to_dict(),
                "results": results,
                "sap_quote_number": results["sap"].get("quote_number") if results["sap"] else None,
                "salesforce_opportunity_id": results["salesforce"].get("opportunity_id") if results["salesforce"] else None
            })
            
        except Exception as e:
            logger.exception(f"Erreur génération final: {str(e)}")
            return self.error_handler.handle_final_error(str(e))
    
    async def _create_sap_quote(self, quote_data: QuoteData) -> Dict[str, Any]:
        """Création du devis dans SAP"""
        try:
            from services.mcp_connector import MCPConnector
            
            # Préparation des données SAP
            sap_quote_data = {
                "CardCode": quote_data.client.sap_code,
                "CardName": quote_data.client.name,
                "DocDate": datetime.now().strftime("%Y-%m-%d"),
                "DocDueDate": datetime.now().strftime("%Y-%m-%d"),
                "DocumentLines": [
                    {
                        "ItemCode": product.code,
                        "Quantity": product.quantity,
                        "UnitPrice": product.price,
                        "LineTotal": product.price * product.quantity
                    }
                    for product in quote_data.products
                ]
            }
            
            result = await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {
                "quotation_data": sap_quote_data
            })
            
            if "error" not in result:
                return {
                    "success": True,
                    "quote_number": result.get("DocNum"),
                    "doc_entry": result.get("DocEntry"),
                    "system": "sap"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                    "system": "sap"
                }
                
        except Exception as e:
            logger.exception(f"Erreur création SAP: {str(e)}")
            return {"success": False, "error": str(e), "system": "sap"}
    
    async def _create_salesforce_opportunity(self, quote_data: QuoteData) -> Dict[str, Any]:
        """Création de l'opportunité dans Salesforce"""
        try:
            from services.mcp_connector import MCPConnector
            
            # Préparation des données Salesforce
            sf_opportunity_data = {
                "Name": f"Devis {quote_data.client.name} - {datetime.now().strftime('%Y-%m-%d')}",
                "AccountId": quote_data.client.salesforce_id,
                "CloseDate": datetime.now().strftime("%Y-%m-%d"),
                "StageName": "Quotation",
                "Amount": quote_data.total_amount,
                "Description": f"Devis généré automatiquement par NOVA"
            }
            
            result = await MCPConnector.call_salesforce_mcp("salesforce_create_opportunity_complete", {
                "opportunity_data": sf_opportunity_data,
                "line_items": [
                    {
                        "Product2Id": product.salesforce_id,
                        "Quantity": product.quantity,
                        "UnitPrice": product.price
                    }
                    for product in quote_data.products
                ]
            })
            
            if "error" not in result:
                return {
                    "success": True,
                    "opportunity_id": result.get("Id"),
                    "system": "salesforce"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error"),
                    "system": "salesforce"
                }
                
        except Exception as e:
            logger.exception(f"Erreur création Salesforce: {str(e)}")
            return {"success": False, "error": str(e), "system": "salesforce"}
    
    def _prepare_quote_data(self, client_data: Dict[str, Any], 
                          products_data: List[Dict[str, Any]], 
                          extracted_info: Dict[str, Any]) -> QuoteData:
        """Préparation des données de devis"""
        
        # Conversion client
        client = ClientData(
            name=client_data.get("Name", ""),
            email=client_data.get("Email", ""),
            phone=client_data.get("Phone", ""),
            address=client_data.get("BillingStreet", ""),
            city=client_data.get("BillingCity", ""),
            country=client_data.get("BillingCountry", "FR"),
            salesforce_id=client_data.get("Id", ""),
            sap_code=client_data.get("CardCode", "")
        )
        
        # Conversion produits
        products = []
        for i, product_data in enumerate(products_data):
            if product_data.get("found"):
                # Récupération de la quantité depuis extracted_info
                requested_qty = 1
                if i < len(extracted_info.get("products", [])):
                    requested_qty = extracted_info["products"][i].get("quantity", 1)
                
                product = ProductData(
                    code=product_data.get("code", ""),
                    name=product_data.get("name", ""),
                    price=product_data.get("price", 0),
                    quantity=requested_qty,
                    stock=product_data.get("stock", 0),
                    available=product_data.get("available", False)
                )
                products.append(product)
        
        return QuoteData(
            client=client,
            products=products,
            total_amount=sum(p.price * p.quantity for p in products),
            created_at=datetime.now()
        )
    
    def _handle_client_suggestions(self, client_result: Dict[str, Any], 
                                 extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """Gestion des suggestions client"""
        return {
            "success": False,
            "status": "client_suggestions_required",
            "message": client_result.get("message", "Client non trouvé"),
            "suggestions": client_result.get("suggestions"),
            "actions": client_result.get("actions", []),
            "context": {
                "extracted_info": extracted_info,
                "task_id": self.task_id
            }
        }
    
    def _handle_products_not_found(self, products_not_found: List[Dict[str, Any]], 
                                 all_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Gestion des produits non trouvés"""
        return {
            "success": False,
            "status": "products_not_found",
            "message": f"{len(products_not_found)} produit(s) non trouvé(s)",
            "products_not_found": products_not_found,
            "products_found": [p for p in all_products if p.get("found")],
            "task_id": self.task_id
        }
    
    def _handle_stock_issues(self, stock_validation: Dict[str, Any]) -> Dict[str, Any]:
        """Gestion des problèmes de stock"""
        return {
            "success": False,
            "status": "stock_insufficient",
            "message": "Stock insuffisant pour certains produits",
            "stock_validation": stock_validation,
            "task_id": self.task_id
        }
    
    def _initialize_task_tracking(self, prompt: str) -> str:
        """Initialisation du tracking de tâche"""
        self.current_task = progress_tracker.create_task(
            user_prompt=prompt,
            draft_mode=self.draft_mode
        )
        return self.current_task.task_id
    
    def _track_step_start(self, step_id: str, message: str = ""):
        """Démarrage d'une étape"""
        if self.current_task:
            self.current_task.start_step(step_id, message)
    
    def _track_step_complete(self, step_id: str, message: str = ""):
        """Complétion d'une étape"""
        if self.current_task:
            self.current_task.complete_step(step_id, message)
    
    def _track_step_fail(self, step_id: str, error: str):
        """Échec d'une étape"""
        if self.current_task:
            self.current_task.fail_step(step_id, error)
    
    def get_task_status(self) -> Optional[Dict[str, Any]]:
        """Récupération du statut de la tâche"""
        if self.current_task:
            return self.current_task.get_detailed_progress()
        return None