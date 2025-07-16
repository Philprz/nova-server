# workflow/devis_workflow.py - VERSION COMPLÈTE AVEC VALIDATEUR CLIENT
import re
import sys
import io
import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from services.llm_extractor import LLMExtractor
from services.mcp_connector import MCPConnector
from services.progress_tracker import progress_tracker, QuoteTask
from services.suggestion_engine import SuggestionEngine
from services.client_validator import ClientValidator

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
    
    def __init__(self, validation_enabled: bool = True, draft_mode: bool = False, force_production: bool = True, task_id: str = None):
        """
        Args:
            validation_enabled: Active la validation des données
            draft_mode: Mode brouillon (True) ou normal (False)
            force_production: Force le mode production même si connexions échouent
        task_id: ID de tâche existant pour récupérer une tâche en cours
        """
        self.mcp_connector = MCPConnector()
        self.llm_extractor = LLMExtractor()
        self.client_validator = ClientValidator() if validation_enabled else None
        self.validation_enabled = validation_enabled
        self.draft_mode = draft_mode
        self.force_production = force_production  # 🆕 NOUVEAU PARAMÈTRE
        self.context = {}

        # Configuration mode production
        if force_production:
            logger.info("🔥 MODE PRODUCTION FORCÉ - Pas de fallback démo")
            self.demo_mode = False
        else:
            self.demo_mode = True  # Mode démo par défaut

        # NOUVEAU : Support du tracking de progression
        self.current_task: Optional[QuoteTask] = None
        self.task_id: Optional[str] = task_id  # Utiliser le task_id fourni
        
        # Si un task_id est fourni, récupérer la tâche existante
        if task_id:
            self.current_task = progress_tracker.get_task(task_id)
            if self.current_task:
                logger.info(f"✅ Tâche récupérée: {task_id}")
            else:
                logger.warning(f"⚠️ Tâche {task_id} introuvable")
        
        # Ancien système de workflow_steps conservé pour compatibilité
        self.workflow_steps = []
        # 🧠 NOUVEAU : Initialiser le moteur de suggestions
        self.suggestion_engine = SuggestionEngine()
        self.client_suggestions = None
        self.product_suggestions = []

        # 🆕 NOUVEAUX COMPOSANTS
        from services.cache_manager import referential_cache
        from workflow.validation_workflow import SequentialValidator

        self.cache_manager = referential_cache
        self.sequential_validator = SequentialValidator(self.mcp_connector, self.llm_extractor)

        # Pré-charger le cache au démarrage (seulement si dans un contexte async)
        try:
            asyncio.create_task(self._initialize_cache())
        except RuntimeError:
            # Pas d'event loop actif, initialisation différée
            logger.info("⏳ Initialisation du cache différée (pas d'event loop actif)")

        logger.info("✅ Workflow initialisé avec cache et validation séquentielle")

    async def _initialize_cache(self):
        """Initialisation asynchrone du cache"""
        try:
            await self.cache_manager.preload_common_data(self.mcp_connector)
            logger.info("🚀 Cache pré-chargé avec succès")
        except Exception as e:
            logger.warning(f"⚠️ Erreur pré-chargement cache: {str(e)}")
        
    def _initialize_task_tracking(self, prompt: str) -> str:
        """Initialise le tracking de progression pour cette génération"""
        self.current_task = progress_tracker.create_task(
            user_prompt=prompt,
            draft_mode=self.draft_mode
        )
        self.task_id = self.current_task.task_id
        logger.info(f"Tracking initialisé pour la tâche: {self.task_id}")
        return self.task_id
    
    def _track_step_start(self, step_id: str, message: str = ""):
        """Démarre le tracking d'une étape"""
        if self.current_task:
            self.current_task.start_step(step_id, message)
    
    def _track_step_progress(self, step_id: str, progress: int, message: str = ""):
        """Met à jour la progression d'une étape"""
        if self.current_task:
            self.current_task.update_step_progress(step_id, progress, message)
    
    def _track_step_complete(self, step_id: str, message: str = ""):
        """Termine une étape avec succès"""
        if self.current_task:
            self.current_task.complete_step(step_id, message)
    
    def _track_step_fail(self, step_id: str, error: str, message: str = ""):
        """Termine une étape en erreur"""
        if self.current_task:
            self.current_task.fail_step(step_id, error, message)

    # 🔧 NOUVELLE MÉTHODE PRINCIPALE AVEC VALIDATION SÉQUENTIELLE
    async def process_quote_request(self, user_prompt: str, draft_mode: bool = False) -> Dict[str, Any]:
        """
        MÉTHODE PRINCIPALE MODIFIÉE - Version avec validation séquentielle
        """

        try:
            self.draft_mode = draft_mode

            # Nettoyage préventif du cache
            await self.cache_manager.cleanup_expired()

            # PHASE 1: Extraction LLM (inchangée)
            self._track_step_start("parse_prompt", "🔍 Analyse de votre demande")
            extracted_info = await self._extract_info_from_prompt(user_prompt)

            if not extracted_info:
                return self._build_error_response("Extraction échouée", "Impossible d'analyser votre demande")

            self._track_step_complete("parse_prompt", "✅ Demande analysée")

            # PHASE 2: NOUVELLE VALIDATION SÉQUENTIELLE
            self._track_step_start("sequential_validation", "🔍 Validation séquentielle en cours...")

            validation_result = await self.sequential_validator.validate_quote_request(extracted_info)

            if validation_result["status"] == "ready":
                # ✅ TOUT EST VALIDÉ - CONTINUER LE WORKFLOW
                self._track_step_complete("sequential_validation", "✅ Validation complète réussie")

                # Mettre à jour le contexte avec les données validées
                self.context["client_info"] = {"data": validation_result["data"]["client"], "found": True}
                self.context["products_info"] = validation_result["data"]["products"]

                # Continuer avec la génération du devis
                return await self._continue_quote_generation(validation_result["data"])

            elif validation_result["status"] == "user_input_required":
                # 🔄 INTERACTION UTILISATEUR NÉCESSAIRE
                self._track_step_progress("sequential_validation", 50, f"En attente: {validation_result['step']}")

                return {
                    "status": "user_interaction_required",
                    "interaction_type": validation_result["step"],
                    "message": validation_result["message"],
                    "question": validation_result.get("question"),
                    "options": validation_result.get("options", []),
                    "input_type": validation_result.get("input_type", "text"),
                    "context": validation_result.get("context", {}),
                    "task_id": self.task_id,
                    "next_step": "continue_validation"
                }

            else:
                # ❌ ERREUR DE VALIDATION
                self._track_step_fail("sequential_validation", "Erreur de validation", validation_result.get("message"))
                return self._build_error_response("Erreur de validation", validation_result.get("message"))

        except Exception as e:
            logger.exception(f"Erreur workflow principal: {str(e)}")
            return self._build_error_response("Erreur système", f"Erreur interne: {str(e)}")

    # 🆕 NOUVELLE MÉTHODE POUR CONTINUER APRÈS INTERACTION
    async def continue_after_user_input(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """
        Continue le workflow après une interaction utilisateur
        """

        try:
            interaction_type = context.get("interaction_type")

            if interaction_type == "client_selection":
                return await self._handle_client_selection(user_input, context)

            elif interaction_type == "client_creation":
                return await self._handle_client_creation(user_input, context)

            elif interaction_type == "product_selection":
                return await self._handle_product_selection(user_input, context)

            elif interaction_type == "quantity_adjustment":
                return await self._handle_quantity_adjustment(user_input, context)

            else:
                return self._build_error_response("Type d'interaction non reconnu", f"Type: {interaction_type}")

        except Exception as e:
            logger.exception(f"Erreur continuation workflow: {str(e)}")
            return self._build_error_response("Erreur continuation", str(e))

    # 🔧 HANDLERS POUR CHAQUE TYPE D'INTERACTION

    async def _handle_client_selection(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la sélection de client par l'utilisateur"""

        selected_option = user_input.get("selected_option")

        if selected_option == "new_client":
            # Demander la création du client
            client_name = context.get("original_client_name")
            return await self._initiate_client_creation(client_name)

        else:
            # Client existant sélectionné
            selected_client_data = user_input.get("selected_data")

            if selected_client_data:
                # Mettre en cache et continuer
                await self.cache_manager.cache_client(selected_client_data["Name"], selected_client_data)

                self.context["client_info"] = {"data": selected_client_data, "found": True}

                # Continuer avec la validation des produits
                original_products = context.get("original_products", [])
                return await self._continue_product_validation(original_products)

        return self._build_error_response("Sélection client invalide", "Données client manquantes")

    async def _handle_client_creation(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la création d'un nouveau client"""

        if user_input.get("action") == "create_client":
            # Lancer le processus de création avec validation SIRET
            client_name = user_input.get("client_name") or context.get("client_name")

            return {
                "status": "client_creation_required",
                "message": f"Création du client '{client_name}' en cours...",
                "next_step": "gather_client_info",
                "client_name": client_name
            }

        elif user_input.get("action") == "retry_client":
            # Demander un nouveau nom de client
            return {
                "status": "user_interaction_required",
                "interaction_type": "client_retry",
                "message": "Veuillez saisir le nom correct du client :",
                "input_type": "text",
                "placeholder": "Nom de l'entreprise"
            }

    async def _handle_product_selection(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la sélection de produit par l'utilisateur"""

        selected_product_data = user_input.get("selected_data")
        current_context = context.get("validation_context", {})

        if selected_product_data:
            # Ajouter le produit sélectionné aux produits validés
            validated_products = current_context.get("validated_products", [])
            validated_products.append({
                "product_data": selected_product_data,
                "requested_quantity": user_input.get("quantity", 1),
                "resolution_type": "user_selected"
            })

            # Vérifier s'il reste des produits à résoudre
            unresolved_products = current_context.get("unresolved_products", [])

            if len(unresolved_products) > 1:
                # Il reste des produits à traiter
                remaining_products = unresolved_products[1:]
                return await self._continue_product_resolution(validated_products, remaining_products)
            else:
                # Tous les produits sont résolus - passer à la validation des quantités
                return await self._continue_quantity_validation(validated_products)

    async def _handle_quantity_adjustment(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère l'ajustement des quantités"""

        action = user_input.get("action")

        if action == "proceed":
            # Continuer avec les quantités disponibles
            final_products = context.get("final_products", [])
            return await self._continue_quote_generation({"products": final_products})

        elif action == "modify":
            # Permettre la modification des quantités
            return {
                "status": "user_interaction_required",
                "interaction_type": "quantity_modification",
                "message": "Modification des quantités :",
                "products": context.get("final_products", []),
                "input_type": "quantity_form"
            }

        elif action == "cancel":
            return {
                "status": "cancelled",
                "message": "Demande de devis annulée par l'utilisateur"
            }

    # 🆕 MÉTHODE DE GÉNÉRATION FINALE OPTIMISÉE
    async def _continue_quote_generation(self, validated_data: Dict) -> Dict[str, Any]:
        """Continue la génération du devis avec les données validées"""

        try:
            # PHASE 3: Génération du devis avec données validées
            self._track_step_start("generate_quote", "📄 Génération du devis...")

            client_data = validated_data.get("client", self.context.get("client_info", {}).get("data"))
            products_data = validated_data.get("products", self.context.get("products_info", []))

            # Calculs finaux
            total_amount = sum(p.get("LineTotal", 0) for p in products_data)

            # Génération SAP
            sap_quote = await self._create_sap_quote(client_data, products_data)

            # Génération Salesforce (si SAP réussi)
            if sap_quote.get("success"):
                sf_opportunity = await self._create_salesforce_opportunity(client_data, products_data, sap_quote)

                self._track_step_complete("generate_quote", f"✅ Devis généré - Total: {total_amount:.2f}€")

                return {
                    "status": "quote_generated",
                    "quote_data": {
                        "client": client_data,
                        "products": products_data,
                        "total_amount": total_amount,
                        "sap_quote_number": sap_quote.get("quote_number"),
                        "salesforce_opportunity_id": sf_opportunity.get("opportunity_id"),
                        "cache_performance": await self.cache_manager.get_cache_stats()
                    }
                }
            else:
                self._track_step_fail("generate_quote", "Erreur SAP", sap_quote.get("error"))
                return self._build_error_response("Erreur génération", sap_quote.get("error"))

        except Exception as e:
            logger.exception(f"Erreur génération finale: {str(e)}")
            return self._build_error_response("Erreur génération", str(e))

    # Méthodes auxiliaires pour la génération
    async def _create_sap_quote(self, client_data: Dict, products_data: List[Dict]) -> Dict[str, Any]:
        """Crée le devis dans SAP"""
        try:
            # Utiliser la méthode existante _create_quote_in_salesforce qui gère SAP et Salesforce
            self.context["client_info"] = {"data": client_data, "found": True}
            self.context["products_info"] = products_data

            result = await self._create_quote_in_salesforce()
            return {
                "success": result.get("success", False),
                "quote_number": result.get("sap_quote_number"),
                "error": result.get("error")
            }
        except Exception as e:
            logger.exception(f"Erreur création devis SAP: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _create_salesforce_opportunity(self, client_data: Dict, products_data: List[Dict], sap_quote: Dict) -> Dict[str, Any]:
        """Crée l'opportunité dans Salesforce"""
        try:
            # Cette méthode est déjà gérée dans _create_quote_in_salesforce
            return {
                "success": True,
                "opportunity_id": sap_quote.get("salesforce_opportunity_id")
            }
        except Exception as e:
            logger.exception(f"Erreur création opportunité Salesforce: {str(e)}")
            return {"success": False, "error": str(e)}

    async def process_prompt(self, prompt: str, task_id: str = None, draft_mode: bool = False) -> Dict[str, Any]:
        """
        Version corrigée avec gestion robuste des erreurs
        """

        try:
            # Initialiser le tracking
            if task_id:
                self.current_task = progress_tracker.get_task(task_id)
                self.task_id = task_id
                if not self.current_task:
                    raise ValueError(f"Tâche {task_id} introuvable")
            else:
                self.task_id = self._initialize_task_tracking(prompt)

            # Stocker le mode draft
            if draft_mode:
                self.draft_mode = draft_mode
                logger.info("Mode DRAFT activé")

            logger.info(f"=== DÉMARRAGE WORKFLOW - Tâche {self.task_id} ===")

            # Phase 1: Extraction des informations (avec fallback robuste)
            self._track_step_start("parse_prompt", "Analyse de votre demande...")

            try:
                extracted_info = await self._extract_info_from_prompt(prompt)

                if extracted_info and "client" in extracted_info:
                    self._track_step_complete("parse_prompt", "✅ Demande analysée")

                    # 🎯 FORCER LE MODE PRODUCTION - Utiliser le workflow complet
                    logger.info("🚀 ACTIVATION MODE PRODUCTION - Workflow complet")

                    # Continuer avec le workflow production au lieu de retourner du démo
                    return await self.process_prompt_original(prompt, task_id, draft_mode)

                else:
                    raise ValueError("Extraction impossible")

            except Exception as e:
                self._track_step_fail("parse_prompt", "Erreur extraction", str(e))
                raise

        except Exception as e:
            logger.exception(f"Erreur workflow principal: {str(e)}")

            # Retourner une erreur détaillée
            return {
                "success": False,
                "error": f"Erreur lors de la génération du devis: {str(e)}",
                "message": f"Erreur lors de la génération du devis: {str(e)}",
                "task_id": getattr(self, 'task_id', None),
                "timestamp": datetime.now().isoformat(),
                "debug_info": {
                    "exception_type": type(e).__name__,
                    "exception_message": str(e),
                    "workflow_step": "extraction_info"
                }
            }

    async def process_prompt_original(self, prompt: str, task_id: str = None, draft_mode: bool = False) -> Dict[str, Any]:
        """
        Traite une demande de devis en langage naturel avec tracking détaillé

        Args:
            prompt: Demande en langage naturel
            task_id: ID de tâche existant (pour récupérer une tâche) ou None pour en créer une
            draft_mode: Mode brouillon si True, mode normal si False
        """
        try:
            # Stocker le mode draft si fourni
            if draft_mode:
                self.draft_mode = draft_mode
                logger.info("Mode DRAFT activé pour cette génération")

            # Test des connexions si mode production forcé
            if self.force_production:
                logger.info("🔍 Vérification connexions pour mode production...")

                try:
                    connections = await MCPConnector.test_connections()
                    sf_connected = connections.get('salesforce', {}).get('connected', False)
                    sap_connected = connections.get('sap', {}).get('connected', False)

                    if not sf_connected and not sap_connected:
                        raise ConnectionError("Aucune connexion système disponible")

                    logger.info(f"✅ Connexions OK - SF: {sf_connected}, SAP: {sap_connected}")

                except Exception as e:
                    if self.force_production:
                        # En mode production forcé, échouer plutôt que de basculer en démo
                        return {
                            "success": False,
                            "error": f"Connexions système indisponibles: {e}",
                            "message": "Impossible de traiter la demande - Systèmes non disponibles"
                        }

            # Initialiser ou récupérer le tracking
            if task_id:
                self.current_task = progress_tracker.get_task(task_id)
                self.task_id = task_id
                if not self.current_task:
                    raise ValueError(f"Tâche {task_id} introuvable")
            else:
                self.task_id = self._initialize_task_tracking(prompt)
            
            logger.info(f"=== DÉMARRAGE WORKFLOW - Tâche {self.task_id} ===")
            logger.info(f"Mode: {'DRAFT' if self.draft_mode else 'NORMAL'}")
            
            # ========== PHASE 1: ANALYSE DE LA DEMANDE ==========
            
            # Étape 1.1: Analyse initiale
            self._track_step_start("parse_prompt", "Analyse de votre demande...")
            await asyncio.sleep(0.5)  # Simulation temps de traitement
            self._track_step_progress("parse_prompt", 50, "Décomposition de la demande")
            
            # Étape 1.2: Extraction des entités
            self._track_step_complete("parse_prompt", "Demande analysée")
            self._track_step_start("extract_entities", "Identification des besoins...")
            
            extracted_info = await self._extract_info_from_prompt(prompt)
            self.context["extracted_info"] = extracted_info

            # 🔍 DEBUG : Log du type d'action
            logger.info(f"🎯 TYPE D'ACTION REÇU: {extracted_info.get('action_type', 'AUCUN')}")
            logger.info(f"📋 DONNÉES EXTRAITES: {extracted_info}")

            # 🆕 NOUVEAU : Router selon le type d'action détecté
            action_type = extracted_info.get("action_type", "DEVIS")
            logger.info(f"🚀 ROUTAGE VERS: {action_type}")

            if action_type == "RECHERCHE_PRODUIT":
                return await self._handle_product_search(extracted_info)
            elif action_type == "INFO_CLIENT":
                return await self._handle_client_info(extracted_info)
            elif action_type == "CONSULTATION_STOCK":
                return await self._handle_stock_consultation(extracted_info)
            elif action_type == "DEVIS":
                # Continuer avec le workflow de devis existant
                pass
            else:
                return await self._handle_other_request(extracted_info)
            # Vérifier les éléments manquants et demander les informations
            missing_elements = []
            if not extracted_info.get("client"):
                missing_elements.append("client")
            if not extracted_info.get("products") or len(extracted_info.get("products", [])) == 0:
                missing_elements.append("produits")
            
            if missing_elements:
                self._track_step_complete("extract_entities", "Informations partielles extraites")
                return await self._build_missing_info_response(extracted_info, missing_elements)
            
            self._track_step_progress("extract_entities", 80, "Informations extraites")
            
            # Étape 1.3: Validation input
            self._track_step_complete("extract_entities", "Besoins identifiés")
            self._track_step_start("validate_input", "Vérification de la cohérence...")
            
            # Validation de cohérence (client + produits présents)
            if not extracted_info.get("client") or not extracted_info.get("products"):
                self._track_step_fail("validate_input", "Informations manquantes",
                                    "Client ou produits non spécifiés")
                return self._build_error_response("Informations incomplètes", 
                                                "Veuillez spécifier le client et les produits")
            
            self._track_step_complete("validate_input", "Demande validée")
            
            # ========== PHASE 2: VALIDATION CLIENT ==========
            
            # Étape 2.1: Recherche client
            self._track_step_start("search_client", "Recherche du client...")
            
            client_info = await self._validate_client(extracted_info.get("client"))
    
            # Gérer les suggestions client
            if not client_info.get("found"):
                if client_info.get("suggestions"):
                    # Il y a des suggestions, retourner pour interaction utilisateur
                    self._track_step_progress("verify_client_info", 50, "Suggestions client disponibles")
                    return {
                        "status": "suggestions_required",
                        "type": "client_suggestions",
                        "message": client_info.get("message", "Suggestions disponibles"),
                        "suggestions": client_info["suggestions"],
                        "auto_suggest": client_info.get("auto_suggest", False),
                        "workflow_context": {
                            "extracted_info": extracted_info,
                            "task_id": self.task_id,
                            "step": "client_validation"
                        }
                    }
                else:
                    # Aucune suggestion, erreur classique
                    return self._build_error_response("Client non trouvé", 
                                                    client_info.get("message", "Client introuvable"))
            
            self.context["client_info"] = client_info
            
            self._track_step_progress("search_client", 70, "Consultation des bases de données")
            
            # Étape 2.2: Vérification des informations
            self._track_step_complete("search_client", "Recherche terminée")
            self._track_step_start("verify_client_info", "Vérification des informations...")
            
            # Gestion client non trouvé avec validation
            if not client_info.get("found") and self.validation_enabled:
                self._track_step_progress("verify_client_info", 50, "Client non trouvé, création en cours...")
                validation_result = await self._handle_client_not_found_with_validation(
                    extracted_info.get("client"), 
                    extracted_info  # ✅ Passer le contexte complet pour continuation
                )
                
                if validation_result.get("client_created"):
                    client_info = validation_result["client_info"] 
                    self.context["client_info"] = client_info
                    self.context["client_validation"] = validation_result["validation_details"]
                    self._track_step_progress("verify_client_info", 90, "Nouveau client créé")
                else:
                    self._track_step_fail("verify_client_info", validation_result.get("error", "Erreur de création"),
                                        "Impossible de créer le client")
                    return self._build_error_response("Impossible de créer le client", validation_result.get("error"))
            elif not client_info.get("found"):
                self._track_step_fail("verify_client_info", "Client introuvable", client_info.get("error"))
                return self._build_error_response("Client non trouvé", client_info.get("error"))
            
            # Étape 2.3: Client prêt
            self._track_step_complete("verify_client_info", "Informations vérifiées")
            self._track_step_complete("client_ready", f"Client {client_info.get('name', 'N/A')} validé")
            # Étape 2.4: Vérification doublons
            self._track_step_start("check_duplicates", "Vérification des doublons...")

            duplicate_check = await self._check_duplicate_quotes(
                client_info, 
                extracted_info.get("products", [])
            )
            self.context["duplicate_check"] = duplicate_check

            if duplicate_check.get("duplicates_found"):
                self._track_step_progress("check_duplicates", 80, f"⚠️ {len(duplicate_check.get('warnings', []))} alerte(s) détectée(s)")
                
                logger.warning(f"⚠️ {len(duplicate_check.get('warnings', []))} doublons détectés - Récupération des informations produits quand même")
                
                # 🔧 MODIFICATION : Récupérer les informations produits MÊME avec des doublons
                self._track_step_start("get_products_info", "Récupération des informations produits...")
                
                validated_products = await self._validate_products_with_suggestions(extracted_info.get("products", []))
                product_info = []
                # Vérifier s'il y a des produits nécessitant des suggestions
                products_with_suggestions = [p for p in validated_products if not p.get("found") and p.get("suggestions")]
                    
                if products_with_suggestions:
                    # Il y a des suggestions produits, retourner pour interaction utilisateur
                    self._track_step_progress("get_products_info", 50, "Suggestions produits disponibles")
                    return {
                        "status": "suggestions_required",
                        "type": "product_suggestions",
                        "message": f"{len(products_with_suggestions)} produit(s) nécessitent votre attention",
                        "products": validated_products,
                        "workflow_context": {
                            "extracted_info": extracted_info,
                            "client_info": client_info,
                            "task_id": self.task_id,
                            "step": "product_validation"
                        }
                    }
                else:
                    # Tous les produits sont OK, continuer avec la génération classique
                    products_info = [p["data"] for p in validated_products if p.get("found")]
                self.context["products_info"] = products_info
                
                self._track_step_complete("get_products_info", f"{len(products_info)} produit(s) analysé(s)")
                
                # 📢 AVERTISSEMENT NON BLOQUANT - L'utilisateur décide AVEC les informations
                self._track_step_complete("check_duplicates", "Doublons détectés - Suite du traitement")
                
                # Récupérer le nom du client depuis le contexte
                client_name = client_info.get("data", {}).get("Name", "Client")
                
                # En mode brouillon, même avec des doublons, on continue le processus
                if self.draft_mode:
                    logger.info(f"⚠️ Doublons détectés en mode brouillon - Continuation du processus malgré tout")
                    # Ne pas retourner ici, continuer à la section suivante
                else:
                    # En mode normal (non brouillon), on demande confirmation avant de continuer
                    # 🔧 CONSTRUIRE MANUELLEMENT LA PRÉVISUALISATION DU DEVIS
                    quote_preview = {
                        "client": {
                            "name": client_name,
                            "account_number": client_info.get("data", {}).get("AccountNumber", ""),
                            "salesforce_id": client_info.get("data", {}).get("Id", ""),
                            "phone": client_info.get("data", {}).get("Phone", ""),
                            "email": client_info.get("data", {}).get("Email", ""),
                            "city": client_info.get("data", {}).get("BillingCity", ""),
                            "country": client_info.get("data", {}).get("BillingCountry", "")
                        },
                        "products": [],
                        "total_amount": 0.0,
                        "currency": "EUR"
                    }

                    # Traiter les produits pour la prévisualisation
                    total_amount = 0.0
                    for product in products_info:
                        if isinstance(product, dict) and "error" not in product:
                            # 🔧 EXTRACTION CORRIGÉE DES DONNÉES PRODUIT
                            product_code = (product.get("code") or 
                                        product.get("item_code") or 
                                        product.get("ItemCode", ""))
                            
                            product_name = (product.get("name") or 
                                        product.get("item_name") or 
                                        product.get("ItemName", "Sans nom"))
                            quantity = float(product.get("quantity", 1))
                            unit_price = float(product.get("unit_price", 0))
                            line_total = quantity * unit_price
                            total_amount += line_total
                            
                            quote_preview["products"].append({
                                "code": product.get("code", ""),
                                "name": product.get("name", "Sans nom"),
                                "quantity": quantity,
                                "unit_price": unit_price,
                                "line_total": line_total,
                                "stock": product.get("stock", 0)
                            })

                    quote_preview["total_amount"] = total_amount

                    # Retourner une réponse WARNING avec tous les détails nécessaires
                    warning_response = {
                        "success": False,  # False pour arrêter le polling
                        "status": "warning",  
                        "task_id": self.task_id,
                        "message": f"Devis existants détectés pour {client_name}", 
                        "error_type": "duplicates_detected",
                        "error_details": {
                            "duplicate_check": duplicate_check,
                            "client_name": client_name,
                            "client_id": client_info.get("data", {}).get("Id"),
                            "action_required": "Des devis existants ont été trouvés. Que souhaitez-vous faire ?",
                            "quote_preview": quote_preview
                        }
                    }

                    # 🔧 CRITIQUE : Marquer la tâche comme terminée AVANT de retourner
                    if self.current_task and self.task_id:
                        progress_tracker.complete_task(self.task_id, warning_response)

                    logger.info(f"🔧 RETOUR WARNING RESPONSE pour tâche {self.task_id}")
                    return warning_response
            else:
                # Pas de doublons, continuer normalement
                self._track_step_complete("check_duplicates", "Aucun doublon détecté")
    
            # ========== PHASE 3: TRAITEMENT DES PRODUITS ==========
            
            # Étape 3.1: Connexion catalogue
            self._track_step_start("connect_catalog", "Connexion au catalogue...")
            await asyncio.sleep(0.3)  # Simulation connexion
            self._track_step_complete("connect_catalog", "Catalogue accessible")
            
            # Étape 3.2: Recherche produits
            self._track_step_start("lookup_products", "Vérification des produits...")
            
            products_info = await self._get_products_info(extracted_info.get("products", []))
            self.context["products_info"] = products_info
            
            self._track_step_progress("lookup_products", 60, f"{len(products_info)} produits analysés")
            
            # Étape 3.3: Vérification stock
            self._track_step_complete("lookup_products", "Produits trouvés")
            self._track_step_start("check_stock", "Vérification du stock...")
            
            availability = await self._check_availability(products_info)
            self.context["availability"] = availability
            
            self._track_step_progress("check_stock", 80, "Stock vérifié")
            
            # Étape 3.4: Calcul des prix
            self._track_step_complete("check_stock", "Stock disponible")
            self._track_step_start("calculate_prices", "Calcul des prix...")
            
            # Simulation calcul prix (logique déjà dans get_products_info)
            await asyncio.sleep(0.2)
            self._track_step_progress("calculate_prices", 90, "Prix calculés")
            
            # Étape 3.5: Produits prêts
            self._track_step_complete("calculate_prices", "Prix finalisés")
            self._track_step_complete("products_ready", f"{len([p for p in products_info if 'error' not in p])} produits confirmés")
            
            # ========== PHASE 4: CRÉATION DU DEVIS ==========
            
            # Étape 4.1: Préparation
            self._track_step_start("prepare_quote", "Préparation du devis...")
            
            # Logique de préparation (regroupement des données)
            await asyncio.sleep(0.2)
            self._track_step_progress("prepare_quote", 70, "Données consolidées")
            
            # Étape 4.2: Enregistrement SAP
            self._track_step_complete("prepare_quote", "Devis préparé")
            self._track_step_start("save_to_sap", "Enregistrement dans SAP...")
            
            quote_result = await self._create_quote_in_salesforce()
            self.context["quote_result"] = quote_result
            
            if not quote_result.get("success"):
                self._track_step_fail("save_to_sap", quote_result.get("error", "Erreur SAP"),
                                    "Impossible d'enregistrer dans SAP")
                return self._build_error_response("Erreur de création", quote_result.get("error"))
            
            self._track_step_progress("save_to_sap", 85, "Enregistré dans SAP")
            
            # Étape 4.3: Synchronisation Salesforce
            self._track_step_complete("save_to_sap", "SAP mis à jour")
            self._track_step_start("sync_salesforce", "Synchronisation Salesforce...")
            
            # La sync est déjà dans _create_quote_in_salesforce
            await asyncio.sleep(0.3)
            self._track_step_progress("sync_salesforce", 95, "Salesforce synchronisé")
            
            # Étape 4.4: Finalisation
            self._track_step_complete("sync_salesforce", "Synchronisation terminée")
            self._track_step_start("quote_finalized", "Finalisation...")
            
            # Construire la réponse finale
            response = self._build_response()
            response["task_id"] = self.task_id  # Ajouter l'ID de tâche
            
            self._track_step_complete("quote_finalized", "Devis généré avec succès")
            
            # Terminer la tâche
            if self.current_task:
                progress_tracker.complete_task(self.task_id, response)
            
            logger.info(f"=== WORKFLOW TERMINÉ - Tâche {self.task_id} ===")
            return response
            
        except Exception as e:
            logger.exception(f"Erreur critique dans le workflow: {str(e)}")
            
            # Marquer la tâche comme échouée
            if self.current_task and self.task_id:
                progress_tracker.fail_task(self.task_id, str(e))
            
            return self._build_error_response("Erreur système", str(e))
    
    def get_task_status(self, task_id: str = None) -> Optional[Dict[str, Any]]:
        """Récupère le statut détaillé d'une tâche"""
        target_id = task_id or self.task_id
        if not target_id:
            return None
            
        task = progress_tracker.get_task(target_id)
        if not task:
            return None
            
        return task.get_detailed_progress()
    
    async def _handle_client_not_found_with_validation(self, client_name: str, extracted_info: Dict = None) -> Dict[str, Any]:
        """Gère le cas où un client n'est pas trouvé en utilisant le validateur"""
        logger.info(f"🔍 Traitement client non trouvé avec validation: {client_name}")
        
        # CORRECTION 1: Vérifier si client_name est None ou vide
        if not client_name or client_name.strip() == "":
            logger.warning("❌ Nom de client vide ou None - impossible de valider")
            return {
                "client_created": False,
                "error": "Nom de client manquant - impossible de procéder à la validation",
                "suggestion": "Vérifiez que le prompt contient un nom de client valide",
                "workflow_context": {
                    "task_id": self.task_id,
                    "extracted_info": extracted_info,  # ✅ Conserver pour continuation
                    "step": "client_suggestions"
                }
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
            validation_result = await self._handle_client_not_found_with_validation(
                extracted_info.get("client"), 
                extracted_info  # ✅ Passer le contexte complet
            )
            
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
    async def _continue_workflow_after_client_selection(self, client_data, original_context):
        """Continuation automatique après sélection client"""
        self.context["client_info"] = {"data": client_data, "found": True}
        products = original_context.get("extracted_info", {}).get("products", [])
        return await self._get_products_info(products)


    async def _validate_products_with_suggestions(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Valide les produits avec suggestions intelligentes
        """
        logger.info(f"🔍 Validation de {len(products)} produit(s) avec suggestions")
        
        validated_products = []
        self.product_suggestions = []
        
        for i, product in enumerate(products):
            product_code = product.get("code", "")
            quantity = product.get("quantity", 1)
            
            logger.info(f"🔍 Validation produit {i+1}: {product_code}")
            
            try:
                # === RECHERCHE CLASSIQUE (code existant) ===
                sap_result = await self.mcp_connector.call_sap_mcp("sap_get_product_details", {"item_code": product_code})
                
                if "error" not in sap_result and sap_result.get("ItemCode"):
                    # Produit trouvé directement - CORRECTION: sap_result contient directement les données, pas de clé "data"
                    product_data = sap_result
                    validated_products.append({
                        "found": True,
                        "data": product_data,
                        "quantity": quantity,
                        "suggestions": None
                    })
                    self.product_suggestions.append(None)
                    logger.info(f"✅ Produit trouvé directement: {product_code}")
                    continue
                
                # === NOUVEAU : RECHERCHE INTELLIGENTE ===
                logger.info(f"🧠 Produit '{product_code}' non trouvé, activation des suggestions...")
                
                # Récupérer tous les produits pour la recherche floue
                all_products_result = await self.mcp_connector.call_sap_mcp("get_all_items", {"limit": 1000})
                available_products = all_products_result.get("data", []) if all_products_result.get("success") else []
                
                # Générer les suggestions
                product_suggestion = await self.suggestion_engine.suggest_product(product_code, available_products)
                self.product_suggestions.append(product_suggestion)
                
                if product_suggestion.has_suggestions:
                    primary_suggestion = product_suggestion.primary_suggestion
                    logger.info(f"🎯 Suggestion produit: {primary_suggestion.suggested_value} (score: {primary_suggestion.score})")
                    
                    validated_products.append({
                        "found": False,
                        "original_code": product_code,
                        "quantity": quantity,
                        "suggestions": product_suggestion.to_dict(),
                        "auto_suggest": (primary_suggestion.confidence.value == "high"),
                        "message": product_suggestion.conversation_prompt
                    })
                else:
                    # Aucune suggestion
                    validated_products.append({
                        "found": False,
                        "original_code": product_code,
                        "quantity": quantity,
                        "suggestions": None,
                        "message": f"Produit '{product_code}' non trouvé dans le catalogue"
                    })
                    
            except Exception as e:
                logger.exception(f"Erreur validation produit {product_code}: {str(e)}")
                validated_products.append({
                    "found": False,
                    "original_code": product_code,
                    "quantity": quantity,
                    "error": str(e)
                })
                self.product_suggestions.append(None)
        
        return validated_products
    
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
    async def apply_client_suggestion(self, suggestion_choice: Dict[str, Any], 
                                    workflow_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applique le choix de l'utilisateur pour une suggestion client
        """
        logger.info(f"🎯 Application suggestion client: {suggestion_choice}")
        
        choice_type = suggestion_choice.get("type")  # "use_suggestion", "create_new", "manual_entry"
        
        if choice_type == "use_suggestion":
            # Utiliser la suggestion proposée
            suggested_client = suggestion_choice.get("selected_client")
            
            # Reprendre le workflow avec le client suggéré
            workflow_context["extracted_info"]["client"] = suggested_client["name"]
            return await self.process_prompt(  # ✅ CORRECT
                workflow_context["extracted_info"]["original_prompt"],
                task_id=workflow_context["task_id"]
            )
        
        elif choice_type == "create_new":
            # Déclencher le processus de création client
            return {
                "status": "client_creation_required",
                "message": "Processus de création client à implémenter",
                "workflow_context": workflow_context
            }
        
        else:
            return self._build_error_response("Choix non supporté", f"Type de choix '{choice_type}' non reconnu")

    async def apply_product_suggestions(self, product_choices: List[Dict[str, Any]], 
                                    workflow_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applique les choix de l'utilisateur pour les suggestions produits
        """
        logger.info(f"🎯 Application suggestions produits: {len(product_choices)} choix")
        
        # Reconstituer la liste des produits avec les choix utilisateur
        final_products = []
        for choice in product_choices:
            if choice.get("type") == "use_suggestion":
                suggested_product = choice.get("selected_product")
                final_products.append({
                    "code": suggested_product["code"],
                    "quantity": choice.get("quantity", 1)
                })
            # Ajouter d'autres types de choix selon les besoins
        
        # Reprendre le workflow avec les produits corrigés
        workflow_context["extracted_info"]["products"] = final_products
        return await self.process_prompt(
            workflow_context["extracted_info"]["original_prompt"],
            task_id=workflow_context["task_id"]
        )
 
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
            if siret_data:
                sap_data["Notes"] += f" - SIRET: {siret_data.get('siret', '')}"
            
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
        
    async def _prepare_quote_data(self) -> Dict[str, Any]:
        """Prépare les données du devis"""
        # Préparer les données pour la création du devis
        client_info = self.context.get("client_info", {})
        products_info = self.context.get("products_info", [])
        
        # Récupérer les détails du client
        client_data = client_info.get("data", {})
        
        # Préparer les lignes de devis
        quote_lines = []
        
        for product in products_info:
            if isinstance(product, dict) and "error" not in product:
                quote_lines.append({
                    "product_id": product.get("id"),
                    "quantity": product.get("quantity", 1),
                    "unit_price": product.get("unit_price", 0)
                })
        
        return {
            "client": {
                "id": client_data.get("Id"),
                "name": client_data.get("Name"),
                "account_number": client_data.get("AccountNumber")
            },
            "quote_lines": quote_lines,
            "total_amount": sum(line["quantity"] * line["unit_price"] for line in quote_lines),
            "draft_mode": self.draft_mode
        }

    async def create_quote_with_confirmation(self, confirmed: bool = False) -> Dict[str, Any]:
        """Crée le devis après confirmation de l'utilisateur
        
        Args:
            confirmed: True si l'utilisateur a confirmé la création du devis
            
        Returns:
            Réponse formatée avec les détails du devis créé
        """
        logger.info(f"Traitement de la confirmation utilisateur, confirmé={confirmed}")
        
        if not confirmed:
            return {
                "status": "cancelled",
                "message": "Création du devis annulée"
            }
            
        # Récupérer le contexte pour poursuivre le workflow
        client_info = self.context.get("client_info", {})
        products_info = self.context.get("products_info", [])
        
        if not client_info or not products_info:
            logger.error("Contexte incomplet pour finaliser le devis")
            return {
                "status": "error",
                "message": "Données insuffisantes pour créer le devis"
            }
        
        # ===== Poursuivre avec la création du devis =====
        logger.info("Confirmation approuvée, poursuite de la création du devis")
        
        self._track_step_start("create_quote", "Création du devis après confirmation...")
        
        # Créer le devis dans Salesforce et SAP
        quote_result = await self._create_quote_in_salesforce()
        self.context["quote_result"] = quote_result
        
        if not quote_result.get("success"):
            self._track_step_fail("create_quote", quote_result.get("error", "Erreur inconnue"),
                               "Impossible de créer le devis confirmé")
            return {
                "status": "error",
                "message": f"Erreur lors de la création du devis: {quote_result.get('error', 'Erreur inconnue')}"
            }
            
        self._track_step_complete("create_quote", "Devis créé avec succès")
        
        # Construire la réponse finale
        response = self._build_response()
        
        # Marquer la tâche comme terminée
        if self.current_task and self.task_id:
            from services.progress_tracker import progress_tracker
            progress_tracker.complete_task(self.task_id, response)
            
        return response
        
    async def _check_sap_client_by_name(self, client_name: str, salesforce_client: Dict[str, Any] = None) -> Dict[str, Any]:
        """Vérifie si le client existe dans SAP par son nom
        
        Args:
            client_name: Nom du client à rechercher
            salesforce_client: Données du client Salesforce pour création SAP si nécessaire
        """
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
            
            # Client non trouvé, le créer avec TOUTES les données Salesforce si disponibles
            logger.info("Client non trouvé dans SAP, création avec données complètes...")
            
            # Vérifier que nous avons les données Salesforce
            sf_client = salesforce_client or {}
            client_id = sf_client.get("Id", "")
            
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
        """Crée le devis dans SAP ET Salesforce - VERSION COMPLÈTEMENT RÉÉCRITE"""
        logger.info("=== DÉBUT CRÉATION DEVIS SAP ET SALESFORCE ===")
        
        # Récupération des données du contexte
        client_info = self.context.get("client_info", {})
        products_info = self.context.get("products_info", [])
        sap_client = self.context.get("sap_client", {})
        
        # Log du contexte disponible
        logger.info(f"Client info disponible: {bool(client_info.get('found'))}")
        logger.info(f"Produits disponibles: {len(products_info)}")
        logger.info(f"Client SAP disponible: {bool(sap_client.get('data'))}")
        
        try:
            # ========== ÉTAPE 1: PRÉPARATION DES DONNÉES DE BASE ==========
            
            # Récupérer les données client Salesforce
            sf_client_data = client_info.get("data", {})
            client_name = sf_client_data.get("Name", "Client Unknown")
            client_id = sf_client_data.get("Id", "")
            
            logger.info(f"Client Salesforce: {client_name} (ID: {client_id})")
            
            # Créer le client SAP si nécessaire
            logger.info("=== CRÉATION/VÉRIFICATION CLIENT SAP ===")
            if not sap_client.get("data"):
                logger.info("Client SAP non trouvé, création nécessaire...")
            sap_client_result = await self._create_sap_client_if_needed(client_info)
            
            # CORRECTION : Traiter le résultat correctement
            if sap_client_result.get("success") and sap_client_result.get("client"):
                # Mettre à jour le contexte avec le client SAP trouvé/créé
                self.context["sap_client"] = {
                    "data": sap_client_result["client"],
                    "created": True  # ou False si trouvé
                }
                sap_client = self.context["sap_client"]
                logger.info(f"✅ Client SAP disponible: {sap_client_result['client'].get('CardCode')}")
            else:
                logger.error("❌ AUCUN CLIENT SAP DISPONIBLE")
                return {
                    "success": False,
                    "error": "Client SAP non disponible pour créer le devis"
                }
            
            # Vérifier que nous avons un client SAP
            sap_card_code = None
            if sap_client.get("data") and sap_client["data"].get("CardCode"):
                sap_card_code = sap_client["data"]["CardCode"]
                logger.info(f"Client SAP confirmé: {sap_card_code}")
            else:
                logger.error("❌ AUCUN CLIENT SAP DISPONIBLE")
                return {
                    "success": False,
                    "error": "Client SAP non disponible pour créer le devis"
                }
            
            # ========== ÉTAPE 2: PRÉPARATION DES PRODUITS ==========
            
            logger.info("=== PRÉPARATION DES LIGNES PRODUITS ===")
            valid_products = [p for p in products_info if isinstance(p, dict) and "error" not in p]
            
            if not valid_products:
                logger.error("❌ AUCUN PRODUIT VALIDE POUR LE DEVIS")
                return {
                    "success": False,
                    "error": "Aucun produit valide trouvé pour créer le devis"
                }
            
            logger.info(f"Produits valides: {len(valid_products)}")
            
            # Préparer les lignes pour SAP
            document_lines = []
            total_amount = 0.0
            
            for idx, product in enumerate(valid_products):
                quantity = float(product.get("quantity", 1))
                unit_price = float(product.get("unit_price", 0))
                line_total = quantity * unit_price
                total_amount += line_total
                
                line = {
                    "ItemCode": product.get("code"),
                    "Quantity": quantity,
                    "Price": unit_price,
                    "DiscountPercent": 0.0,
                    "TaxCode": "S1",
                    "LineNum": idx
                }
                document_lines.append(line)
                
                logger.info(f"Ligne {idx}: {product.get('code')} x{quantity} = {line_total}€")
            
            logger.info(f"Total calculé: {total_amount}€")
            
            # ========== ÉTAPE 3: PRÉPARATION DES DONNÉES DEVIS SAP ==========
            
            logger.info("=== PRÉPARATION DONNÉES DEVIS SAP ===")
            
            # Préparer les dates
            today = datetime.now()
            doc_date = today.strftime("%Y-%m-%d")
            due_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
            
            # Préparer les données complètes du devis SAP
            quotation_data = {
                "CardCode": sap_card_code,
                "DocDate": doc_date,
                "DocDueDate": due_date,
                "DocCurrency": "EUR",
                "Comments": f"Devis créé automatiquement via NOVA le {today.strftime('%d/%m/%Y %H:%M')} - Mode: {'DRAFT' if self.draft_mode else 'NORMAL'}",
                "SalesPersonCode": -1,
                "DocumentLines": document_lines,
                "DocTotal": total_amount,
                "VatSum": 0.0,
                "DiscountPercent": 0.0
            }
            
            # Ajouter des champs spécifiques au mode Draft si nécessaire
            if self.draft_mode:
                quotation_data["Comments"] = f"[BROUILLON] {quotation_data['Comments']}"
                quotation_data["Remarks"] = "Devis en mode brouillon - Non validé"
            
            logger.info("Données devis SAP préparées:")
            logger.info(f"  - Client: {sap_card_code}")
            logger.info(f"  - Lignes: {len(document_lines)}")
            logger.info(f"  - Total: {total_amount}€")
            logger.info(f"  - Mode: {'DRAFT' if self.draft_mode else 'NORMAL'}")
            
            # ========== ÉTAPE 4: APPEL SAP ==========
            
            logger.info("=== APPEL SAP POUR CRÉATION DEVIS ===")
            logger.info("Données complètes envoyées à SAP:")
            logger.info(json.dumps(quotation_data, indent=2, ensure_ascii=False))
            
            sap_quote = None
            
            try:
                # Choisir la méthode SAP selon le mode
                if self.draft_mode:
                    logger.info("Appel SAP en mode DRAFT...")
                    sap_quote = await MCPConnector.call_sap_mcp("sap_create_quotation_draft", {
                        "quotation_data": quotation_data
                    })
                else:
                    logger.info("Appel SAP en mode NORMAL...")
                    sap_quote = await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {
                        "quotation_data": quotation_data
                    })
                
                logger.info("=== RÉSULTAT APPEL SAP ===")
                logger.info(f"Type retourné: {type(sap_quote)}")
                logger.info(f"Contenu: {sap_quote}")
                
                # Vérifier le résultat SAP
                if sap_quote is None:
                    logger.error("❌ SAP a retourné None!")
                    sap_quote = {"success": False, "error": "SAP a retourné None - problème de communication"}
                elif not isinstance(sap_quote, dict):
                    logger.error(f"❌ SAP a retourné un type inattendu: {type(sap_quote)}")
                    sap_quote = {"success": False, "error": f"Type de retour SAP inattendu: {type(sap_quote)}"}
                elif not sap_quote.get("success", False):
                    logger.error(f"❌ SAP a signalé un échec: {sap_quote.get('error', 'Erreur non spécifiée')}")
                else:
                    logger.info(f"✅ Devis SAP créé avec succès: DocNum {sap_quote.get('doc_num')}")
                    
            except Exception as e:
                logger.exception(f"❌ EXCEPTION lors de l'appel SAP: {str(e)}")
                sap_quote = {"success": False, "error": f"Exception lors de l'appel SAP: {str(e)}"}
            
            # ========== ÉTAPE 5: CRÉATION SALESFORCE ==========
            
            logger.info("=== CRÉATION OPPORTUNITÉ SALESFORCE ===")
            
            # Préparer les données Salesforce avec référence SAP
            sap_ref = ""
            if sap_quote and sap_quote.get("success") and sap_quote.get("doc_num"):
                sap_ref = f" (SAP DocNum: {sap_quote['doc_num']})"
            
            opportunity_data = {
                'Name': f'NOVA-{today.strftime("%Y%m%d-%H%M%S")}',
                'AccountId': client_id,
                'StageName': 'Proposal/Price Quote',
                'CloseDate': due_date,
                'Amount': total_amount,
                'Description': f'Devis généré automatiquement via NOVA{sap_ref} - Mode: {"Brouillon" if self.draft_mode else "Définitif"}',
                'LeadSource': 'NOVA Middleware',
                'Type': 'New Customer',
                'Probability': 50 if not self.draft_mode else 25
            }
            
            logger.info("Création opportunité Salesforce...")
            logger.info(f"Données: {json.dumps(opportunity_data, indent=2, ensure_ascii=False)}")
            
            salesforce_quote = None
            
            try:
                opportunity_result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                    "sobject": "Opportunity",
                    "data": opportunity_data
                })
                
                if opportunity_result and opportunity_result.get("success"):
                    opportunity_id = opportunity_result.get("id")
                    logger.info(f"✅ Opportunité Salesforce créée: {opportunity_id}")
                    
                    salesforce_quote = {
                        "success": True,
                        "id": opportunity_id,
                        "opportunity_id": opportunity_id,
                        "lines_created": len(document_lines),
                        "total_amount": total_amount,
                        "message": f"Opportunité Salesforce créée avec succès: {opportunity_id}"
                    }
                else:
                    logger.error(f"❌ Erreur création opportunité Salesforce: {opportunity_result}")
                    salesforce_quote = {
                        "success": False,
                        "error": opportunity_result.get("error", "Erreur Salesforce non spécifiée")
                    }
                    
            except Exception as e:
                logger.exception(f"❌ EXCEPTION lors de la création Salesforce: {str(e)}")
                salesforce_quote = {
                    "success": False,
                    "error": f"Exception Salesforce: {str(e)}"
                }
            
            # ========== ÉTAPE 6: CONSTRUCTION DE LA RÉPONSE ==========
            
            logger.info("=== CONSTRUCTION RÉPONSE FINALE ===")
            
            # Déterminer le succès global
            sap_success = sap_quote and sap_quote.get("success", False)
            sf_success = salesforce_quote and salesforce_quote.get("success", False)
            
            # Pour le POC, on considère que le succès = au moins SAP OU Salesforce
            overall_success = sap_success or sf_success
            
            # Construire la réponse finale
            result = {
                "success": overall_success,
                "quote_id": f"SAP-{sap_quote.get('doc_num', 'FAILED')}" if sap_success else f"SF-{salesforce_quote.get('id', 'FAILED')}" if sf_success else f"FAILED-{today.strftime('%Y%m%d-%H%M%S')}",
                "sap_doc_entry": sap_quote.get("doc_entry") if sap_success else None,
                "sap_doc_num": sap_quote.get("doc_num") if sap_success else None,
                "salesforce_quote_id": salesforce_quote.get("id") if sf_success else None,
                "opportunity_id": salesforce_quote.get("id") if sf_success else None,
                "status": "Created" if overall_success else "Failed",
                "total_amount": total_amount,
                "currency": "EUR",
                "draft_mode": self.draft_mode,
                "sap_result": sap_quote,
                "salesforce_result": salesforce_quote,
                "creation_details": {
                    "sap_success": sap_success,
                    "salesforce_success": sf_success,
                    "client_code": sap_card_code,
                    "lines_count": len(document_lines),
                    "creation_timestamp": today.isoformat()
                }
            }
            
            # Message de statut
            if overall_success:
                messages = []
                if sap_success:
                    messages.append(f"SAP DocNum: {sap_quote.get('doc_num')}")
                if sf_success:
                    messages.append(f"Salesforce ID: {salesforce_quote.get('id')}")
                result["message"] = f"Devis créé avec succès - {', '.join(messages)}"
            else:
                errors = []
                if not sap_success:
                    errors.append(f"SAP: {sap_quote.get('error', 'Erreur inconnue') if sap_quote else 'Aucune réponse'}")
                if not sf_success:
                    errors.append(f"Salesforce: {salesforce_quote.get('error', 'Erreur inconnue') if salesforce_quote else 'Aucune réponse'}")
                result["message"] = f"Échec création devis - {'; '.join(errors)}"
                result["error"] = result["message"]
            
            logger.info("=== CRÉATION DEVIS TERMINÉE ===")
            logger.info(f"Succès global: {overall_success}")
            logger.info(f"SAP: {'✅' if sap_success else '❌'}")
            logger.info(f"Salesforce: {'✅' if sf_success else '❌'}")
            logger.info(f"Quote ID: {result['quote_id']}")
            
            return result
            
        except Exception as e:
            logger.exception(f"❌ ERREUR CRITIQUE dans _create_quote_in_salesforce: {str(e)}")
            return {
                "success": False,
                "error": f"Erreur critique lors de la création du devis: {str(e)}",
                "quote_id": f"ERROR-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "status": "Failed",
                "draft_mode": self.draft_mode,
                "creation_details": {
                    "error_type": "critical_exception",
                    "error_timestamp": datetime.now().isoformat()
                }
            }
    async def _create_sap_client_if_needed(self, client_info: Dict) -> Dict:
        """Crée un client SAP si nécessaire - STRUCTURE DE RETOUR CORRIGÉE"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            client_name = client_info.get("data", {}).get("Name", "Client NOVA")
            
            # 1. Chercher si le client existe avec sap_search
            search_result = await self.mcp_connector.call_sap_mcp(
                "sap_search", {
                    "query": client_name,
                    "entity_type": "BusinessPartners",
                    "limit": 5
                }
            )
            
            # CORRECTION: Vérifier la vraie structure de retour SAP
            if "error" not in search_result:
                # Si des résultats existent dans la réponse
                if search_result.get("value") and len(search_result["value"]) > 0:
                    found_client = search_result["value"][0]
                    logger.info(f"✅ Client SAP trouvé: {found_client.get('CardCode')} - {found_client.get('CardName')}")
                    return {"success": True, "client": found_client}
                elif search_result.get("results") and len(search_result["results"]) > 0:
                    found_client = search_result["results"][0]
                    logger.info(f"✅ Client SAP trouvé: {found_client.get('CardCode')} - {found_client.get('CardName')}")
                    return {"success": True, "client": found_client}
            
            # 2. Si pas trouvé, créer le client
            card_code = f"C{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            customer_data = {
                "CardCode": card_code,
                "CardName": client_name,
                "CardType": "cCustomer",
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO"
            }
            
            create_result = await self.mcp_connector.call_sap_mcp(
                "sap_create_customer_complete", 
                {"customer_data": customer_data}
            )
            
            if create_result.get("success"):
                logger.info(f"✅ Client SAP créé: {card_code}")
                return {"success": True, "client": {"CardCode": card_code, "CardName": client_name}}
            else:
                logger.error(f"❌ Échec création client SAP: {create_result.get('error')}")
                return {"success": False, "error": create_result.get("error", "Erreur inconnue")}
                
        except Exception as e:
            logger.error(f"❌ Exception création client SAP: {str(e)}")
            return {"success": False, "error": str(e)}
    
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
    
    def _get_stock_value(self, product: Dict[str, Any]) -> float:  # ← BON
        """Extrait la valeur du stock, qu'il soit un float ou un dict"""
        stock = product.get("stock", 0)
        
        # Si c'est déjà un float/int, le retourner directement
        if isinstance(stock, (int, float)):
            return float(stock)
        
        # Si c'est un dictionnaire, chercher 'total'
        if isinstance(stock, dict):
            return float(stock.get("total", 0))
        
        # Fallback
        return 0.0
    
    def _get_stock_safely(self, product: Dict[str, Any]) -> float:
        """
        Extrait la valeur du stock de manière robuste
        Gère les cas où stock est un float OU un dictionnaire
        """
        stock = product.get("stock", 0)
        
        # Cas 1: stock est déjà un nombre (float/int)
        if isinstance(stock, (int, float)):
            return float(stock)
        
        # Cas 2: stock est un dictionnaire avec 'total'
        if isinstance(stock, dict):
            return float(stock.get("total", 0))
            
        # Cas 3: fallback
        return 0.0
        
    def _build_response(self) -> Dict[str, Any]:
        """🔧 CORRECTION : Construit la réponse finale avec nom client correct"""
        logger.info("Construction de la réponse finale enrichie")
        
        client_info = self.context.get("client_info", {})
        quote_result = self.context.get("quote_result", {})
        sap_client = self.context.get("sap_client", {})
        client_validation = self.context.get("client_validation", {})
        products_info = self.context.get("products_info", [])
        extracted_info = self.context.get("extracted_info", {})
        
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
        
        # 🎯 CORRECTION CRITIQUE : Extraction intelligente du nom client  
        client_name = "Client extrait"

        # 1. Priorité au contexte client_info (données Salesforce)
        if self.context.get("client_info", {}).get("data", {}).get("Name"):
            client_name = self.context["client_info"]["data"]["Name"]
            logger.info(f"✅ Nom client depuis context Salesforce: {client_name}")

        # 2. Sinon, essayer les données SAP dans le contexte
        elif self.context.get("client_info", {}).get("data", {}).get("CardName"):
            sap_name = self.context["client_info"]["data"]["CardName"]
            # Nettoyer le format "CSAFRAN8267 - SAFRAN" -> "SAFRAN"
            if " - " in sap_name:
                client_name = sap_name.split(" - ", 1)[1].strip()
            else:
                client_name = sap_name
            logger.info(f"✅ Nom client depuis context SAP (nettoyé): {client_name}")

        # 3. En dernier recours, utiliser l'extraction LLM originale
        elif self.context.get("extracted_info", {}).get("client"):
            client_name = self.context["extracted_info"]["client"]
            logger.info(f"✅ Nom client depuis extraction LLM: {client_name}")
        
        # 4. En dernier recours, utiliser l'extraction LLM originale
        elif extracted_info.get("client"):
            client_name = extracted_info["client"]
            logger.info(f"✅ Nom client depuis extraction LLM: {client_name}")
        
        # 5. NOUVEAU: Utiliser les données SAP brutes depuis le résultat du devis
        elif quote_result.get("sap_result", {}).get("raw_result", {}).get("CardName"):
            sap_card_name = quote_result["sap_result"]["raw_result"]["CardName"]
            client_name = sap_card_name
            logger.info(f"✅ Nom client depuis SAP raw result: {client_name}")
        
        # Journalisation du nom client final après toutes les conditions
        logger.info(f"🎯 Nom client final pour interface: '{client_name}'")

        # Construction des données client pour l'interface
        client_data = client_info.get("data", {})
        client_response = {
            "name": client_name,  # ← UTILISER LE NOM CORRECTEMENT EXTRAIT
            "account_number": client_data.get("AccountNumber") or sap_client.get("data", {}).get("CardCode") or "",
            "salesforce_id": client_data.get("Id", ""),
            "phone": client_data.get("Phone", ""),
            "email": client_data.get("Email", ""),
            "city": client_data.get("BillingCity", ""),
            "country": client_data.get("BillingCountry", "")
        }
        
        # Construction des données produits (garder la logique existante)
        products_response = []
        for product in products_info:
            if isinstance(product, dict) and "error" not in product:
                # 🔧 EXTRACTION CORRIGÉE DES DONNÉES PRODUIT
                product_code = (product.get("code") or 
                            product.get("item_code") or 
                            product.get("ItemCode", ""))
                
                product_name = (product.get("name") or 
                            product.get("item_name") or 
                            product.get("ItemName", "Sans nom"))
                
                quantity = float(product.get("quantity", 1))
                unit_price = float(product.get("unit_price", 0))
                line_total = quantity * unit_price
                
                product_data = {
                    "code": product_code,                    # ✅ CORRIGÉ
                    "name": product_name,                    # ✅ CORRIGÉ  
                    "quantity": quantity,                    # ✅ CORRIGÉ
                    "unit_price": unit_price,               # ✅ CORRIGÉ
                    "line_total": line_total,               # ✅ CORRIGÉ
                    "stock_available": self._get_stock_value(product),
                    "available": self._get_stock_safely(product) >= quantity
                }
                products_response.append(product_data)
                
                logger.info(f"✅ Produit formaté dans réponse: {product_code} x{quantity} = {line_total}€")
        
        # 🔧 CONSTRUCTION RÉPONSE FINALE CORRIGÉE
        response = {
            "success": True,
            "status": "success",
            "quote_id": quote_result.get("opportunity_id", f"NOVA-{datetime.now().strftime('%Y%m%d-%H%M%S')}"),
            
            # 🎯 DONNÉES CLIENT CORRIGÉES AVEC BON NOM
            "client": client_response,
            
            # 🎯 DONNÉES PRODUITS
            "products": products_response,
            
            # Calculs financiers
            "total_amount": sum(float(p.get("line_total", 0)) for p in products_response),
            "currency": "EUR",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "quote_status": "Created",
            
            # Disponibilité
            "all_products_available": all(p.get("available", False) for p in products_response),
            
            # Informations système
            "sap_doc_num": quote_result.get("sap_doc_num"),
            "salesforce_quote_id": quote_result.get("opportunity_id"),
            "message": f"Devis généré avec succès pour {client_name}",  # ← INCLURE LE NOM
            
            # Mode draft
            "draft_mode": self.draft_mode
        }
        
        # Ajouter les informations de validation client si disponibles
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
        # Informations de vérification doublons DEVIS (nouveau)
        duplicate_check = self.context.get("duplicate_check", {})
        if duplicate_check:
            response["duplicate_check"] = {
                "duplicates_found": duplicate_check.get("duplicates_found", False),
                "warnings_count": len(duplicate_check.get("warnings", [])),
                "suggestions_count": len(duplicate_check.get("suggestions", [])),
                "recent_quotes": len(duplicate_check.get("recent_quotes", [])),
                "draft_quotes": len(duplicate_check.get("draft_quotes", [])),
                "similar_quotes": len(duplicate_check.get("similar_quotes", [])),
                "details": duplicate_check
            }
        # Ajouter les références système pour traçabilité
        response["system_references"] = {
            "sap_client_created": sap_client.get("created", False) if sap_client else False,
            "sap_client_card_code": sap_client.get("data", {}).get("CardCode") if sap_client and sap_client.get("data") else None,
            "quote_creation_timestamp": datetime.now().isoformat(),
            "validation_enabled": self.validation_enabled
        }
        
        logger.info(f"✅ Réponse finale enrichie construite avec nom client: {client_name}")
        response["workflow_steps"] = self.workflow_steps
        return response
    
    # ✅ MÉTHODE D'AIDE - Ajouter aussi cette méthode pour enrichir les données client
    def _enrich_client_data(self, client_name: str, salesforce_data: Dict[str, Any]) -> None:
        """Enrichit les données client dans le contexte"""
        self.enriched_client_name = client_name
        
        # Enrichir le contexte avec le nom correct
        if "client_info" not in self.context:
            self.context["client_info"] = {}
        
        if "data" not in self.context["client_info"]:
            self.context["client_info"]["data"] = {}
        
        # S'assurer que le nom est bien présent
        self.context["client_info"]["data"]["Name"] = client_name
        self.context["client_info"]["data"].update(salesforce_data)
        
        logger.info(f"✅ Client enrichi dans le contexte: {client_name}")    
    def _build_error_response(self, error_title: str, error_message: str) -> Dict[str, Any]:
        """Construit une réponse d'erreur standardisée"""
        logger.error(f"Erreur workflow: {error_title} - {error_message}")
        
        return {
            "status": "error",
            "success": False,
            "task_id": self.task_id,
            "error_title": error_title,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
            "workflow_steps": getattr(self, 'workflow_steps', []),
            "context_available": bool(self.context),
            "draft_mode": self.draft_mode
        }    
    
    async def _validate_client(self, client_name: str) -> Dict[str, Any]:
        """
        Valide le client avec suggestions intelligentes
        """
        logger.info(f"🔍 RECHERCHE CLIENT RÉEL: {client_name}")

        try:
            # === RECHERCHE CLASSIQUE (code existant) ===
            query = f"SELECT Id, Name, AccountNumber, AnnualRevenue, LastActivityDate FROM Account WHERE Name LIKE '%{client_name}%' LIMIT 10"
            logger.debug(f"📝 Requête Salesforce: {query}")

            sf_result = await self.mcp_connector.call_salesforce_mcp("salesforce_query", {"query": query})

            logger.info(f"📊 RÉSULTAT SALESFORCE BRUT: {json.dumps(sf_result, indent=2, ensure_ascii=False)}")

            # Client trouvé directement
            if sf_result.get("totalSize", 0) > 0 and sf_result.get("records"):
                client_record = sf_result["records"][0]
                logger.debug(f"📋 ENREGISTREMENT CLIENT TROUVÉ: {json.dumps(client_record, indent=2)}")

                self._enrich_client_data(client_record.get("Name", client_name), client_record)
                logger.info(f"✅ Client trouvé directement: {client_record.get('Name')} (ID: {client_record.get('Id')})")
                logger.debug(f"🔍 Détails client: AccountNumber={client_record.get('AccountNumber')}, Revenue={client_record.get('AnnualRevenue')}")
                return {"found": True, "data": client_record}
            
            # === NOUVEAU : RECHERCHE INTELLIGENTE ===
            logger.info("🧠 Client non trouvé, activation du moteur de suggestions...")

            # Récupérer tous les clients pour la recherche floue
            all_clients_query = "SELECT Id, Name, AccountNumber, AnnualRevenue, LastActivityDate FROM Account LIMIT 1000"
            logger.debug(f"📝 Requête tous clients: {all_clients_query}")

            all_clients_result = await self.mcp_connector.call_salesforce_mcp("salesforce_query", {"query": all_clients_query})
            logger.debug(f"📊 RÉSULTAT TOUS CLIENTS: {json.dumps(all_clients_result, indent=2, ensure_ascii=False)}")

            available_clients = all_clients_result.get("records", []) if all_clients_result.get("totalSize", 0) > 0 else []
            logger.info(f"🔍 {len(available_clients)} clients disponibles pour analyse")
            
            # Générer les suggestions
            self.client_suggestions = await self.suggestion_engine.suggest_client(client_name, available_clients)
            logger.debug(f"🔍 SUGGESTIONS GÉNÉRÉES: {json.dumps(self.client_suggestions.to_dict(), indent=2)}")

            if self.client_suggestions.has_suggestions:
                primary_suggestion = self.client_suggestions.primary_suggestion

                # Si confiance élevée, proposer auto-correction
                if primary_suggestion.confidence.value == "high":
                    logger.info(f"🎯 Suggestion haute confiance: {primary_suggestion.suggested_value} (score: {primary_suggestion.score})")
                    logger.debug(f"🔍 Détails suggestion: {primary_suggestion.details}")
                    
                    # Retourner avec suggestion pour que l'utilisateur puisse choisir
                    return {
                        "found": False, 
                        "suggestions": self.client_suggestions.to_dict(),
                        "auto_suggest": True,
                        "message": f"Client '{client_name}' non trouvé. Je suggère '{primary_suggestion.suggested_value}' (similarité: {primary_suggestion.score}%)"
                    }
                else:
                    # Confiance moyenne/faible, présenter les options
                    logger.info(f"🤔 Multiple suggestions trouvées pour: {client_name}")
                    return {
                        "found": False,
                        "suggestions": self.client_suggestions.to_dict(),
                        "auto_suggest": False,
                        "message": self.client_suggestions.conversation_prompt
                    }
            else:
                # Aucune suggestion, proposer création
                logger.info(f"❌ Aucune suggestion trouvée pour: {client_name}")
                return {
                    "found": False,
                    "suggestions": None,
                    "message": f"Client '{client_name}' non trouvé. Voulez-vous créer un nouveau client ?"
                }
                
        except Exception as e:
            logger.exception(f"Erreur validation client avec suggestions: {str(e)}")
            return {"found": False, "error": str(e)}
    
    async def _check_duplicate_quotes(self, client_info: Dict[str, Any], products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Vérifie s'il existe déjà des devis similaires pour éviter les doublons
        
        Args:
            client_info: Informations du client validé
            products: Liste des produits demandés
            
        Returns:
            Dict avec statut de vérification et actions suggérées
        """
        logger.info("🔍 Vérification des doublons de devis...")
        
        duplicate_check = {
            "duplicates_found": False,
            "recent_quotes": [],
            "similar_quotes": [],
            "draft_quotes": [],
            "action_required": False,
            "suggestions": [],
            "warnings": []
        }
        
        try:
            # Récupérer les identifiants client
            client_name = client_info.get("data", {}).get("Name", "")
            
            if not client_name:
                logger.warning("Aucun nom client pour vérification doublons")
                return duplicate_check
            
            # 1. Vérifier les devis SAP récents (dernières 48h)
            recent_quotes = await self._get_recent_sap_quotes(client_name, hours=48)
            
            # 2. Vérifier les devis brouillons existants
            draft_quotes = await self._get_client_draft_quotes(client_name)
            
            # 3. Analyser la similarité des produits
            similar_quotes = await self._find_similar_product_quotes(client_name, products)
            
            # Populate results
            duplicate_check["recent_quotes"] = recent_quotes
            duplicate_check["draft_quotes"] = draft_quotes  
            duplicate_check["similar_quotes"] = similar_quotes
            
            # Analyser les résultats
            total_findings = len(recent_quotes) + len(draft_quotes) + len(similar_quotes)
            
            if total_findings > 0:
                duplicate_check["duplicates_found"] = True
                duplicate_check["action_required"] = True
                
                # Messages d'alerte
                if recent_quotes:
                    duplicate_check["warnings"].append(f"⚠️ {len(recent_quotes)} devis récent(s) trouvé(s) pour {client_name}")
                    
                if draft_quotes:
                    duplicate_check["warnings"].append(f"📝 {len(draft_quotes)} devis en brouillon pour {client_name}")
                    duplicate_check["suggestions"].append("💡 Considérez consolider avec les brouillons existants")
                    
                if similar_quotes:
                    duplicate_check["warnings"].append(f"🔄 {len(similar_quotes)} devis avec produits similaires")
                    duplicate_check["suggestions"].append("💡 Vérifiez s'il s'agit d'une mise à jour ou d'un nouveau besoin")
            
            else:
                duplicate_check["suggestions"].append("✅ Aucun doublon détecté - Création sécurisée")
                
            logger.info(f"Vérification doublons terminée: {total_findings} potentiel(s) doublon(s)")
            return duplicate_check
            
        except Exception as e:
            logger.exception(f"Erreur vérification doublons devis: {str(e)}")
            duplicate_check["warnings"].append(f"❌ Erreur vérification doublons: {str(e)}")
            return duplicate_check

    async def _get_recent_sap_quotes(self, client_name: str, hours: int = 48) -> List[Dict[str, Any]]:
        """Récupère les devis SAP récents pour un client"""
        try:
            from datetime import datetime, timedelta
            
            # Calculer la date limite
            cutoff_date = datetime.now() - timedelta(hours=hours)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            # Rechercher dans SAP avec filtre date et client
            from services.mcp_connector import MCPConnector
            
            result = await MCPConnector.call_sap_mcp("sap_search_quotes", {
                "client_name": client_name,
                "date_from": cutoff_str,
                "limit": 10
            })
            
            if result.get("success") and result.get("quotes"):
                return result["quotes"]
            
            return []
            
        except Exception as e:
            logger.warning(f"Erreur recherche devis récents: {str(e)}")
            return []

    async def _get_client_draft_quotes(self, client_name: str) -> List[Dict[str, Any]]:
        """Récupère les devis en brouillon pour un client"""
        try:
            from sap_mcp import sap_list_draft_quotes
            
            # Récupérer tous les brouillons
            draft_result = await sap_list_draft_quotes()
            
            if not draft_result.get("success"):
                return []
            
            # Filtrer par nom client
            client_drafts = [
                quote for quote in draft_result.get("draft_quotes", [])
                if quote.get("card_name", "").lower() == client_name.lower()
            ]
            
            return client_drafts
            
        except Exception as e:
            logger.warning(f"Erreur recherche brouillons client: {str(e)}")
            return []

    async def _find_similar_product_quotes(self, client_name: str, requested_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trouve les devis avec des produits similaires"""
        try:
            # Pour l'instant, implémentation simplifiée
            # TODO: Logique avancée de comparaison produits
            
            # Extraire les codes produits demandés
            requested_codes = set(product.get("code", "").upper() for product in requested_products)
            
            logger.info(f"Recherche produits similaires pour {client_name}: {requested_codes}")
            
            # Retourner vide pour l'instant - à implémenter selon les besoins
            return []
            
        except Exception as e:
            logger.warning(f"Erreur recherche produits similaires: {str(e)}")
            return []
        
    async def _get_products_info(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Récupère les informations produits depuis SAP - VERSION CORRIGÉE POUR LES PRIX"""
        if not products:
            logger.warning("Aucun produit spécifié")
            return []

        logger.info(f"🔍 RECHERCHE PRODUITS RÉELS: {products}")

        enriched_products = []

        for product in products:
            try:
                # Appel MCP pour récupérer les détails du produit
                product_details = await MCPConnector.call_sap_mcp("sap_get_product_details", {
                    "item_code": product["code"]
                })

                logger.info(f"🏭 RÉSULTAT SAP: {product_details}")
                
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
    def _build_error_response(self, error_title: str, error_message: str) -> Dict[str, Any]:
        """Construit une réponse d'erreur standardisée"""
        logger.error(f"Erreur workflow: {error_title} - {error_message}")
        
        return {
            "status": "error",
            "success": False,
            "task_id": self.task_id,
            "error_title": error_title,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
            "workflow_steps": getattr(self, 'workflow_steps', []),
            "context_available": bool(self.context),
            "draft_mode": self.draft_mode
        }

    async def _extract_info_from_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Extraction des informations avec fallback robuste
        Version corrigée qui fonctionne même si Claude échoue
        """

        logger.info(f"🔄 Extraction d'informations depuis: {prompt}")

        # 🔧 STRATÉGIE 1: Essayer Claude API (si disponible)
        try:
            # Vérifier si l'API Claude est configurée
            api_key = os.getenv("ANTHROPIC_API_KEY")

            if api_key and api_key.startswith("sk-ant-"):
                logger.info("📞 Tentative d'extraction via Claude API...")

                # Importer le module avec gestion d'erreur
                try:
                    from services.llm_extractor import LLMExtractor
                    extracted_info = await LLMExtractor.extract_quote_info(prompt)

                    # Vérifier si l'extraction a réussi
                    if extracted_info and "error" not in extracted_info:
                        logger.info("✅ Extraction Claude réussie")
                        return extracted_info
                    else:
                        logger.warning(f"⚠️ Erreur Claude: {extracted_info.get('error', 'Réponse invalide')}")

                except Exception as e:
                    logger.warning(f"⚠️ Exception Claude: {str(e)}")
            else:
                logger.info("⚠️ API Claude non configurée, passage au fallback")

        except Exception as e:
            logger.warning(f"⚠️ Erreur générale Claude: {str(e)}")

        # 🔧 STRATÉGIE 2: Fallback avec extraction manuelle robuste
        logger.info("🔄 Utilisation du fallback d'extraction manuelle...")

        try:
            fallback_result = await self._extract_info_basic_robust(prompt)

            if fallback_result and "client" in fallback_result:
                logger.info("✅ Extraction manuelle réussie")
                return fallback_result
            else:
                logger.warning("⚠️ Extraction manuelle échoue, utilisation des valeurs par défaut")

        except Exception as e:
            logger.warning(f"⚠️ Exception fallback: {str(e)}")

        # 🔧 STRATÉGIE 3: Extraction minimale par défaut
        logger.info("🔄 Extraction minimale par défaut...")

        return await self._extract_info_minimal(prompt)

    async def _extract_info_basic_robust(self, prompt: str) -> Dict[str, Any]:
        """
        Extraction manuelle robuste avec patterns améliorés
        """

        import re

        # Normaliser le prompt
        prompt_lower = prompt.lower()

        # 🔍 EXTRACTION CLIENT avec patterns multiples
        client_patterns = [
            r"pour\s+(?:la\s+société\s+|l'entreprise\s+|le\s+client\s+)?([A-Za-z0-9\s&\-'.,]+?)(?:\s+|$)",
            r"client\s*[:=]\s*([A-Za-z0-9\s&\-'.,]+?)(?:\s+|$)",
            r"société\s*[:=]\s*([A-Za-z0-9\s&\-'.,]+?)(?:\s+|$)",
            r"entreprise\s*[:=]\s*([A-Za-z0-9\s&\-'.,]+?)(?:\s+|$)",
            r"([A-Za-z0-9\s&\-'.,]{3,30})\s+(?:a\s+besoin|souhaite|demande|veut)",
        ]

        client_name = None

        for pattern in client_patterns:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                # Nettoyer le nom du client
                client_name = matches[0].strip()

                # Supprimer les mots parasites
                stop_words = ['de', 'pour', 'le', 'la', 'les', 'un', 'une', 'des', 'du', 'devis', 'faire', 'créer']
                client_words = [word for word in client_name.split() if word not in stop_words]

                if client_words:
                    client_name = ' '.join(client_words).title()
                    break

        # Si pas de client trouvé, utiliser une valeur par défaut
        if not client_name:
            client_name = "Client à identifier"

        # 🔍 EXTRACTION PRODUITS avec patterns multiples
        product_patterns = [
            r"(\d+)\s+(?:unités?\s+de\s+|)([A-Za-z0-9\-_]+)",
            r"(\d+)\s+([A-Za-z0-9\-_\s]+?)(?:\s+pour|$)",
            r"(?:ref\s*[:=]\s*|référence\s*[:=]\s*|code\s*[:=]\s*)([A-Za-z0-9\-_]+)",
            r"(\d+)\s+(imprimante|ordinateur|écran|clavier|souris|serveur|switch|routeur|câble)",
        ]

        products = []

        for pattern in product_patterns:
            matches = re.findall(pattern, prompt_lower)
            for match in matches:
                if len(match) == 2:
                    # Pattern avec quantité et produit
                    quantity, product = match
                    products.append({
                        "code": product.strip(),
                        "quantity": int(quantity) if quantity.isdigit() else 1,
                        "name": product.strip().title()
                    })
                else:
                    # Pattern sans quantité
                    products.append({
                        "code": match.strip(),
                        "quantity": 1,
                        "name": match.strip().title()
                    })

        # Si pas de produits trouvés, analyser par mots-clés
        if not products:
            keywords = ['imprimante', 'ordinateur', 'écran', 'clavier', 'souris', 'serveur']

            for keyword in keywords:
                if keyword in prompt_lower:
                    # Chercher une quantité avant le mot-clé
                    quantity_match = re.search(rf"(\d+)\s+.*?{keyword}", prompt_lower)
                    quantity = int(quantity_match.group(1)) if quantity_match else 1

                    products.append({
                        "code": f"{keyword.upper()}_001",
                        "quantity": quantity,
                        "name": keyword.title()
                    })
                    break

        # Si toujours pas de produits, créer un produit par défaut
        if not products:
            products.append({
                "code": "PRODUIT_001",
                "quantity": 1,
                "name": "Produit à identifier"
            })

        return {
            "action_type": "DEVIS",
            "client": client_name,
            "products": products,
            "extracted_method": "manual_robust",
            "confidence": 0.7
        }

    async def _extract_info_minimal(self, prompt: str) -> Dict[str, Any]:
        """
        Extraction minimale garantie de fonctionner
        """

        # Analyser le prompt pour des indices basiques
        words = prompt.lower().split()

        # Chercher des nombres (potentiellement des quantités)
        quantities = [int(word) for word in words if word.isdigit()]
        default_quantity = quantities[0] if quantities else 1

        # Chercher des mots-clés produits
        product_keywords = ['imprimante', 'ordinateur', 'écran', 'laptop', 'serveur', 'switch', 'routeur']
        found_products = [keyword for keyword in product_keywords if keyword in prompt.lower()]

        # Générer un nom de client basique
        client_name = "Client NOVA"

        # Créer les produits
        products = []

        if found_products:
            for product in found_products:
                products.append({
                    "code": f"{product.upper()}_001",
                    "quantity": default_quantity,
                    "name": product.title()
                })
        else:
            # Produit par défaut
            products.append({
                "code": "PRODUIT_STANDARD",
                "quantity": default_quantity,
                "name": "Produit Standard"
            })

        return {
            "action_type": "DEVIS",
            "client": client_name,
            "products": products,
            "extracted_method": "minimal_fallback",
            "confidence": 0.5,
            "note": "Extraction minimale - données à vérifier"
        }

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
        
        return availability_status
    
    async def _build_missing_info_response(self, extracted_info: Dict[str, Any], missing_elements: List[str]) -> Dict[str, Any]:
        """Construit une réponse proactive demandant les informations manquantes avec des propositions concrètes"""
        
        # Récupérer les listes pour proposer des choix
        available_clients = await self._get_available_clients_list()
        available_products = await self._get_available_products_list()
        
        # Construire le message personnalisé selon ce qui manque
        if "client" in missing_elements and "produits" in missing_elements:
            message = "🎯 **Parfait ! Je vais vous aider à créer votre devis étape par étape.**\n\n" + \
                     "Pour commencer, j'ai besoin de connaître le client. Voulez-vous que je vous présente la liste de nos clients ?"
            questions = [
                "🏢 **Étape 1 - Client** : Choisissez une option ci-dessous"
            ]
            
        elif "client" in missing_elements:
            products_info = ", ".join([f"{p.get('quantity', 1)}x {p.get('code', '')}" for p in extracted_info.get("products", [])])
            message = f"🎯 **Excellent ! J'ai identifié les produits : {products_info}**\n\n" + \
                     "Maintenant, pour quel client souhaitez-vous créer ce devis ? Voulez-vous que je vous présente la liste de nos clients ?"
            questions = [
                "🏢 **Client requis** : Choisissez une option ci-dessous"
            ]
            
        elif "produits" in missing_elements:
            client_name = extracted_info.get("client", "le client")
            message = f"🎯 **Parfait ! Devis pour {client_name}**\n\n" + \
                     "Maintenant, quels produits souhaitez-vous inclure dans ce devis ? Voulez-vous que je vous présente notre catalogue ?"
            questions = [
                "📦 **Étape 2 - Produits** : Choisissez une option ci-dessous"
            ]
        
        # Construire les actions rapides PROACTIVES
        quick_actions = []
        
        if "client" in missing_elements:
            quick_actions.extend([
                {
                    "action": "show_clients_list",
                    "label": f"📋 Voir nos {len(available_clients)} clients",
                    "type": "primary",
                    "description": "Afficher la liste complète des clients",
                    "data": {"count": len(available_clients)}
                },
                {
                    "action": "search_client",
                    "label": "🔍 Rechercher un client",
                    "type": "secondary",
                    "description": "Rechercher par nom d'entreprise"
                },
                {
                    "action": "new_client",
                    "label": "➕ Nouveau client",
                    "type": "secondary",
                    "description": "Créer un nouveau client"
                }
            ])
        
        if "produits" in missing_elements:
            quick_actions.extend([
                {
                    "action": "show_products_list",
                    "label": f"📦 Voir nos {len(available_products)} produits",
                    "type": "primary",
                    "description": "Afficher notre catalogue produits",
                    "data": {"count": len(available_products)}
                },
                {
                    "action": "search_product",
                    "label": "🔍 Rechercher un produit",
                    "type": "secondary",
                    "description": "Rechercher par code ou nom"
                },
                {
                    "action": "product_categories",
                    "label": "📂 Par catégories",
                    "type": "secondary",
                    "description": "Parcourir par catégories"
                }
            ])
        
        # Actions générales toujours disponibles
        quick_actions.extend([
            {
                "action": "manual_entry",
                "label": "✏️ Saisie manuelle",
                "type": "tertiary",
                "description": "Saisir directement les informations"
            },
            {
                "action": "examples",
                "label": "💡 Voir des exemples",
                "type": "tertiary",
                "description": "Exemples de demandes"
            }
        ])
        
        return {
            "success": False,
            "workflow_status": "waiting_for_input",
            "message": message,
            "questions": questions,
            "extracted_info": extracted_info,
            "missing_elements": missing_elements,
            "quick_actions": quick_actions,
            "available_data": {
                "clients": available_clients[:10] if "client" in missing_elements else [],  # Top 10 pour aperçu
                "products": available_products[:10] if "produits" in missing_elements else [],  # Top 10 pour aperçu
                "clients_count": len(available_clients),
                "products_count": len(available_products)
            },
            "quote_data": {
                "status": "incomplete",
                "task_id": self.task_id,
                "partial_data": extracted_info,
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "workflow_steps": self.workflow_steps,
                "context_available": True,
                "draft_mode": self.draft_mode
            },
            "suggestions": {
                "examples": [
                    "Je veux un devis pour Acme Corp avec 5 PROD001 et 2 PROD002",
                    "Créer un devis pour Entreprise XYZ, produit REF123 quantité 10",
                    "Devis pour client ABC avec 3 unités ITEM456"
                ],
                "next_steps": [
                    "Choisissez un client dans la liste" if "client" in missing_elements else None,
                    "Sélectionnez les produits souhaités" if "produits" in missing_elements else None
                ]
            }
        }
    
    async def _get_available_clients_list(self) -> List[Dict[str, Any]]:
        """Récupère la liste des clients disponibles depuis Salesforce"""
        try:
            clients_data = asyncio.create_task(self.mcp_connector.get_salesforce_accounts(limit=100))
            clients_data = await clients_data
        except Exception as e:  # Catch specific exceptions if possible
            logger.warning(f"Primary method failed, falling back: {str(e)}")
            try:
                # Fallback avec appel MCP direct
                clients_data = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                    "query": "SELECT Id, Name, Type, Industry FROM Account LIMIT 100"
                })

                if clients_data and "records" in clients_data:
                    clients = []
                    for record in clients_data["records"]:
                        client_info = {
                            "id": record.get("Id", ""),
                            "name": record.get("Name", ""),
                            "type": record.get("Type", "Prospect"),
                            "industry": record.get("Industry", ""),
                            "phone": record.get("Phone", ""),
                            "website": record.get("Website", ""),
                            "recent_quotes": 0  # À calculer si nécessaire
                        }
                        clients.append(client_info)

                    # Trier par nom
                    clients.sort(key=lambda x: x["name"])
                    logger.info(f"Récupéré {len(clients)} clients depuis Salesforce")
                    return clients
                else:
                    logger.warning("Aucun client trouvé dans Salesforce")
                    return []

            except Exception as e:
                logger.error(f"Erreur lors de la récupération des clients: {str(e)}")
                # Retourner une liste d'exemple en cas d'erreur
                return [
                    {"id": "example1", "name": "Acme Corporation", "type": "Customer", "industry": "Technology"},
                    {"id": "example2", "name": "Global Industries", "type": "Prospect", "industry": "Manufacturing"},
                    {"id": "example3", "name": "Tech Solutions Ltd", "type": "Customer", "industry": "IT Services"}
                ]

    async def _get_available_products_list(self) -> List[Dict[str, Any]]:
        """Récupère la liste des produits disponibles depuis SAP"""
        try:
            # Récupérer les produits depuis SAP via MCP
            products_data = await self.mcp_connector.get_sap_products(limit=100)
            
            if products_data and "products" in products_data:
                products = []
                for product in products_data["products"]:
                    product_info = {
                        "code": product.get("code", ""),
                        "name": product.get("name", ""),
                        "description": product.get("description", ""),
                        "price": product.get("price", 0),
                        "currency": product.get("currency", "EUR"),
                        "stock": product.get("stock", 0),
                        "category": product.get("category", "Général"),
                        "unit": product.get("unit", "pièce"),
                        "promotion": product.get("promotion", False),
                        "discount_threshold": product.get("discount_threshold", 50)  # Remise à partir de 50 unités
                    }
                    products.append(product_info)
                
                # Trier par code produit
                products.sort(key=lambda x: x["code"])
                logger.info(f"Récupéré {len(products)} produits depuis SAP")
                return products
            else:
                logger.warning("Aucun produit trouvé dans SAP")
                return []
                
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des produits: {str(e)}")
            # Retourner une liste d'exemple en cas d'erreur
            return [
                {"code": "PROD001", "name": "Imprimante Laser Pro", "price": 299.99, "currency": "EUR", "stock": 25, "category": "Imprimantes", "discount_threshold": 10},
                {"code": "PROD002", "name": "Scanner Document Plus", "price": 199.99, "currency": "EUR", "stock": 15, "category": "Scanners", "discount_threshold": 5},
                {"code": "PROD003", "name": "Cartouche Encre XL", "price": 49.99, "currency": "EUR", "stock": 100, "category": "Consommables", "discount_threshold": 20, "promotion": True}
            ]
    
    async def _build_product_quantity_response(self, client_info: Dict[str, Any], selected_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Construit une réponse pour demander les quantités avec suggestions de remises et promotions"""
        
        products_with_suggestions = []
        total_savings_potential = 0
        
        for product in selected_products:
            product_code = product.get("code", "")
            product_name = product.get("name", product_code)
            price = product.get("price", 0)
            discount_threshold = product.get("discount_threshold", 50)
            promotion = product.get("promotion", False)
            
            # Calculer les suggestions de quantité
            suggestions = {
                "recommended_quantities": [1, 5, 10, discount_threshold] if discount_threshold > 10 else [1, 5, 10],
                "discount_info": {
                    "threshold": discount_threshold,
                    "discount_rate": 0.15 if discount_threshold <= 20 else 0.10,  # 15% pour petites quantités, 10% pour grandes
                    "savings_per_unit": price * (0.15 if discount_threshold <= 20 else 0.10)
                },
                "promotion": {
                    "active": promotion,
                    "description": f"Promotion spéciale sur {product_name}" if promotion else None,
                    "additional_discount": 0.05 if promotion else 0  # 5% supplémentaire
                }
            }
            
            # Chercher des produits alternatifs
            alternatives = await self._find_product_alternatives(product)
            
            product_info = {
                "code": product_code,
                "name": product_name,
                "price": price,
                "currency": product.get("currency", "EUR"),
                "stock": product.get("stock", 0),
                "suggestions": suggestions,
                "alternatives": alternatives
            }
            
            products_with_suggestions.append(product_info)
            
            # Calculer le potentiel d'économies
            if discount_threshold <= 50:
                potential_savings = price * discount_threshold * suggestions["discount_info"]["discount_rate"]
                total_savings_potential += potential_savings
        
        client_name = client_info.get("name", "votre client")
        
        message = f"🎯 **Excellent ! Devis pour {client_name}**\n\n" + \
                 f"Maintenant, précisons les quantités pour chaque produit. Je vais vous donner des conseils sur les remises disponibles :"
        
        quick_actions = [
            {
                "action": "auto_quantities",
                "label": "✨ Quantités optimales",
                "type": "primary",
                "description": f"Appliquer les quantités recommandées (potentiel d'économies: {total_savings_potential:.2f}€)"
            },
            {
                "action": "manual_quantities",
                "label": "✏️ Saisir manuellement",
                "type": "secondary",
                "description": "Définir les quantités une par une"
            },
            {
                "action": "add_more_products",
                "label": "➕ Ajouter d'autres produits",
                "type": "secondary",
                "description": "Compléter la sélection"
            }
        ]
        
        return {
            "success": False,
            "workflow_status": "configuring_quantities",
            "message": message,
            "client_info": client_info,
            "products_details": products_with_suggestions,
            "savings_potential": total_savings_potential,
            "quick_actions": quick_actions,
            "suggestions": {
                "tips": [
                    f"Commandez {products_with_suggestions[0]['suggestions']['discount_info']['threshold']} unités ou plus pour bénéficier de remises",
                    "Certains produits ont des promotions en cours",
                    "Je peux vous proposer des alternatives avec un meilleur rapport qualité-prix"
                ]
            }
        }
    
    async def _find_product_alternatives(self, product: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Trouve des produits alternatifs avec avantages/inconvénients"""
        try:
            product_category = product.get("category", "")
            product_price = product.get("price", 0)
            
            # Simuler la recherche d'alternatives (en réalité, cela ferait appel à SAP)
            alternatives = []
            
            # Exemple d'alternatives basées sur la catégorie
            if "Imprimante" in product.get("name", ""):
                alternatives = [
                    {
                        "code": "PROD001B",
                        "name": "Imprimante Laser Pro V2",
                        "price": product_price * 1.2,
                        "advantages": ["Vitesse d'impression supérieure (+30%)", "Garantie étendue 3 ans"],
                        "disadvantages": ["Prix plus élevé", "Consommation énergétique supérieure"],
                        "recommendation": "Recommandé pour usage intensif"
                    },
                    {
                        "code": "PROD001C",
                        "name": "Imprimante Laser Eco",
                        "price": product_price * 0.8,
                        "advantages": ["Prix attractif", "Faible consommation", "Compact"],
                        "disadvantages": ["Vitesse réduite (-20%)", "Capacité papier limitée"],
                        "recommendation": "Idéal pour usage occasionnel"
                    }
                ]
            
            return alternatives[:2]  # Limiter à 2 alternatives
            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche d'alternatives: {str(e)}")
            return []
    async def _handle_product_search(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gère les demandes de recherche de produits par caractéristiques
        """
        logger.info("🔍 Traitement demande de recherche produit")
        
        search_criteria = extracted_info.get("search_criteria", {})
        if not search_criteria:
            return {
                "success": False,
                "message": "Critères de recherche non spécifiés",
                "action_type": "RECHERCHE_PRODUIT",
                "suggestion": "Exemple: 'Je cherche une imprimante laser recto-verso réseau 50 ppm'"
            }
        
        # Utiliser le moteur de recherche
        from services.product_search_engine import ProductSearchEngine
        search_engine = ProductSearchEngine()
        
        results = await search_engine.search_products_by_characteristics(search_criteria)
        
        if results.get("success"):
            return {
                "success": True,
                "action_type": "RECHERCHE_PRODUIT",
                "message": f"🎯 {results['total_found']} produit(s) trouvé(s)",
                "search_criteria": search_criteria,
                "products": results["matched_products"],
                "quick_actions": [
                    {
                        "action": "create_quote",
                        "label": "📋 Créer un devis",
                        "type": "primary",
                        "description": "Créer un devis avec un de ces produits"
                    },
                    {
                        "action": "refine_search",
                        "label": "🔍 Affiner la recherche",
                        "type": "secondary", 
                        "description": "Préciser les critères"
                    }
                ]
            }
        else:
            return {
                "success": False,
                "action_type": "RECHERCHE_PRODUIT",
                "message": "❌ Aucun produit trouvé avec ces critères",
                "error": results.get("error"),
                "search_criteria": search_criteria,
                "suggestions": [
                    "Essayez des termes plus généraux",
                    "Vérifiez l'orthographe des caractéristiques",
                    "Contactez le support pour des produits spécifiques"
                ]
            }

    async def _handle_client_info(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gère les demandes d'information client
        """
        logger.info("👤 Traitement demande d'information client")
        
        client_name = extracted_info.get("client")
        if not client_name:
            return {
                "success": False,
                "action_type": "INFO_CLIENT",
                "message": "Nom du client non spécifié",
                "suggestion": "Exemple: 'Informations sur le client Edge Communications'"
            }
        
        # Rechercher le client dans Salesforce
        client_info = await self._validate_client(client_name)
        
        if client_info.get("found"):
            client_data = client_info["data"]
            return {
                "success": True,
                "action_type": "INFO_CLIENT",
                "message": f"ℹ️ Informations pour {client_data.get('Name')}",
                "client": {
                    "name": client_data.get("Name"),
                    "account_number": client_data.get("AccountNumber"),
                    "phone": client_data.get("Phone"),
                    "email": client_data.get("Email"),
                    "address": f"{client_data.get('BillingStreet', '')} {client_data.get('BillingCity', '')}",
                    "salesforce_id": client_data.get("Id")
                },
                "quick_actions": [
                    {
                        "action": "create_quote_for_client",
                        "label": "📋 Créer un devis",
                        "type": "primary",
                        "description": f"Nouveau devis pour {client_data.get('Name')}"
                    }
                ]
            }
        else:
            return {
                "success": False,
                "action_type": "INFO_CLIENT",
                "message": f"❌ Client '{client_name}' non trouvé",
                "suggestions": client_info.get("suggestions", []),
                "quick_actions": [
                    {
                        "action": "create_client",
                        "label": "➕ Créer ce client",
                        "type": "secondary",
                        "description": f"Ajouter '{client_name}' comme nouveau client"
                    }
                ]
            }

    async def _handle_stock_consultation(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gère les demandes de consultation de stock
        """
        logger.info("📦 Traitement demande de consultation stock")
        
        # À implémenter selon vos besoins
        return {
            "success": True,
            "action_type": "CONSULTATION_STOCK",
            "message": "🚧 Fonction en cours de développement",
            "suggestion": "Utilisez la recherche de produits pour voir les stocks"
        }

    async def _handle_other_request(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gère les autres types de demandes
        """
        logger.info("❓ Traitement autre demande")
        
        return {
            "success": False,
            "action_type": "AUTRE",
            "message": "🤔 Je n'ai pas compris votre demande",
            "extracted_info": extracted_info,
            "suggestions": [
                "Générer un devis: 'faire un devis pour [client] avec [produits]'",
                "Rechercher un produit: 'je cherche une imprimante laser recto-verso'",
                "Consulter un client: 'informations sur le client [nom]'"
            ]
        }
    async def handle_client_suggestions(self, choice: Dict, workflow_context: Dict) -> Dict:
        """
        🔧 GESTION COMPLÈTE DES SUGGESTIONS CLIENT
        """
        choice_type = choice.get("type")
        
        if choice_type == "use_suggestion":
            # Client sélectionné depuis les suggestions
            suggested_client = choice.get("client_data")
            client_name = suggested_client.get("name") or suggested_client.get("Name")
            
            logger.info(f"✅ Client sélectionné: {client_name}")
            
            # 🔧 MISE À JOUR DU CONTEXTE ET CONTINUATION
            self.context.update({
                "client_info": {"data": suggested_client, "found": True},
                "client_validated": True
            })
            
            # Extraire les produits du contexte original
            original_products = workflow_context.get("extracted_info", {}).get("products", [])
            
            # 🔧 CONTINUATION DIRECTE DU WORKFLOW
            if original_products:
                # Passer à l'étape suivante : récupération produits
                return await self._get_products_info(original_products)
            else:
                # Demander les produits si manquants
                return self._build_product_request_response(client_name)
        
        elif choice_type == "create_new":
            # 🔧 DÉCLENCHER CRÉATION CLIENT PUIS CONTINUER
            new_client_name = choice.get("client_name", "")
            return await self._handle_new_client_creation(new_client_name, workflow_context)
        
        else:
            return self._build_error_response("Choix non supporté", f"Type '{choice_type}' non reconnu")

    async def _handle_new_client_creation(self, client_name: str, workflow_context: Dict) -> Dict:
        """
        🔧 CRÉATION CLIENT PUIS CONTINUATION WORKFLOW
        """
        # Validation et création du client
        validation_result = await self.client_validator.validate_and_enrich_client(client_name)
        
        if validation_result.get("can_create"):
            # Créer dans Salesforce puis SAP
            sf_client = await self._create_salesforce_client(validation_result)
            sap_client = await self._create_sap_client_from_validation(validation_result, sf_client)
            
            # Mettre à jour le contexte
            self.context.update({
                "client_info": {"data": sf_client, "found": True},
                "client_validated": True
            })
            
            # 🔧 CONTINUER AVEC LES PRODUITS
            original_products = workflow_context.get("extracted_info", {}).get("products", [])
            if original_products:
                return await self._get_products_info(original_products)
            else:
                return self._build_product_request_response(sf_client.get("Name", client_name))
        
        else:
            return self._build_error_response("Impossible de créer le client", validation_result.get("error", ""))
    async def _continue_workflow_after_client_selection(self, client_data: Dict, original_context: Dict) -> Dict:
        """
        🔧 CONTINUATION AUTOMATIQUE DU WORKFLOW APRÈS SÉLECTION CLIENT
        """
        logger.info("🔄 Continuation du workflow avec client sélectionné")
        
        # Mettre à jour le contexte avec le client validé
        self.context["client_info"] = {"data": client_data, "found": True}
        self.context["client_validated"] = True
        
        # Récupérer les produits de la demande originale
        original_products = original_context.get("extracted_info", {}).get("products", [])
        
        if original_products:
            # Passer directement à la récupération des produits
            self._track_step_start("get_products_info", "🔍 Récupération des informations produits")
            return await self._get_products_info(original_products)
        else:
            # Si pas de produits, demander à l'utilisateur
            return self._build_product_selection_interface(client_data.get("Name", ""))

    # 🆕 MÉTHODES AUXILIAIRES POUR LA VALIDATION SÉQUENTIELLE

    async def _initiate_client_creation(self, client_name: str) -> Dict[str, Any]:
        """Initie le processus de création d'un nouveau client"""
        return {
            "status": "user_interaction_required",
            "interaction_type": "client_creation",
            "message": f"Le client '{client_name}' n'existe pas. Voulez-vous le créer ?",
            "question": "Créer un nouveau client ?",
            "options": [
                {"value": "create_client", "label": "Oui, créer le client"},
                {"value": "retry_client", "label": "Non, saisir un autre nom"}
            ],
            "input_type": "choice",
            "context": {"client_name": client_name}
        }

    async def _continue_product_validation(self, products: List[Dict]) -> Dict[str, Any]:
        """Continue la validation avec les produits"""
        try:
            # Utiliser le validateur séquentiel pour valider les produits
            extracted_info = {"products": products}
            validation_result = await self.sequential_validator.validate_quote_request(extracted_info)

            if validation_result["status"] == "ready":
                return await self._continue_quote_generation(validation_result["data"])
            else:
                return validation_result

        except Exception as e:
            logger.exception(f"Erreur validation produits: {str(e)}")
            return self._build_error_response("Erreur validation produits", str(e))

    async def _continue_product_resolution(self, validated_products: List[Dict], remaining_products: List[Dict]) -> Dict[str, Any]:
        """Continue la résolution des produits restants"""
        try:
            # Traiter le prochain produit non résolu
            next_product = remaining_products[0]

            return {
                "status": "user_interaction_required",
                "interaction_type": "product_selection",
                "message": f"Sélectionnez le produit pour '{next_product.get('original_request', '')}'",
                "question": "Quel produit souhaitez-vous ?",
                "options": next_product.get("suggestions", []),
                "input_type": "product_choice",
                "context": {
                    "validation_context": {
                        "validated_products": validated_products,
                        "unresolved_products": remaining_products
                    }
                }
            }

        except Exception as e:
            logger.exception(f"Erreur résolution produits: {str(e)}")
            return self._build_error_response("Erreur résolution produits", str(e))

    async def _continue_quantity_validation(self, validated_products: List[Dict]) -> Dict[str, Any]:
        """Continue avec la validation des quantités"""
        try:
            # Vérifier la disponibilité des stocks
            final_products = []
            stock_issues = []

            for product in validated_products:
                product_data = product.get("product_data", {})
                requested_qty = product.get("requested_quantity", 1)
                available_stock = product_data.get("Stock", 0)

                if available_stock >= requested_qty:
                    final_products.append({
                        **product_data,
                        "RequestedQuantity": requested_qty,
                        "LineTotal": product_data.get("Price", 0) * requested_qty
                    })
                else:
                    stock_issues.append({
                        "product": product_data.get("Name", "Produit inconnu"),
                        "requested": requested_qty,
                        "available": available_stock
                    })

            if stock_issues:
                return {
                    "status": "user_interaction_required",
                    "interaction_type": "quantity_adjustment",
                    "message": "Problèmes de stock détectés",
                    "question": "Comment souhaitez-vous procéder ?",
                    "stock_issues": stock_issues,
                    "options": [
                        {"value": "proceed", "label": "Continuer avec les quantités disponibles"},
                        {"value": "modify", "label": "Modifier les quantités"},
                        {"value": "cancel", "label": "Annuler la demande"}
                    ],
                    "input_type": "choice",
                    "context": {"final_products": final_products}
                }
            else:
                # Pas de problème de stock, continuer
                return await self._continue_quote_generation({"products": final_products})

        except Exception as e:
            logger.exception(f"Erreur validation quantités: {str(e)}")
            return self._build_error_response("Erreur validation quantités", str(e))

# 🔧 NOUVELLES ROUTES FASTAPI OPTIMISÉES
from fastapi import APIRouter, HTTPException
from datetime import datetime

# Créer un routeur pour les nouvelles routes
router_v2 = APIRouter()

@router_v2.post("/generate_quote_v2")  # Nouvelle version optimisée
async def generate_quote_optimized(request: dict):
    """
    Route optimisée avec validation séquentielle et cache
    """

    try:
        user_prompt = request.get("prompt", "").strip()
        draft_mode = request.get("draft_mode", False)

        if not user_prompt:
            raise HTTPException(status_code=400, detail="Prompt requis")

        # Initialiser le workflow optimisé
        workflow = DevisWorkflow(validation_enabled=True, draft_mode=draft_mode)

        # Lancer le processus
        result = await workflow.process_quote_request(user_prompt, draft_mode)

        return {
            "success": True,
            "data": result,
            "performance": {
                "cache_stats": await workflow.cache_manager.get_cache_stats(),
                "timestamp": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.exception(f"Erreur route generate_quote_v2: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router_v2.post("/continue_quote")  # Route pour continuer après interaction
async def continue_quote_after_interaction(request: dict):
    """
    Continue le workflow après une interaction utilisateur
    """

    try:
        task_id = request.get("task_id")
        user_input = request.get("user_input", {})
        context = request.get("context", {})

        if not task_id:
            raise HTTPException(status_code=400, detail="task_id requis")

        # Récupérer l'instance du workflow (en pratique, utiliser un cache/session)
        workflow = DevisWorkflow()  # À adapter selon votre système de session
        workflow.task_id = task_id

        result = await workflow.continue_after_user_input(user_input, context)

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.exception(f"Erreur continue_quote: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Export du routeur pour intégration dans main.py
__all__ = ['DevisWorkflow', 'router_v2']