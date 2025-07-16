# workflow/devis_workflow_v2.py
"""
DevisWorkflow V2 - Version refactorisée utilisant les nouveaux managers
Compatible avec l'ancien système pour migration progressive
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from managers.client_manager import ClientManager
from managers.product_manager import ProductManager
from managers.quote_manager import QuoteManager
from utils.common_utils import ResponseBuilder, ErrorHandler
from models.data_models import QuoteData, ClientData, ProductData, APIResponse

logger = logging.getLogger(__name__)

class DevisWorkflowV2:
    """
    Version 2 du workflow de devis - Architecture modulaire
    
    Remplace progressivement l'ancien DevisWorkflow monolithique
    """
    
    def __init__(self, draft_mode: bool = False, task_id: Optional[str] = None):
        """
        Initialisation du workflow V2
        
        Args:
            draft_mode: Mode brouillon si True
            task_id: ID de tâche existant pour récupération
        """
        self.draft_mode = draft_mode
        self.task_id = task_id
        
        # Managers spécialisés
        self.quote_manager = QuoteManager(draft_mode=draft_mode)
        self.client_manager = ClientManager()
        self.product_manager = ProductManager()
        
        # Utilitaires
        self.response_builder = ResponseBuilder()
        self.error_handler = ErrorHandler()
        
        logger.info(f"✅ DevisWorkflowV2 initialisé (draft: {draft_mode})")
    
    async def process_quote_request(self, user_prompt: str) -> Dict[str, Any]:
        """
        Traitement d'une demande de devis - Point d'entrée principal
        
        Args:
            user_prompt: Demande utilisateur en langage naturel
            
        Returns:
            Dict avec le résultat du traitement
        """
        try:
            logger.info(f"🚀 Traitement demande devis V2: {user_prompt[:100]}...")
            
            # Délégation au QuoteManager
            result = await self.quote_manager.generate_quote(user_prompt, self.task_id)
            
            # Enrichissement de la réponse avec métadonnées V2
            if isinstance(result, dict):
                result["workflow_version"] = "v2"
                result["managers_used"] = {
                    "quote_manager": True,
                    "client_manager": True,
                    "product_manager": True
                }
                result["performance_metrics"] = await self._get_performance_metrics()
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur workflow V2: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def continue_after_user_input(self, user_input: Dict[str, Any], 
                                      context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Continuation du workflow après interaction utilisateur
        
        Args:
            user_input: Réponse utilisateur
            context: Contexte de l'interaction
            
        Returns:
            Dict avec la suite du traitement
        """
        try:
            interaction_type = context.get("interaction_type", "")
            
            if interaction_type == "client_suggestions":
                return await self._handle_client_suggestions_response(user_input, context)
            elif interaction_type == "product_suggestions":
                return await self._handle_product_suggestions_response(user_input, context)
            elif interaction_type == "stock_validation":
                return await self._handle_stock_validation_response(user_input, context)
            else:
                return self.error_handler.handle_generation_error(
                    f"Type d'interaction non reconnu: {interaction_type}"
                )
                
        except Exception as e:
            logger.exception(f"Erreur continuation workflow V2: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def _handle_client_suggestions_response(self, user_input: Dict[str, Any], 
                                                context: Dict[str, Any]) -> Dict[str, Any]:
        """Gestion de la réponse aux suggestions client"""
        try:
            action = user_input.get("action", "")
            
            if action == "select_client":
                # Client sélectionné depuis les suggestions
                selected_client = user_input.get("selected_client", {})
                client_data = ClientData.from_dict(selected_client)
                
                # Continuer avec le client sélectionné
                return await self._continue_with_client(client_data, context)
                
            elif action == "create_new_client":
                # Création d'un nouveau client
                client_data = ClientData.from_dict(user_input.get("client_data", {}))
                
                # Validation et création
                validation = await self.client_manager.validate_client(client_data.to_dict())
                if not validation.is_valid:
                    return self.response_builder.build_error_response(
                        "Validation échouée",
                        f"Erreurs: {', '.join(validation.errors)}"
                    )
                
                creation_result = await self.client_manager.create_client(client_data)
                if not creation_result.get("success"):
                    return self.response_builder.build_error_response(
                        "Erreur création client",
                        creation_result.get("message", "Erreur inconnue")
                    )
                
                # Continuer avec le nouveau client
                return await self._continue_with_client(client_data, context)
                
            else:
                return self.error_handler.handle_generation_error(
                    f"Action client non reconnue: {action}"
                )
                
        except Exception as e:
            logger.exception(f"Erreur gestion suggestions client: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def _handle_product_suggestions_response(self, user_input: Dict[str, Any], 
                                                 context: Dict[str, Any]) -> Dict[str, Any]:
        """Gestion de la réponse aux suggestions produit"""
        try:
            action = user_input.get("action", "")
            
            if action == "select_products":
                # Produits sélectionnés depuis les suggestions
                selected_products = user_input.get("selected_products", [])
                products_data = [ProductData.from_dict(p) for p in selected_products]
                
                # Continuer avec les produits sélectionnés
                return await self._continue_with_products(products_data, context)
                
            elif action == "search_alternatives":
                # Recherche d'alternatives
                search_query = user_input.get("search_query", "")
                alternatives = await self.product_manager.get_product_catalog(
                    category=search_query, limit=20
                )
                
                return self.response_builder.build_suggestions_response(
                    {"alternatives": alternatives},
                    "Alternatives trouvées"
                )
                
            else:
                return self.error_handler.handle_generation_error(
                    f"Action produit non reconnue: {action}"
                )
                
        except Exception as e:
            logger.exception(f"Erreur gestion suggestions produit: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def _handle_stock_validation_response(self, user_input: Dict[str, Any], 
                                              context: Dict[str, Any]) -> Dict[str, Any]:
        """Gestion de la réponse à la validation de stock"""
        try:
            action = user_input.get("action", "")
            
            if action == "proceed_with_available":
                # Procéder avec les quantités disponibles
                adjusted_products = user_input.get("adjusted_products", [])
                products_data = [ProductData.from_dict(p) for p in adjusted_products]
                
                return await self._continue_with_products(products_data, context)
                
            elif action == "find_alternatives":
                # Rechercher des alternatives pour les produits en rupture
                out_of_stock_products = user_input.get("out_of_stock_products", [])
                
                alternatives = {}
                for product_code in out_of_stock_products:
                    product_alternatives = await self.product_manager._find_alternative_products(product_code)
                    alternatives[product_code] = product_alternatives
                
                return self.response_builder.build_suggestions_response(
                    {"alternatives": alternatives},
                    "Alternatives trouvées pour les produits en rupture"
                )
                
            else:
                return self.error_handler.handle_generation_error(
                    f"Action stock non reconnue: {action}"
                )
                
        except Exception as e:
            logger.exception(f"Erreur gestion validation stock: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def _continue_with_client(self, client_data: ClientData, 
                                  context: Dict[str, Any]) -> Dict[str, Any]:
        """Continuation du workflow avec un client validé"""
        try:
            # Récupération des produits depuis le contexte
            extracted_info = context.get("extracted_info", {})
            product_codes = [p.get("code") for p in extracted_info.get("products", [])]
            
            if not product_codes:
                return self.error_handler.handle_generation_error(
                    "Aucun produit trouvé dans le contexte"
                )
            
            # Recherche des produits
            products_result = await self.product_manager.find_products(product_codes)
            
            # Validation des produits
            products_not_found = [p for p in products_result if not p.get("found")]
            if products_not_found:
                return self.response_builder.build_suggestions_response(
                    {"products_not_found": products_not_found},
                    "Certains produits n'ont pas été trouvés"
                )
            
            # Création des objets ProductData
            products_data = []
            for i, product_result in enumerate(products_result):
                if product_result.get("found"):
                    # Récupération quantité depuis extracted_info
                    requested_qty = 1
                    if i < len(extracted_info.get("products", [])):
                        requested_qty = extracted_info["products"][i].get("quantity", 1)
                    
                    product_data = ProductData(
                        code=product_result.get("code", ""),
                        name=product_result.get("name", ""),
                        price=product_result.get("price", 0),
                        quantity=requested_qty,
                        stock=product_result.get("stock", 0),
                        available=product_result.get("available", False)
                    )
                    products_data.append(product_data)
            
            return await self._continue_with_products(products_data, context, client_data)
            
        except Exception as e:
            logger.exception(f"Erreur continuation avec client: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def _continue_with_products(self, products_data: List[ProductData], 
                                    context: Dict[str, Any],
                                    client_data: Optional[ClientData] = None) -> Dict[str, Any]:
        """Continuation du workflow avec des produits validés"""
        try:
            # Validation du stock
            products_dict = [p.to_dict() for p in products_data]
            stock_validation = await self.product_manager.validate_stock(products_dict)
            
            if not stock_validation["all_available"]:
                return self.response_builder.build_warning_response(
                    "Stock insuffisant pour certains produits",
                    stock_validation,
                    stock_validation["warnings"]
                )
            
            # Si pas de client fourni, le récupérer du contexte
            if not client_data:
                client_info = context.get("client_info", {})
                if not client_info:
                    return self.error_handler.handle_generation_error(
                        "Aucune information client disponible"
                    )
                client_data = ClientData.from_dict(client_info)
            
            # Création du devis
            quote_data = QuoteData(
                client=client_data,
                products=products_data,
                total_amount=sum(p.price * p.quantity for p in products_data)
            )
            
            # Génération selon le mode
            if self.draft_mode:
                return await self._generate_draft_response(quote_data)
            else:
                return await self._generate_final_response(quote_data)
                
        except Exception as e:
            logger.exception(f"Erreur continuation avec produits: {str(e)}")
            return self.error_handler.handle_generation_error(str(e))
    
    async def _generate_draft_response(self, quote_data: QuoteData) -> Dict[str, Any]:
        """Génération d'une réponse draft"""
        return self.response_builder.build_success_response(
            {
                "mode": "draft",
                "quote_data": quote_data.to_dict(),
                "actions": [
                    {"action": "confirm_quote", "label": "Confirmer le devis"},
                    {"action": "modify_quote", "label": "Modifier le devis"},
                    {"action": "cancel_quote", "label": "Annuler"}
                ]
            },
            "Devis draft généré avec succès"
        )
    
    async def _generate_final_response(self, quote_data: QuoteData) -> Dict[str, Any]:
        """Génération d'une réponse finale"""
        # Délégation au QuoteManager pour la génération finale
        result = await self.quote_manager._generate_final_quote(quote_data)
        return result
    
    async def _get_performance_metrics(self) -> Dict[str, Any]:
        """Récupération des métriques de performance"""
        return {
            "cache_stats": {
                "client_cache": self.client_manager.get_cache_stats(),
                "product_cache": self.product_manager.get_cache_stats()
            },
            "workflow_version": "v2",
            "timestamp": datetime.now().isoformat()
        }
    
    def get_task_status(self) -> Optional[Dict[str, Any]]:
        """Récupération du statut de la tâche"""
        if self.quote_manager:
            return self.quote_manager.get_task_status()
        return None
    
    # Méthodes de compatibilité avec l'ancien système
    
    async def process_prompt(self, prompt: str, task_id: str = None, 
                           draft_mode: bool = False) -> Dict[str, Any]:
        """
        Méthode de compatibilité avec l'ancien DevisWorkflow
        
        Args:
            prompt: Demande utilisateur
            task_id: ID de tâche (optionnel)
            draft_mode: Mode brouillon
            
        Returns:
            Dict avec le résultat
        """
        logger.info("🔄 Appel méthode de compatibilité process_prompt")
        
        # Mise à jour des paramètres
        if task_id:
            self.task_id = task_id
        if draft_mode != self.draft_mode:
            self.draft_mode = draft_mode
            self.quote_manager.draft_mode = draft_mode
        
        # Délégation à la nouvelle méthode
        return await self.process_quote_request(prompt)
    
    async def continue_quote_generation(self, user_input: Dict[str, Any], 
                                      context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Méthode de compatibilité pour la continuation
        
        Args:
            user_input: Entrée utilisateur
            context: Contexte de l'interaction
            
        Returns:
            Dict avec la suite du traitement
        """
        logger.info("🔄 Appel méthode de compatibilité continue_quote_generation")
        return await self.continue_after_user_input(user_input, context)
    
    def clear_caches(self) -> None:
        """Nettoyage des caches"""
        self.client_manager.clear_cache()
        self.product_manager.clear_cache()
        logger.info("🧹 Caches nettoyés")
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiques globales du workflow V2"""
        return {
            "workflow_version": "v2",
            "draft_mode": self.draft_mode,
            "task_id": self.task_id,
            "managers": {
                "client_manager": self.client_manager.get_cache_stats(),
                "product_manager": self.product_manager.get_cache_stats()
            },
            "timestamp": datetime.now().isoformat()
        }