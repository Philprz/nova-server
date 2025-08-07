# workflow/devis_workflow.py - VERSION COMPLÈTE AVEC VALIDATEUR CLIENT
import re
import sys
import io
import os
import json
import logging
import asyncio
from fastapi import APIRouter, HTTPException

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from difflib import SequenceMatcher
from services.llm_extractor import LLMExtractor
from services.mcp_connector import MCPConnector, call_mcp_with_progress, test_mcp_connections_with_progress
from services.progress_tracker import progress_tracker, QuoteTask, TaskStatus
from services.suggestion_engine import SuggestionEngine
from services.client_validator import ClientValidator
from services.websocket_manager import websocket_manager
from services.company_search_service import company_search_service
from utils.client_lister import find_client_everywhere
from services.product_search_engine import ProductSearchEngine
from workflow.client_creation_workflow import client_creation_workflow
from services.price_engine import PriceEngineService
from services.cache_manager import referential_cache
from workflow.validation_workflow import SequentialValidator

# Configuration sécurisée pour Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Configuration des logs avec gestion d'erreur
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
        # Initialisation des composants principaux
        self.mcp_connector = MCPConnector()
        self.llm_extractor = LLMExtractor()
        self.client_validator = ClientValidator() if validation_enabled else None
        self.validation_enabled = validation_enabled
        self.draft_mode = draft_mode
        self.force_production = force_production
        self.task_id = task_id  # Accepter un task_id prédéfini
        self.current_task = None
        self.context = {}
        self.workflow_steps = []

        # Configuration mode production/démo
        self.demo_mode = not force_production
        if force_production:
            logger.info("🔥 MODE PRODUCTION FORCÉ - Pas de fallback démo")

        if task_id:
            self.task_id = task_id
            self.current_task = progress_tracker.get_task(task_id)
            if self.current_task:
                logger.info(f"✅ Tâche récupérée: {task_id}")
            else:
                # Ici, tu dois forcer la création explicite AVEC ce même ID
                logger.warning(f"⚠️ Tâche {task_id} introuvable - création explicite avec l'ID existant")
                self.current_task = progress_tracker.create_task(
                    user_prompt="Génération de devis (créée via fallback)",
                    draft_mode=self.draft_mode,
                    task_id=self.task_id  # <-- garder explicitement le même ID
                )

        else:
            self.current_task = None
            self.task_id = None
            try:
                if task_id:
                    self.current_task = progress_tracker.get_task(task_id)
                    if self.current_task:
                        logger.info(f"✅ Tâche récupérée: {task_id}")
                        # Synchroniser le contexte existant si disponible
                        if hasattr(self.current_task, 'context'):
                            self.context.update(self.current_task.context)
                    else:
                        logger.warning(f"⚠️ Tâche {task_id} introuvable")
            except Exception as e:
                logger.error(f"Erreur lors de la récupération de la tâche {task_id}: {str(e)}")

        # Initialisation des moteurs
        self.suggestion_engine = SuggestionEngine()
        self.client_suggestions = None
        self.product_suggestions = []

        # Initialisation des validateurs et cache
        self.cache_manager = referential_cache
        self.sequential_validator = SequentialValidator(self.mcp_connector, self.llm_extractor)

        # Pré-chargement asynchrone du cache
        try:
            asyncio.create_task(self._initialize_cache())
        except RuntimeError:
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
        if self.task_id:
            # Utiliser le task_id prédéfini
            self.current_task = progress_tracker.create_task(
                user_prompt=prompt,
                draft_mode=self.draft_mode,
                task_id=self.task_id
            )
        else:
            # Créer un nouveau task_id si non fourni
            self.current_task = progress_tracker.create_task(
                user_prompt=prompt,
                draft_mode=self.draft_mode
            )
            self.task_id = self.current_task.task_id
        # Conserver une référence globale pour les WebSockets
        progress_tracker._current_task = self.current_task
        logger.info(f"Tracking initialisé pour la tâche: {self.task_id}")
        return self.task_id
    
    def _track_step_start(self, step_id: str, message: str = ""):
        """Démarre le tracking d'une étape"""
        self._track_step_complete("extract_info", "✅ Informations extraites avec succès")
        if self.current_task:
            self.current_task.start_step(step_id, message)
    
    def _track_step_progress(self, step_id: str, progress: int, message: str = ""):
        """Track et notifie la progression avec WebSocket"""
        if self.current_task:
            if progress == 0:
                self.current_task.start_step(step_id, message)
            elif progress == 100:
                self.current_task.complete_step(step_id, message)
            else:
                self.current_task.update_step_progress(step_id, progress, message)
            
            # Notification WebSocket si disponible
            try:
                asyncio.create_task(websocket_manager.broadcast_to_task(
                    self.current_task.task_id,
                    {
                        "type": "progress_update",
                        "step_id": step_id,
                        "progress": progress,
                        "message": message
                    }
                ))
            except Exception:
                pass  # WebSocket optionnel
    
    def _track_step_complete(self, step_id: str, message: str = ""):
        """Termine une étape avec succès"""
        if self.current_task:
            self.current_task.complete_step(step_id, message)
    
    def _track_step_fail(self, step_id: str, error: str, message: str = ""):
        """Termine une étape en erreur"""
        if self.current_task:
            self.current_task.fail_step(step_id, error, message)

    def _build_error_response(self, error_title: str, error_message: str,
                        context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Construit une réponse d'erreur standardisée

        Args:
            error_title: Titre de l'erreur
            error_message: Message détaillé
            context: Contexte additionnel optionnel

        Returns:
            Dict avec structure d'erreur standardisée
        """

        response = {
            "success": False,
            "status": "error",
            "error": error_message,
            "message": error_message,
            "timestamp": datetime.now().isoformat(),
            "error_type": error_title.lower().replace(" ", "_")
        }

        if self.task_id:
            response["task_id"] = self.task_id

        if context:
            response["context"] = context

        return response

    # 🔧 NOUVELLE MÉTHODE PRINCIPALE AVEC VALIDATION SÉQUENTIELLE
    async def process_quote_request(self, user_prompt: str, draft_mode: bool = False) -> Dict[str, Any]:
        """
        🔧 MÉTHODE PRINCIPALE REFACTORISÉE : extraction, validation, génération du devis
        """
        try:
            # Mode brouillon
            self.draft_mode = draft_mode

            # Nettoyage préventif du cache
            await self.cache_manager.cleanup_expired()

            # PHASE 1: Analyse du prompt
            self._track_step_start("parse_prompt", "🔍 Analyse de votre demande")
            extracted_info = await self._extract_info_from_prompt(user_prompt)
            if not extracted_info:
                return self._build_error_response(
                    "Extraction échouée", "Impossible d'analyser votre demande"
                )
            self._track_step_complete("parse_prompt", "✅ Demande analysée")

            # PHASE 2: Exécution du workflow de devis
            self._track_step_start("quote_workflow", "🚀 Démarrage du workflow de devis")
            workflow_result = await self._process_quote_workflow(extracted_info)

            # Cas : interaction utilisateur nécessaire
            if workflow_result.get("status") == "user_interaction_required":
                # Suivi d'étape
                step = workflow_result.get("step")
                if step:
                    self._track_step_progress(
                        "quote_workflow", 50, f"❗ En attente: {step}"
                    )
                # Ajout du contexte pour reprise
                workflow_result.setdefault("workflow_context", {}).update({
                    "task_id": self.task_id,
                    "extracted_info": extracted_info,
                    "user_prompt": user_prompt,
                    "draft_mode": draft_mode
                })
                return workflow_result

            # Cas : workflow terminé normalement
            self._track_step_complete("quote_workflow", "✅ Workflow de devis terminé")
            return workflow_result

        except Exception as e:
            logger.exception(f"Erreur workflow principal: {e}")
            # Suivi d'erreur global
            self._track_step_fail(
                "quote_workflow", "❌ Erreur système", str(e)
            )
            return self._build_error_response(
                "Erreur système", f"Erreur interne: {str(e)}"
            )


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
        """🔧 Gère la sélection de client par l'utilisateur avec continuation workflow"""
        try:
            action = user_input.get("action")

            if action == "select_existing":
                # Vérification et cache
                selected_client_data = user_input.get("selected_data")
                if not selected_client_data:
                    return self._build_error_response("Sélection invalide", "Données client manquantes")
                await self.cache_manager.cache_client(
                    selected_client_data.get("Name"),
                    selected_client_data
                )

                # Mise à jour du contexte
                self.context["client_info"] = {"data": selected_client_data, "found": True}
                self.context["client_validated"] = True
                logger.info(f"✅ Client sélectionné: {selected_client_data.get('Name','N/A')}")

                # Poursuite du workflow
                workflow_ctx = context.get("workflow_context", {})
                original_products = workflow_ctx.get("extracted_info", {}).get("products", [])
                if original_products:
                    self._track_step_start(
                        "lookup_products",
                        f"📦 Recherche de {len(original_products)} produit(s)"
                    )
                    await self._process_products_retrieval(original_products)
                    return await self._continue_workflow_after_client_selection(
                        selected_client_data,
                        {"extracted_info": {"products": original_products}}
                    )
                else:
                    return self._build_error_response(
                        "Workflow incomplet",
                        "Produits manquants pour continuer"
                    )

            elif action == "create_new":
                client_name = user_input.get("client_name", context.get("original_client_name", ""))
                return await self._initiate_client_creation(client_name)

            elif action == "cancel":
                return {
                    "status": "cancelled",
                    "message": "Demande de devis annulée par l'utilisateur"
                }

            else:
                return self._build_error_response(
                    "Action non reconnue",
                    f"Action: {action}"
                )

        except Exception as e:
            logger.exception(f"Erreur _handle_client_selection: {e}")
            return self._build_error_response("Erreur sélection client", str(e))

            logger.exception(f"Erreur gestion sélection client: {str(e)}")
            return self._build_error_response("Erreur sélection client", str(e))


    async def _search_company_enrichment(self, company_name: str) -> Dict[str, Any]:
        """Enrichissement des données client via INSEE/PAPPERS"""
        try:
           
            # Recherche via agent d'enrichissement
            search_result = await company_search_service.search_company(company_name, max_results=5)

            
            if search_result.get("success") and search_result.get("companies"):
                company = search_result["companies"][0]  # Premier résultat
                
                return {
                    "success": True,
                    "company_data": {
                        "official_name": company.get("denomination", company_name),
                        "siren": company.get("siren", ""),
                        "siret": company.get("siret", ""),
                        "address": {
                            "street": company.get("adresse", ""),
                            "postal_code": company.get("code_postal", ""),
                            "city": company.get("ville", ""),
                            "country": "France"
                        },
                        "activity": {
                            "code": company.get("activite_principale", ""),
                            "label": company.get("libelle_activite", "")
                        },
                        "legal_form": company.get("forme_juridique", ""),
                        "status": company.get("etat", ""),
                        "creation_date": company.get("date_creation", ""),
                        "source": "INSEE/PAPPERS"
                    }
                }
            else:
                # Pas de données enrichies disponibles
                return {
                    "success": False,
                    "message": "Aucune donnée d'enrichissement trouvée",
                    "company_data": {
                        "official_name": company_name,
                        "source": "manual"
                    }
                }
                
        except Exception as e:
            logger.error(f"Erreur enrichissement: {e}")
            return {
                "success": False,
                "error": str(e),
                "company_data": {"official_name": company_name, "source": "manual"}
            }

    ## 4. PRÉVENTION DOUBLONS

    async def _check_duplicates_enhanced(self, client_name: str, enrichment_data: Dict) -> Dict[str, Any]:
        """🔎 Détection avancée des doublons (SIREN + similarité de nom)"""
        try:
            potential_duplicates = []

            # 1️⃣ Recherche par SIREN
            potential_duplicates += await self._search_duplicates_by_siren(enrichment_data)

            # 2️⃣ Recherche par mots du nom
            potential_duplicates += await self._search_duplicates_by_name(client_name)

            # 3️⃣ Nettoyage et scoring
            scored_duplicates = self._deduplicate_and_score(client_name, potential_duplicates)

            # 4️⃣ Filtrage final
            probable_duplicates = [dup for dup in scored_duplicates if dup["similarity_score"] > 0.7]

            if probable_duplicates:
                return {
                    "has_duplicates": True,
                    "duplicates": probable_duplicates,
                    "duplicate_count": len(probable_duplicates),
                    "requires_user_choice": True,
                    "message": f"⚠️ {len(probable_duplicates)} client(s) similaire(s) détecté(s)",
                    "actions": [
                        {"action": "use_existing", "label": "📋 Utiliser client existant"},
                        {"action": "create_anyway", "label": "➕ Créer quand même"},
                        {"action": "cancel", "label": "❌ Annuler"}
                    ]
                }
            else:
                return {"has_duplicates": False, "message": "✅ Aucun doublon détecté"}

        except Exception as e:
            logger.error(f"❌ Erreur vérification doublons: {e}")
            return {"has_duplicates": False, "error": str(e)}


    async def _search_duplicates_by_siren(self, enrichment_data: Dict) -> list:
        """🔍 Recherche des doublons via le SIREN"""
        siren = enrichment_data.get("company_data", {}).get("siren", "")
        if not siren:
            return []
        
        query = f"""
            SELECT Id, Name, AccountNumber, FederalTaxID 
            FROM Account 
            WHERE FederalTaxID LIKE '%{siren}%'
        """
        result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": query})
        return result.get("data", []) if result.get("success") else []


    async def _search_duplicates_by_name(self, client_name: str) -> list:
        """🔍 Recherche des doublons par mots significatifs dans le nom"""
        words = {word for word in client_name.split() if len(word) > 3}
        if not words:
            return []
        
        conditions = " OR ".join([f"Name LIKE '%{word}%'" for word in words])
        query = f"""
            SELECT Id, Name, AccountNumber 
            FROM Account 
            WHERE {conditions}
        """
        result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": query})
        return result.get("data", []) if result.get("success") else []


    def _deduplicate_and_score(self, client_name: str, duplicates: list) -> list:
        """🧠 Déduplique et ajoute un score de similarité"""
        seen_ids = set()
        unique = []

        for dup in duplicates:
            account_id = dup.get("Id")
            if account_id and account_id not in seen_ids:
                seen_ids.add(account_id)
                dup["similarity_score"] = self._calculate_similarity(
                    client_name.upper().strip(),
                    dup.get("Name", "").upper().strip()
                )
                unique.append(dup)
        return unique

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calcul simple de similarité entre deux noms"""
        try:
            
            return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
        except:
            return 0.0
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

    async def process_prompt(self, user_prompt: str, task_id: str = None) -> Dict[str, Any]:
        """IMPORTANT: Utiliser le task_id fourni, ne jamais le régénérer"""
        """
        Traite un prompt avec tracking de progression
        """
        if task_id:
            self.task_id = task_id
            logger.info(f"✅ Utilisation du task_id fourni: {task_id}")
        extracted_info: Optional[Dict[str, Any]] = None
        """Process le prompt utilisateur via LLM et workflow"""
        try:
            # 🔧 MODIFICATION : Utiliser le task_id fourni si disponible
            if task_id:
                self.task_id = task_id
                # Récupérer la tâche existante créée par start_quote_workflow
                self.current_task = progress_tracker.get_task(task_id)
                if not self.current_task:
                # Si pas trouvée (ne devrait pas arriver), la créer
                    self.current_task = progress_tracker.create_task(
                    user_prompt=user_prompt,
                    draft_mode=self.draft_mode,
                    task_id=task_id
                    )

            # Si pas de task existante, en créer une nouvelle
            if not self.current_task:
                self.task_id = self._initialize_task_tracking(user_prompt)

            logger.info(f"=== DÉMARRAGE WORKFLOW - Tâche {self.task_id} ===")

            # 🔧 MODIFICATION : Démarrer le tracking de progression
            self._track_step_start("parse_prompt", "🔍 Analyse de votre demande")

            # Extraction des informations (code existant adapté)
            extracted_info = await self.llm_extractor.extract_quote_info(user_prompt)
            if not extracted_info:
                raise ValueError("Extraction des informations échouée")
            self._track_step_progress("parse_prompt", 100, "✅ Demande analysée")
            self._track_step_complete("parse_prompt")

            # 🔧 MODIFICATION : Vérification du mode production
            mode = "PRODUCTION" if not self.draft_mode else "DRAFT"
            logger.info(f"🔧 MODE {mode} ACTIVÉ")

            # Vérifier les connexions
            self._track_step_start("validate_input", "🔧 Vérification des connexions")
            connections_ok = await self._check_connections()
            if not connections_ok:
                raise Exception("Connexions SAP/Salesforce indisponibles")
            self._track_step_complete("validate_input", "✅ Connexions validées")

            # Router selon le type d'action
            action_type = extracted_info.get("action_type", "DEVIS")

            if action_type == "DEVIS":
                try:
                    result = await self._process_quote_workflow(extracted_info)
                    if result.get("status") == "client_validation_required":
                        return result
                except Exception as e:
                    logger.error(f"❌ Erreur process_prompt: {str(e)}")
                    return {"success": False, "error": str(e)}
            else:
                result = await self._process_other_action(extracted_info)


            # 🔧 CORRECTION : Ne marquer comme terminée QUE si workflow réellement terminé
            if self.current_task:
                if result.get("status") == "user_interaction_required":
                    # Laisser la tâche en attente d'interaction - ne pas la terminer
                    logger.info(f"⏸️ Tâche {self.task_id} en attente d'interaction utilisateur")
                else:
                    # Workflow terminé normalement
                    progress_tracker.complete_task(self.task_id, result)
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur process_prompt: {str(e)}", exc_info=True)
            if self.current_task:
                progress_tracker.fail_task(self.task_id, str(e))
            raise
    
    async def _execute_full_workflow(self, prompt: str) -> Dict[str, Any]:
        """
        🔧 MÉTHODE AJOUTÉE : Wrapper pour exécution complète du workflow
        
        ⚠️ NOTE : Cette méthode est appelée dans process_prompt mais semble redondante
        car le workflow principal est déjà traité par _process_quote_workflow
        
        Args:
            prompt: Demande utilisateur originale
            
        Returns:
            Dict avec le résultat complet du workflow
        """
        try:
            logger.info("🔄 Exécution du workflow complet")
            
            # 🔧 ATTENTION : Cette méthode ne devrait pas être nécessaire
            # Le workflow est déjà traité dans process_prompt par :
            # - _process_quote_workflow pour les devis
            # - _process_other_action pour les autres actions
            
            # Si cette méthode est appelée, retourner le résultat déjà calculé
            if hasattr(self, '_current_workflow_result'):
                logger.info("✅ Retour du résultat déjà calculé")
                return self._current_workflow_result
            
            # Sinon, re-exécuter l'extraction et le workflow de base
            logger.warning("⚠️ Ré-exécution du workflow - ceci indique un problème de logique")
            
            # Extraction de base
            extracted_info = await self.llm_extractor.extract_quote_info(prompt)
            
            # Router selon le type d'action
            action_type = extracted_info.get("action_type", "DEVIS")
            
            # Exécuter le workflow approprié et sauvegarder le résultat
            if action_type == "DEVIS":
                self._current_workflow_result = await self._process_quote_workflow(extracted_info)
            else:
                self._current_workflow_result = await self._process_other_action(extracted_info)

            # Utiliser le résultat sauvegardé (pas de re-calcul)
            result = self._current_workflow_result
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur _execute_full_workflow: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Erreur lors de l'exécution du workflow complet"
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
            
            extracted_info = await self._extract_info_unified(prompt, "standard")
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
            
            client_info = await unified_validator.validate_client_complete(extracted_info.get("client"))
            # CORRECTION : Gérer les suggestions client MÊME si trouvé (choix multiple)
            if client_info.get("suggestions") and len(client_info["suggestions"]) > 1:
                self._track_step_progress("verify_client_info", 50, "Plusieurs clients trouvés - sélection requise")
                return {
                    "status": "suggestions_required",
                    "type": "client_suggestions", 
                    "message": f"{len(client_info['suggestions'])} clients trouvés pour '{client_name}'",
                    "suggestions": client_info["suggestions"],
                    "workflow_context": {
                        "extracted_info": extracted_info,
                        "task_id": self.task_id,
                        "step": "client_validation"
                    }
                }
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

                # Ajout de log détaillé avant envoi à websocket (dans _handle_client_not_found_with_validation)
                # Cette fonction doit inclure le logging demandé, ex:
                # logger.info(f"▶️ [WORKFLOW] Demande de validation utilisateur pour le client '{client_name}'")
                # logger.debug(f"🔍 [WORKFLOW] Données d'interaction préparées: {json.dumps(interaction_data, indent=2, ensure_ascii=False)}")
                # ...

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
            
            # ✅ NOUVEAU CODE AVEC PRICE ENGINE
            # Étape 1: Récupérer les données techniques
            self._track_step_start("get_products_info", "Récupération des informations produits...")
            products_info = await self._get_products_info(extracted_info.get("products", []))
            self._track_step_complete("get_products_info", f"{len(products_info)} produit(s) trouvé(s)")

            # Étape 2: Calculer les prix avec le Price Engine
            self._track_step_start("calculate_prices", "Calcul des prix avec Price Engine...")
            products_info = await self._apply_price_calculations(products_info, client_info.get("data", {}))
            self._track_step_complete("calculate_prices", "Prix calculés avec succès")

            # Étape 3: Calculer le total
            total_amount = sum(p.get("line_total", 0) for p in products_info if not p.get("error"))
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
            # ✅ NOUVEAU CODE AVEC PRICE ENGINE

            self._track_step_start("calculate_prices", "Calcul des prix avec Price Engine...")
            price_engine = PriceEngineService()

            # Calculer les prix avec le nouveau moteur
            pricing_result = await price_engine.calculate_quote_pricing({
                "client_data": client_data,
                "products": products_data,
                "special_conditions": extracted_info.get("conditions", {})
            })

            # Mettre à jour les produits avec les nouveaux prix
            products_data = pricing_result.get("updated_products", products_data)
            total_amount = pricing_result.get("total_amount", 0.0)

            self._track_step_progress("calculate_prices", 90, "Prix calculés avec Price Engine")
            
            # Étape 3.5: Produits prêts
            self._track_step_complete("calculate_prices", "Prix finalisés")
            self._track_step_complete("product_ready", f"{len([p for p in products_info if 'error' not in p])} produits confirmés")
            
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
        """
        Gère le cas où un client n'est pas trouvé - VERSION COMPLÈTE CORRIGÉE
        
        CONSERVE :
        - Logique de validation et enrichissement
        - Création SAP/Salesforce automatique en mode POC
        - Workflow complet avec continuation
        
        AJOUTE :
        - Validation utilisateur optionnelle
        - Gestion robuste des erreurs
        - Continuation automatique du workflow
        """
        logger.info(f"🔍 Traitement client non trouvé avec validation complète: {client_name}")
        
        # CORRECTION 1: Vérifier si client_name est valide
        if not client_name or client_name.strip() == "":
            logger.warning("❌ Nom de client vide ou None")
            return {
                "client_created": False,
                "error": "Nom de client manquant",
                "suggestion": "Vérifiez que le prompt contient un nom de client valide",
                "workflow_context": {
                    "task_id": self.task_id,
                    "extracted_info": extracted_info,
                    "step": "client_validation_failed"
                }
            }
        
        try:
            # === ÉTAPE 1: ENRICHISSEMENT ET VALIDATION DONNÉES ===
            logger.info(f"🔍 Étape 1: Enrichissement données pour {client_name}")
            
            # Détecter le pays probable
            country = self._detect_country_from_name(client_name)
            logger.info(f"Pays détecté: {country}")
            
            # CONSERVÉ: Validation avec le validateur client
            validation_result = None
            if self.client_validator:
                try:
                    logger.info("🔍 Validation via ClientValidator...")
                    validation_result = await self.client_validator.validate_and_enrich_client(client_name)
                    logger.info(f"✅ Validation terminée: {validation_result.get('can_create', False)}")
                except Exception as e:
                    logger.warning(f"⚠️ Erreur validation client: {str(e)}")
                    validation_result = {"can_create": True, "warnings": [str(e)]}
            
            # CONSERVÉ: Enrichissement externe via company_search_service
            enrichment_data = {}
            try:
                logger.info("🔍 Enrichissement externe...")
                enrichment_result = await self._search_company_enrichment(client_name)
                if enrichment_result.get("success"):
                    enrichment_data = enrichment_result.get("company_data", {})
                    logger.info(f"✅ Données enrichies récupérées pour {client_name}")
            except Exception as e:
                logger.warning(f"⚠️ Erreur enrichissement: {str(e)}")
            
            # === ÉTAPE 2: VÉRIFICATION DOUBLONS ===
            logger.info("🔍 Étape 2: Vérification doublons avancée")
            
            duplicate_check = {}
            try:
                duplicate_check = await self._check_duplicates_enhanced(client_name, enrichment_data)
                if duplicate_check.get("has_duplicates"):
                    logger.warning(f"⚠️ Doublons détectés: {duplicate_check.get('duplicate_count', 0)}")
                    
                    # NOUVEAU: Gestion des doublons avec choix utilisateur
                    return {
                        "client_created": False,
                        "status": "duplicates_found",
                        "duplicate_check": duplicate_check,
                        "enrichment_data": enrichment_data,
                        "validation_result": validation_result,
                        "workflow_context": {
                            "task_id": self.task_id,
                            "extracted_info": extracted_info,
                            "step": "duplicate_resolution_required"
                        },
                        "user_action_required": True,
                        "message": f"Doublons potentiels trouvés pour '{client_name}'"
                    }
            except Exception as e:
                logger.warning(f"⚠️ Erreur vérification doublons: {str(e)}")
            
            # === ÉTAPE 3: VALIDATION UTILISATEUR (MODE POC = AUTO-APPROBATION) ===
            logger.info("🔍 Étape 3: Validation utilisateur")
            
            # NOUVEAU: Demande validation utilisateur
            try:
                validation_request = await self._request_user_validation_for_client_creation(
                    client_name, 
                    {
                        "enrichment_data": enrichment_data,
                        "validation_result": validation_result,
                        "duplicate_check": duplicate_check
                    }
                )
                
                # En mode POC, auto-approuver
                if validation_request.get("status") != "approved":
                    logger.warning("⚠️ ATTENTION: Client non trouvé avec find_client_everywhere - Création bloquée")
                    validation_request["status"] = "requires_user_confirmation"
                    validation_request["requires_explicit_approval"] = True
                    
            except Exception as e:
                logger.warning(f"⚠️ Erreur validation utilisateur: {str(e)}")
                # Fallback: approuver automatiquement
                validation_request = {"status": "approved", "auto_approved": True, "fallback": True}
            
            # === ÉTAPE 4: CRÉATION CLIENT COMPLÈTE ===
            if validation_request.get("status") == "approved":
                logger.info("🚀 Étape 4: Création client approuvée")
                
                # Préparer les données client enrichies
                client_data = {
                    "company_name": client_name.strip(),
                    "billing_country": country,
                    "email": f"contact@{client_name.replace(' ', '').lower()}.com",
                    "phone": "+33 1 00 00 00 00" if country == "FR" else "+1 555 000 0000"
                }
                
                # Fusionner avec les données enrichies
                if enrichment_data:
                    client_data.update({
                        "official_name": enrichment_data.get("official_name", client_name),
                        "siren": enrichment_data.get("siren", ""),
                        "siret": enrichment_data.get("siret", ""),
                        "address": enrichment_data.get("address", {}),
                        "activity": enrichment_data.get("activity", {}),
                        "enriched": True
                    })
                
                # CONSERVÉ: Création dans Salesforce d'abord
                logger.info("💾 Création Salesforce...")
                sf_client = await self._create_salesforce_client_from_validation(client_data, validation_result or {})
                
                if sf_client.get("success"):
                    logger.info(f"✅ Client Salesforce créé: {sf_client.get('id')}")
                    
                    # CONSERVÉ: Création dans SAP ensuite
                    logger.info("💾 Création SAP...")
                    sap_client = await self._create_sap_client_from_validation(client_data, sf_client)
                    
                    if sap_client.get("success"):
                        logger.info(f"✅ Client SAP créé: {sap_client.get('data', {}).get('CardCode')}")
                    
                    # === ÉTAPE 5: CONTINUATION WORKFLOW AUTOMATIQUE ===
                    logger.info("🔄 Étape 5: Continuation automatique du workflow")
                    
                    # Mettre à jour le contexte avec le client créé
                    client_final_data = sf_client.get("data", {})
                    self.context.update({
                        "client_info": {"data": client_final_data, "found": True, "created": True},
                        "client_validation": validation_result,
                        "sap_client": sap_client
                    })
                    
                    # NOUVEAU: Continuation automatique avec les produits si disponibles
                    if extracted_info and extracted_info.get("products"):
                        logger.info("🔄 Continuation avec récupération produits...")
                        try:
                            products_result = await self._process_products_retrieval(extracted_info["products"])
                            self.context["products_info"] = products_result.get("products", [])
                            logger.info(f"✅ Workflow continué - {len(products_result.get('products', []))} produit(s) traités")
                        except Exception as e:
                            logger.warning(f"⚠️ Erreur continuation produits: {str(e)}")
                    
                    return {
                        "client_created": True,
                        "client_info": {"data": client_final_data, "found": True, "created": True},
                        "validation_details": validation_result,
                        "sap_client": sap_client,
                        "enrichment_data": enrichment_data,
                        "duplicate_check": duplicate_check,
                        "workflow_continued": bool(extracted_info and extracted_info.get("products")),
                        "message": f"Client '{client_name}' créé avec succès et workflow continué"
                    }
                else:
                    logger.error(f"❌ Erreur création Salesforce: {sf_client.get('error')}")
                    return {
                        "client_created": False,
                        "error": f"Erreur création Salesforce: {sf_client.get('error')}",
                        "validation_details": validation_result,
                        "enrichment_data": enrichment_data
                    }
            else:
                # === ÉTAPE 5 ALTERNATIVE: VALIDATION UTILISATEUR REQUISE ===
                logger.info("⏸️ Validation utilisateur requise")
                return {
                    "client_created": False,
                    "status": "user_validation_required",
                    "validation_request": validation_request,
                    "enrichment_data": enrichment_data,
                    "validation_details": validation_result,
                    "duplicate_check": duplicate_check,
                    "workflow_context": {
                        "task_id": self.task_id,
                        "extracted_info": extracted_info,
                        "step": "awaiting_user_validation"
                    },
                    "message": f"Validation utilisateur requise pour créer '{client_name}'"
                }
                    
        except Exception as e:
            logger.exception(f"❌ Erreur lors de la gestion client non trouvé: {str(e)}")
            return {
                "client_created": False,
                "error": f"Erreur système: {str(e)}",
                "workflow_context": {
                    "task_id": self.task_id,
                    "extracted_info": extracted_info,
                    "step": "error_handling"
                }
            }

    # === MÉTHODES D'APPUI REQUISES ===

    def _detect_country_from_name(self, client_name: str) -> str:
        """Détecte le pays probable à partir du nom du client - VERSION ROBUSTE"""
        if not client_name:
            return "FR"  # Par défaut
            
        client_name_lower = client_name.lower()
        
        # Indicateurs USA
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
        
        # Par défaut, France
        return "FR"

    async def _request_user_validation_for_client_creation(self, client_name: str, context_data: Dict) -> Dict[str, Any]:
        """Demande validation utilisateur pour création client - MÉTHODE MANQUANTE AJOUTÉE"""
        try:
            logger.info(f"📩 Demande validation création client: {client_name}")
            
            enrichment_data = context_data.get("enrichment_data", {})
            validation_result = context_data.get("validation_result", {})
            duplicate_check = context_data.get("duplicate_check", {})
            
            # MODE POC: Auto-approuver si données suffisantes
            if enrichment_data.get("siren") or validation_result.get("can_create"):
                logger.info("✅ Auto-approbation avec données suffisantes")
                return {
                    "status": "approved",
                    "method": "auto_approved_with_data",
                    "confidence": "high",
                    "reason": "Données enrichies disponibles"
                }
            
            # Auto-approuver en mode fallback (POC)
            logger.info("⚠️ Auto-approbation mode POC")
            return {
                "status": "approved", 
                "method": "auto_approved_poc",
                "confidence": "medium",
                "reason": "Mode POC activé"
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur validation utilisateur: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
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
        """
        Crée le devis après confirmation de l'utilisateur

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

        # 🆕 ENRICHISSEMENT CLIENT
        client_name = client_info.get("data", {}).get("Name", "")
        if client_name and not client_info.get("enriched"):
            logger.info("🔍 Enrichissement informations client avant création devis")
            try:
                company_info = await self._search_company_info(client_name)
                if company_info.get("found"):
                    client_info["enriched_data"] = company_info
                    client_info["enriched"] = True
                    self.context["client_info"] = client_info
                    logger.info(f"✅ Client enrichi avec SIREN: {company_info.get('siren', 'N/A')}")
            except Exception as e:
                logger.warning(f"Enrichissement client échoué: {str(e)}")

        # 🆕 RECHERCHE ALTERNATIVES PRODUITS
        enhanced_products = []
        for i, product in enumerate(products_info):
            if product.get("error") or not product.get("found"):
                product_name = product.get("original_name", product.get("name", ""))
                if product_name:
                    logger.info(f"🔍 Recherche alternatives pour produit: {product_name}")
                    try:
                        alternatives = await self._find_similar_products(product_name)
                        if alternatives:
                            return {
                                "status": "user_interaction_required",
                                "interaction_type": "product_selection",
                                "message": f"Alternatives trouvées pour '{product_name}'",
                                "product_index": i,
                                "alternatives": alternatives,
                                "context": {
                                    "client_info": client_info,
                                    "products_info": products_info,
                                    "confirmed": confirmed
                                }
                            }
                    except Exception as e:
                        logger.warning(f"Recherche alternatives échouée: {str(e)}")
            enhanced_products.append(product)

        self.context["products_info"] = enhanced_products

        # ===== Poursuivre avec la création du devis =====
        logger.info("Confirmation approuvée, poursuite de la création du devis")
        self._track_step_start("prepare_quote", "Création du devis après confirmation...")

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

        self._track_step_complete("prepare_quote", "Devis créé avec succès")

        # 🧾 Réponse enrichie
        response = {
            "status": "success",
            "message": "Devis créé avec succès",
            "quote_data": quote_result.get("quote_data", {}),
            "client_enrichment": client_info.get("enriched_data"),
            "alternatives_used": any(p.get("alternative_selected") for p in enhanced_products)
        }

        # 🔁 Finalisation (restaurée)
        if self.current_task and self.task_id:
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
            
            # Données minimales pour éviter erreurs de validation
            opportunity_data = {
                'Name': f'NOVA-{today.strftime("%Y%m%d-%H%M%S")}',
                'StageName': 'Prospecting',  # Étape standard qui existe toujours
                'CloseDate': due_date,
                'Type': 'New Customer'
            }
            
            # Ajouter AccountId seulement si client valide
            if client_id and client_id != "":
                opportunity_data['AccountId'] = client_id
            else:
                # Créer avec compte générique ou utiliser un compte par défaut
                logger.warning("⚠️ Pas de client Salesforce - création avec compte générique")
                # Utiliser un compte par défaut ou créer l'opportunité sans compte
                pass
            
            # Ajouter montant seulement si positif
            if total_amount > 0:
                opportunity_data['Amount'] = total_amount
            
            # Ajouter description avec gestion d'erreurs
            try:
                # CORRECTION: Définir sap_ref correctement
                sap_ref = ""
                if sap_quote and sap_quote.get('doc_num'):
                    sap_ref = f" (SAP DocNum: {sap_quote.get('doc_num')})"
                
                opportunity_data['Description'] = f'Devis généré automatiquement via NOVA{sap_ref} - Mode: {"Brouillon" if self.draft_mode else "Définitif"}'
                opportunity_data['LeadSource'] = 'NOVA Middleware'
                opportunity_data['Probability'] = 50 if not self.draft_mode else 25
            except Exception as e:
                logger.warning(f"⚠️ Erreur ajout métadonnées: {e}")
            
            logger.info("Création opportunité Salesforce...")
            logger.info(f"Données: {json.dumps(opportunity_data, indent=2, ensure_ascii=False)}")
            
            salesforce_quote = None
            
            try:
                # Utiliser try/catch spécifique pour Salesforce
                opportunity_result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
                    "sobject": "Opportunity",
                    "data": opportunity_data
                })
                
                logger.info(f"📊 Résultat brut Salesforce: {opportunity_result}")
                
                # Validation robuste du résultat
                if opportunity_result is None:
                    raise Exception("Salesforce a retourné None")
                
                if not isinstance(opportunity_result, dict):
                    raise Exception(f"Salesforce a retourné un type inattendu: {type(opportunity_result)}")
                
                # Vérifier succès avec plusieurs critères
                success_indicators = [
                    opportunity_result.get("success") is True,
                    "id" in opportunity_result and opportunity_result["id"],
                    "error" not in opportunity_result
                ]
                
                if any(success_indicators) and opportunity_result.get("id"):
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
                    # Analyser l'erreur spécifique
                    error_msg = opportunity_result.get("error", "Erreur Salesforce non spécifiée")
                    logger.error(f"❌ Erreur création opportunité Salesforce: {error_msg}")
                    
                    salesforce_quote = {
                        "success": False,
                        "error": error_msg,
                        "raw_response": opportunity_result,
                        "attempted_data": opportunity_data
                    }
                        
            except Exception as e:
                logger.exception(f"❌ EXCEPTION lors de la création Salesforce: {str(e)}")
                salesforce_quote = {
                    "success": False,
                    "error": f"Exception Salesforce: {str(e)}",
                    "exception_type": type(e).__name__
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
        
        # CORRECTION CRITIQUE: Vérifier les conditions d'erreur AVANT de construire la réponse
        if not client_info.get("found", False):
            return {
                "success": False,
                "status": "error",
                "message": f"Client non trouvé: {client_info.get('error', 'Erreur inconnue')}",
                "error": client_info.get('error', 'Client non trouvé'),
                "next_steps": "Veuillez vérifier le nom du client et réessayer."
            }
        
        if not quote_result.get("success", False):
            return {
                "success": False,
                "status": "error",
                "message": f"Échec de la création du devis: {quote_result.get('error', 'Erreur inconnue')}",
                "error": quote_result.get('error', 'Erreur création devis'),
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
                # === AUCUN CLIENT TROUVÉ - SUGGESTIONS ===
                # Aucune suggestion, proposer création
                logger.info(f"❌ Aucune suggestion trouvée pour: {client_name}")
                # 🆕 TENTATIVE DE CRÉATION AUTOMATIQUE
                creation_result = await self._create_client_automatically(client_name)

                if creation_result.get("created"):
                    logger.info(f"✅ Client '{client_name}' créé automatiquement !")
                    return {
                        "found": True,
                        "data": creation_result.get("client_data"),
                        "source": "auto_created",
                        "message": creation_result.get("message"),
                        "auto_created": True
                    }

                logger.warning(f"⚠️ Création automatique échouée: {creation_result.get('error')}")
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
            
            # Calculer la date limite
            cutoff_date = datetime.now() - timedelta(hours=hours)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            # Rechercher dans SAP avec filtre date et client
            
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
        """
        Récupère UNIQUEMENT les informations techniques des produits depuis SAP
        Le calcul des prix est délégué au Price Engine
        """
        if not products:
            logger.warning("Aucun produit spécifié")
            return []
            
        logger.info(f"🔍 RECHERCHE PRODUITS (sans calcul prix): {products}")
        enriched_products = []

        for product in products:
            try:
                product_code = product.get("code", "")
                product_name = product.get("name", "")
                
                # PROBLÈME ICI : Si product_code est vide, on ne fait rien
                if product_code:
                    # Recherche par code exact (existant)
                    product_details = await MCPConnector.call_sap_mcp("sap_get_product_details", {
                        "item_code": product_code
                    })
                elif product_name:
                    # NOUVELLE LOGIQUE : Recherche par nom
                    logger.info(f"🔍 Produit sans code, recherche par nom: {product_name}")
                    product_details = await self._search_product_by_name_only(product_name)
                else:
                    logger.error(f"❌ Produit sans code ni nom: {product}")
                    enriched_products.append({
                        "code": "",
                        "quantity": product.get("quantity", 1),
                        "error": "Produit sans code ni nom"
                    })
                    continue
                
                # Calculer le stock total (logique conservée car technique)
                total_stock = self._extract_stock_from_sap_data(product_details)
                
                # Récupérer l'ID Salesforce
                salesforce_id = await self._find_product_in_salesforce(product["code"])
                
                # ✅ NOUVEAU : Produit enrichi SANS calcul de prix
                enriched_product = {
                    "code": product["code"],
                    "quantity": product["quantity"],
                    "name": product_details.get("ItemName", "Unknown"),
                    "stock": total_stock,
                    "salesforce_id": salesforce_id,
                    # ✅ Conserver les données SAP brutes pour le Price Engine
                    "sap_raw_data": product_details,
                    # ✅ Prix à null - sera calculé par le Price Engine
                    "unit_price": None,
                    "line_total": None,
                    "price_calculated": False
                }
                
                enriched_products.append(enriched_product)
                logger.info(f"✅ Produit enrichi (sans prix): {product['code']} - Stock: {total_stock}")
                
            except Exception as e:
                logger.error(f"Erreur récupération produit {product['code']}: {str(e)}")
                enriched_products.append({
                    "code": product["code"],
                    "quantity": product["quantity"],
                    "error": str(e)
                })
        
        return enriched_products
    async def _find_similar_products(self, product_name: str) -> List[Dict[str, Any]]:
        """
        Trouve des produits similaires basés sur des mots-clés
        """
        if not product_name:
            return []
            
        try:
            # Extraire des mots-clés intelligents
            keywords = self._extract_product_keywords(product_name)
            similar_products = []
            
            for keyword in keywords[:2]:  # Limiter à 2 mots-clés
                search_result = await self.mcp_connector.call_mcp(
                    "sap_mcp",
                    "sap_search",
                    {
                        "search_term": keyword,
                        "search_fields": ["ItemName", "U_Description"],
                        "limit": 3
                    }
                )
                
                if search_result.get("success") and search_result.get("results"):
                    for product in search_result["results"]:
                        if product not in similar_products:  # Éviter les doublons
                            similar_products.append({
                                "code": product.get("ItemCode"),
                                "name": product.get("ItemName"),
                                "price": float(product.get("AvgPrice", 0)),
                                "description": product.get("U_Description", ""),
                                "matched_keyword": keyword
                            })
            
            logger.info(f"🔍 {len(similar_products)} alternatives trouvées pour '{product_name}'")
            return similar_products[:5]  # Limiter à 5 alternatives max
            
        except Exception as e:
            logger.error(f"Erreur recherche alternatives: {str(e)}")
            return []
    async def _search_product_by_name_only(self, product_name: str) -> Dict[str, Any]:
        """
        Recherche un produit SAP par nom uniquement (quand pas de code)
        """
        try:
            logger.info(f"🔍 Recherche SAP par nom: {product_name}")
            
            # Utiliser la méthode MCP de recherche générale
            search_result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_search",
                {
                    "search_term": product_name,
                    "search_fields": ["ItemName", "U_Description"],
                    "limit": 5
                }
            )
            
            if search_result.get("success") and search_result.get("results"):
                # Prendre le premier résultat comme meilleure correspondance
                best_match = search_result["results"][0]
                
                logger.info(f"✅ Produit trouvé par nom: {best_match.get('ItemName')} ({best_match.get('ItemCode')})")
                
                # Retourner au format attendu par _get_products_info
                return {
                    "ItemCode": best_match.get("ItemCode"),
                    "ItemName": best_match.get("ItemName"),
                    "OnHand": best_match.get("OnHand", 0),
                    "AvgPrice": best_match.get("AvgPrice", 0),
                    "U_Description": best_match.get("U_Description", ""),
                    "found_by": "name_search"
                }
            elif search_result.get("success"):
                # Recherche réussie mais aucun résultat
                logger.warning(f"❌ Aucun produit SAP trouvé pour: {product_name}")
                return {
                    "error": f"Aucun produit trouvé pour '{product_name}'"
                }
            else:
                # Erreur dans la recherche MCP
                logger.error(f"❌ Erreur recherche MCP: {search_result.get('error')}")
                return {
                    "error": f"Erreur recherche SAP: {search_result.get('error')}"
                }
                
        except Exception as e:
            logger.exception(f"❌ Exception recherche par nom: {str(e)}")
            return {
                "error": f"Erreur système: {str(e)}"
            }
    def _extract_stock_from_sap_data(self, product_details: Dict) -> float:
        """Extrait le stock total depuis les données SAP"""
        total_stock = 0.0
        
        if "stock" in product_details and isinstance(product_details["stock"], dict):
            total_stock = float(product_details["stock"].get("total", 0))
        elif "QuantityOnStock" in product_details:
            total_stock = float(product_details.get("QuantityOnStock", 0))
        elif "OnHand" in product_details:
            total_stock = float(product_details.get("OnHand", 0))
        
        return total_stock

    async def _apply_price_engine(self, client_data: Dict, products_data: List[Dict]) -> Dict[str, Any]:
        """Applique le Price Engine pour calculer les prix finaux"""
        try:
            
            price_engine = PriceEngineService()
            
            # Préparer les données pour le Price Engine
            pricing_request = {
                "client": {
                    "id": client_data.get("Id"),
                    "name": client_data.get("Name"),
                    "account_number": client_data.get("AccountNumber"),
                    "type": client_data.get("Type", "Standard"),
                    "city": client_data.get("BillingCity"),
                    "country": client_data.get("BillingCountry")
                },
                "products": [
                    {
                        "code": p.get("code"),
                        "name": p.get("name"),
                        "quantity": p.get("quantity", 1),
                        "base_price": p.get("sap_data", {}).get("Price", 0),
                        "category": p.get("sap_data", {}).get("ItemsGroupCode"),
                        "sap_data": p.get("sap_data", {})
                    }
                    for p in products_data
                ],
                "conditions": {
                    "draft_mode": self.draft_mode,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Calculer les prix avec le Price Engine
            pricing_result = await price_engine.calculate_pricing(pricing_request)
            
            if pricing_result.get("success"):
                return {
                    "success": True,
                    "updated_products": pricing_result.get("products", []),
                    "total_amount": pricing_result.get("total_amount", 0.0),
                    "pricing_details": pricing_result.get("details", {})
                }
            else:
                logger.error(f"Erreur Price Engine: {pricing_result.get('error')}")
                return {"success": False, "error": pricing_result.get("error")}
                
        except Exception as e:
            logger.error(f"Erreur application Price Engine: {str(e)}")
            return {"success": False, "error": str(e)}
        
    async def _apply_price_calculations(self, products_data: List[Dict], client_data: Dict) -> List[Dict]:
        """
        Applique les calculs de prix via le Price Engine
        """
        try:
            
            logger.info("💰 Démarrage calculs Prix Engine...")
            
            # Préparer les données pour le Price Engine
            price_engine = PriceEngineService()
            
            pricing_request = {
                "client": {
                    "id": client_data.get("Id"),
                    "name": client_data.get("Name"),
                    "account_number": client_data.get("AccountNumber"),
                    "type": client_data.get("Type", "Standard"),
                    "city": client_data.get("BillingCity"),
                    "country": client_data.get("BillingCountry")
                },
                "products": [
                    {
                        "code": p.get("code"),
                        "name": p.get("name"),
                        "quantity": p.get("quantity", 1),
                        "sap_data": p.get("sap_raw_data", {}),
                        "stock": p.get("stock", 0)
                    }
                    for p in products_data if not p.get("error")
                ],
                "conditions": {
                    "draft_mode": self.draft_mode,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # 🚀 APPEL AU PRICE ENGINE
            pricing_result = await price_engine.calculate_pricing(pricing_request)
            
            if not pricing_result.get("success"):
                logger.error(f"❌ Erreur Price Engine: {pricing_result.get('error')}")
                raise Exception(pricing_result.get("error", "Erreur Price Engine"))
            
            # Fusionner les résultats du Price Engine avec les données produits
            priced_products = []
            pricing_products = {p["code"]: p for p in pricing_result.get("products", [])}
            
            for product in products_data:
                if product.get("error"):
                    priced_products.append(product)  # Conserver les erreurs
                    continue
                    
                product_code = product["code"]
                pricing_data = pricing_products.get(product_code, {})
                
                # ✅ Fusionner données techniques + prix
                priced_product = {
                    **product,  # Données techniques existantes
                    "unit_price": pricing_data.get("unit_price", 0.0),
                    "line_total": pricing_data.get("line_total", 0.0),
                    "price_calculated": True,
                    "pricing_details": pricing_data.get("details", {}),
                    "discounts": pricing_data.get("discounts", []),
                    "price_engine_version": pricing_result.get("version", "1.0")
                }
                
                priced_products.append(priced_product)
            
            logger.info(f"✅ Price Engine appliqué sur {len(priced_products)} produits")
            return priced_products
            
        except Exception as e:
            logger.error(f"❌ Erreur application Price Engine: {str(e)}")
            # En cas d'erreur, retourner les produits avec prix par défaut
            return self._apply_fallback_pricing(products_data)

    def _apply_fallback_pricing(self, products_data: List[Dict]) -> List[Dict]:
        """Prix de secours si le Price Engine échoue"""
        logger.warning("⚠️ Application des prix de secours...")
        
        for product in products_data:
            if not product.get("error") and product.get("unit_price") is None:
                # Prix de secours basé sur les données SAP brutes
                sap_data = product.get("sap_raw_data", {})
                fallback_price = self._extract_fallback_price_from_sap(sap_data)
                
                product.update({
                    "unit_price": fallback_price,
                    "line_total": product["quantity"] * fallback_price,
                    "price_calculated": True,
                    "pricing_method": "fallback"
                })
        
        return products_data

    def _extract_fallback_price_from_sap(self, sap_data: Dict) -> float:
        """Extrait un prix de secours depuis les données SAP"""
        # Votre logique actuelle de récupération de prix (extraite de l'ancienne version)
        if "price_details" in sap_data and sap_data["price_details"].get("price_engine"):
            pe = sap_data["price_details"]["price_engine"]
            return float(pe.get("unit_price_after_discount", 0.0))
        elif "Price" in sap_data:
            return float(sap_data.get("Price", 0.0))
        elif "ItemPrices" in sap_data and len(sap_data["ItemPrices"]) > 0:
            return float(sap_data["ItemPrices"][0].get("Price", 0.0))
        elif "LastPurchasePrice" in sap_data:
            return float(sap_data.get("LastPurchasePrice", 0.0))
        else:
            return 100.0  # Prix par défaut

    def _get_standard_system_prompt(self) -> str:
        """Retourne le prompt système standard pour l'extraction"""
        return """Tu es un assistant spécialisé dans l'extraction d'informations de devis.
        Extrait les informations client, produits et quantités de la demande utilisateur.
        Retourne un JSON structuré avec les champs: client_info, products, special_requirements."""

    def _get_robust_system_prompt(self) -> str:
        """Retourne le prompt système robuste avec fallbacks"""
        return """Tu es un assistant expert en extraction d'informations de devis.
        Extrait toutes les informations disponibles même si incomplètes.
        Utilise des valeurs par défaut raisonnables pour les champs manquants.
        Retourne un JSON structuré avec validation et suggestions."""

    def _get_minimal_system_prompt(self) -> str:
        """Retourne le prompt système minimal pour extraction rapide"""
        return """Extrait rapidement: nom client, produits demandés, quantités.
        Format JSON simple uniquement."""
        
    async def _extract_info_unified(self, prompt: str, 
                                extraction_mode: str = "standard") -> Dict[str, Any]:
        """
        Méthode d'extraction LLM unifiée
        
        Args:
            prompt: Demande utilisateur
            extraction_mode: Mode d'extraction (standard, robust, minimal)
        
        Returns:
            Informations extraites
        """
        system_prompts = {
            "standard": self._get_standard_system_prompt(),
            "robust": self._get_robust_system_prompt(),
            "minimal": self._get_minimal_system_prompt()
        }
        
        system_prompt = system_prompts.get(extraction_mode, system_prompts["standard"])
        
        try:
            # Logique d'extraction commune
            result = await self.llm_extractor.extract_quote_info(prompt)
            
            # Post-traitement selon le mode
            # Pour l'instant, on retourne le résultat tel quel
            # Les modes "robust" et "minimal" peuvent être implémentés plus tard
            return result

        except Exception as e:
            logger.error(f"Erreur extraction {extraction_mode}: {e}")
            return {"error": str(e)}
    
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
    async def _extract_intelligent_search_criteria(self, product_name: str) -> Dict[str, Any]:
        """Extrait critères de recherche intelligents via LLM"""
        
        prompt = f"""
    Analyse ce produit et extrais les critères de recherche SAP :
    Produit: "{product_name}"

    Extrais :
    - Catégorie principale (imprimante, ordinateur, etc.)
    - Spécifications techniques (vitesse ppm, type laser/jet, etc.)
    - Mots-clés de recherche optimaux

    Format JSON uniquement.
    """
        
        try:
            result = await self.llm_extractor.extract_quote_info(prompt)
            search_criteria = result.get("search_criteria", {})
            
            return {
                "category": search_criteria.get("category", product_name.split()[0]),
                "specifications": search_criteria.get("specifications", {}),
                "keywords": search_criteria.get("characteristics", [product_name])
            }
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return {"category": product_name, "keywords": [product_name]}

    async def _smart_product_search(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Recherche produits avec critères intelligents"""
        
        category = criteria.get("category", "")
        specifications = criteria.get("specifications", {})
        keywords = criteria.get("keywords", [])
        
        exact_matches = []
        close_matches = []
        
        # Recherche par catégorie + spécifications
        if "vitesse" in specifications:
            target_speed = int(specifications["vitesse"].replace(" ppm", "").replace("ppm", ""))
            query = f"{category} {target_speed}"
        else:
            query = category
        
        try:
            result = await self.mcp_connector.call_mcp(
                "sap_mcp", "sap_search", 
                {"query": query, "entity_type": "Items", "limit": 5}
            )
            
            if result.get("success"):
                products = result.get("results", []) or result.get("value", [])
                
                for product in products:
                    score = self._calculate_product_match_score(product, criteria)
                    
                    if score >= 0.8:
                        exact_matches.append(product)
                    elif score >= 0.5:
                        close_matches.append(product)
                        
        except Exception as e:
            logger.warning(f"Erreur recherche '{query}': {e}")
        
        return {
            "success": len(exact_matches) > 0 or len(close_matches) > 0,
            "exact_matches": exact_matches[:3],
            "close_matches": close_matches[:5]
        }

    def _calculate_product_match_score(self, product: Dict, criteria: Dict) -> float:
        """Calcule score de correspondance produit/critères"""
        
        score = 0.0
        product_name = product.get("ItemName", "").lower()
        combined_text = f"{product_name} {product.get('U_Description', '').lower()}"
        
        # Score catégorie
        category = criteria.get("category", "").lower()
        if category in combined_text:
            score += 0.4
        
        # Score spécifications techniques (vitesse ppm)
        specifications = criteria.get("specifications", {})
        if "vitesse" in specifications:
            target_speed = int(specifications["vitesse"].replace(" ppm", "").replace("ppm", ""))
            
            import re
            speed_matches = re.findall(r'(\d+)\s*ppm', combined_text)
            for match in speed_matches:
                product_speed = int(match)
                speed_diff = abs(product_speed - target_speed)
                
                if speed_diff == 0:
                    score += 0.5
                elif speed_diff <= 2:
                    score += 0.3
                elif speed_diff <= 5:
                    score += 0.1
        
        return min(score, 1.0)
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

        # 🔧 PROTECTION SUPPLÉMENTAIRE: S'assurer que les listes ne sont jamais None
        if available_clients is None:
            logger.warning("available_clients est None, utilisation d'une liste vide")
            available_clients = []
        if available_products is None:
            logger.warning("available_products est None, utilisation d'une liste vide")
            available_products = []

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
            "success": True,
            "workflow_status": "waiting_for_input",
            "response_type": "user_input_required",
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
            clients_data = await self.mcp_connector.get_salesforce_accounts(limit=100)

            # 🔧 CORRECTION: Vérifier si clients_data est valide
            if clients_data and isinstance(clients_data, list):
                clients = []
                for record in clients_data:
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
                logger.info(f"Récupéré {len(clients)} clients depuis Salesforce (méthode principale)")
                return clients
            else:
                logger.warning("Méthode principale n'a pas retourné de données valides, passage au fallback")

        except Exception as e:
            logger.warning(f"Méthode principale échouée, passage au fallback: {str(e)}")

        # 🔧 FALLBACK: Essayer avec appel MCP direct
        try:
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
                logger.info(f"Récupéré {len(clients)} clients depuis Salesforce (fallback)")
                return clients
            else:
                logger.warning("Aucun client trouvé dans Salesforce")

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des clients: {str(e)}")

        # 🔧 CORRECTION: Toujours retourner une liste, jamais None
        logger.info("Retour de la liste d'exemple de clients")
        return [
            {"id": "example1", "name": "Acme Corporation", "type": "Customer", "industry": "Technology"},
            {"id": "example2", "name": "Global Industries", "type": "Prospect", "industry": "Manufacturing"},
            {"id": "example3", "name": "Tech Solutions Ltd", "type": "Customer", "industry": "IT Services"}
        ]
    
    async def _enhanced_product_search(self, product_name: str, product_code: str = "") -> Dict[str, Any]:
        """
        🔧 RECHERCHE PRODUIT AMÉLIORÉE pour cas comme "Imprimante 20 ppm"
        """
        try:
            logger.info(f"🔍 Recherche produit améliorée: '{product_name}' (code: '{product_code}')")

            # 1. Recherche exacte par code si fourni
            if product_code:
                exact_result = await self.mcp_connector.call_mcp(
                    "sap_mcp",
                    "sap_search",
                    {
                        "table": "OITM",
                        "filter": f"ItemCode eq '{product_code}'",
                        "select": "ItemCode,ItemName,OnHand,AvgPrice"
                    }
                )
                
                if exact_result.get("success") and exact_result.get("data"):
                    return {
                        "found": True,
                        "product": exact_result["data"][0],
                        "search_method": "exact_code"
                    }

            # 2. Recherche intelligente par nom pour "imprimantes"
            if product_name:
                search_terms = self._extract_product_keywords(product_name)
                
                for term in search_terms:
                    logger.info(f"🔍 Recherche avec terme: '{term}'")
                    
                    fuzzy_result = await self.mcp_connector.call_mcp(
                        "sap_mcp",
                        "sap_search",
                        {
                            "table": "OITM",
                            "filter": f"contains(tolower(ItemName),'{term.lower()}') or contains(tolower(U_Description),'{term.lower()}')",
                            "select": "ItemCode,ItemName,OnHand,AvgPrice,U_Description",
                            "top": 3
                        }
                    )
                    
                    if fuzzy_result.get("success") and fuzzy_result.get("data"):
                        best_match = fuzzy_result["data"][0]
                        logger.info(f"✅ Produit trouvé: {best_match.get('ItemName')} ({best_match.get('ItemCode')})")
                        
                        return {
                            "found": True,
                            "product": best_match,
                            "search_method": "fuzzy",
                            "search_term": term
                        }

            # 3. Recherche intelligente avec mots-clés
            logger.info(f"🔍 Recherche intelligente pour: {product_name}")
            keywords = self._extract_product_keywords(product_name)
            
            for keyword in keywords[:2]:  # Tester 2 mots-clés max
                keyword_result = await self.mcp_connector.call_mcp(
                    "sap_mcp",
                    "sap_search",
                    {
                        "search_term": keyword,
                        "search_fields": ["ItemName", "U_Description"],
                        "limit": 3
                    }
                )
                
                if keyword_result.get("success") and keyword_result.get("results"):
                    best_match = keyword_result["results"][0]
                    logger.info(f"✅ Produit trouvé via mot-clé '{keyword}': {best_match.get('ItemName')}")
                    
                    return {
                        "found": True,
                        "product": {
                            "code": best_match.get("ItemCode"),
                            "name": best_match.get("ItemName"),
                            "price": float(best_match.get("AvgPrice", 0)),
                            "stock": int(best_match.get("OnHand", 0)),
                            "description": best_match.get("U_Description", "")
                        },
                        "search_method": "keyword_match",
                        "matched_keyword": keyword
                    }
            
            
        except Exception as e:
            logger.exception(f"❌ Erreur recherche produit: {str(e)}")
            return {
                "found": False,
                "error": str(e)
            }

    def _extract_product_keywords(self, product_name: str) -> List[str]:
        """
        🔧 EXTRACTION INTELLIGENTE de mots-clés pour "Imprimante 20 ppm"
        """
        product_lower = product_name.lower()
        keywords = []
        
        # Détection type de produit
        if "imprimante" in product_lower:
            keywords.extend(["printer", "imprimante", "laser"])
            
            # Détection vitesse
            if "20 ppm" in product_lower or "20ppm" in product_lower:
                keywords.extend(["20ppm", "20 ppm", "pages per minute"])
                
            # Détection technologie
            if any(tech in product_lower for tech in ["laser", "jet", "inkjet"]):
                keywords.extend(["laser", "inkjet"])
            else:
                keywords.append("laser")  # Par défaut pour imprimantes pro
        
        elif "ordinateur" in product_lower or "pc" in product_lower:
            keywords.extend(["computer", "pc", "desktop"])
        
        elif "écran" in product_lower or "moniteur" in product_lower:
            keywords.extend(["monitor", "screen", "display"])
        
        else:
            # Mots génériques
            keywords.append(product_name.split()[0])  # Premier mot
        
        logger.info(f"🔍 Mots-clés extraits de '{product_name}': {keywords}")
        return keywords

    def _create_generic_product(self, product_name: str) -> Dict[str, Any]:
        """
        🔧 CRÉATION PRODUIT GÉNÉRIQUE avec prix estimé
        """
        import time
        
        # Prix estimés selon le type
        estimated_price = 100.0  # Par défaut
        
        if "imprimante" in product_name.lower():
            if "20 ppm" in product_name.lower():
                estimated_price = 250.0  # Imprimante laser 20 ppm
            else:
                estimated_price = 150.0  # Imprimante générique
        elif "ordinateur" in product_name.lower():
            estimated_price = 800.0
        elif "écran" in product_name.lower():
            estimated_price = 300.0
        
        generic_code = f"GEN{int(time.time()) % 10000:04d}"
        
        return {
            "ItemCode": generic_code,
            "ItemName": product_name.title(),
            "OnHand": 999,  # Stock fictif
            "AvgPrice": estimated_price,
            "U_Description": f"Produit générique créé automatiquement - Prix estimé",
            "Generic": True
        }
    
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
    
    async def _search_products_with_validation(self, products: List[Dict]) -> Dict[str, Any]:
        """Recherche produits avec gestion des alternatives"""
        
        self._track_step_start("search_products", f"🔍 Recherche de {len(products)} produit(s)")
        
        results = []
        requires_validation = False
        
        for i, product in enumerate(products):
            product_name = product.get("name", "")
            product_code = product.get("code", "")
            quantity = product.get("quantity", 1)
            
            self._track_step_progress("product_search_progress", 
                                    int((i / len(products)) * 100), 
                                    f"Recherche: {product_name}")
            
            # Rechercher dans SAP
            sap_results = await self.mcp_connector.search_sap_items(product_name, product_code)
            
            exact_matches = []
            fuzzy_matches = []
            
            for result in sap_results.get("results", []):
                name_similarity = self._calculate_similarity(product_name, result.get("ItemName", ""))
                code_similarity = self._calculate_similarity(product_code, result.get("ItemCode", "")) if product_code else 0
                
                max_similarity = max(name_similarity, code_similarity)
                
                if max_similarity >= 0.9:
                    exact_matches.append({"data": result, "similarity": max_similarity})
                elif max_similarity >= 0.6:
                    fuzzy_matches.append({"data": result, "similarity": max_similarity})
            
            if exact_matches:
                # Produit trouvé
                best_match = max(exact_matches, key=lambda x: x["similarity"])
                results.append({
                    "original": product,
                    "found": True,
                    "product_data": best_match["data"],
                    "quantity": quantity,
                    "status": "found"
                })
            elif fuzzy_matches:
                # Alternatives trouvées
                results.append({
                    "original": product,
                    "found": False,
                    "alternatives": fuzzy_matches,
                    "quantity": quantity,
                    "status": "alternatives_available"
                })
                requires_validation = True
            else:
                # Aucun produit trouvé
                results.append({
                    "original": product,
                    "found": False,
                    "alternatives": [],
                    "quantity": quantity,
                    "status": "not_found"
                })
        
        self._track_step_complete("product_search_progress", "Recherche terminée")
        
        if requires_validation:
            self._track_step_start("product_alternatives", "🔄 Alternatives produits trouvées")
            self._track_step_start("product_validation", "⏳ Sélection utilisateur requise")
            
            validation_data = {
                "products": results,
                "message": "Sélectionnez les produits appropriés"
            }
            
            self.current_task.require_user_validation("product_validation", "product_selection", validation_data)
            
            await websocket_manager.send_user_interaction_required(self.task_id, {
                "type": "product_selection",
                "message": "Certains produits nécessitent votre attention",
                "data": validation_data
            })
            
            return {
                "found": False,
                "requires_validation": True,
                "validation_type": "product_selection",
                "results": results
            }
        else:
            # Tous les produits trouvés
            found_products = [r for r in results if r["found"]]
            self._track_step_complete("search_products", f"✅ {len(found_products)} produit(s) trouvé(s)")
            
            return {
                "found": True,
                "products": found_products
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

    @router_v2.post("/continue_quote")
    async def continue_quote_after_interaction(request: dict):
        """
        Continue le workflow après interaction utilisateur
        """
        try:
            task_id = request.get("task_id")
            user_input = request.get("user_input", {})
            context = request.get("context", {})

            if not task_id:
                raise HTTPException(status_code=400, detail="task_id requis")

            # Récupérer l'instance workflow depuis le cache
            workflow_data = await cache_manager.get_workflow_state(task_id)
            if not workflow_data:
                raise HTTPException(status_code=404, detail="Workflow expiré")

            # Recréer l'instance et restaurer le contexte
            workflow = DevisWorkflow()
            workflow.task_id = task_id
            workflow.context = workflow_data.get("context", {})

            # Continuer le workflow avec le contexte restauré
            result = await workflow.continue_after_user_input(user_input, workflow.context)

            # Sauvegarder l'état mis à jour
            await cache_manager.save_workflow_state(task_id, {
                "context": workflow.context,
                "last_update": datetime.now().isoformat()
            })

            return {"success": True, "data": result}

        except HTTPException:
            # Réélever les erreurs HTTP
            raise
        except Exception as e:
            logger.exception(f"Erreur continue_quote: {e}")
            raise HTTPException(status_code=500, detail="Erreur interne")

    async def _process_quote_workflow(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 REFONTE : Workflow de devis avec gestion d'interruption client et statuts critiques
        """
        try:
            client_name = extracted_info.get("client", "")
            products = extracted_info.get("products", [])

            # Étape 1 : recherche/validation du client
            self._track_step_start("search_client", f"👤 Recherche du client : {client_name}")
            client_result = await self._process_client_validation(client_name)

            # 🔧 CORRECTION CRITIQUE: Vérifier si interaction utilisateur requise
            if client_result.get("status") in ["user_interaction_required", "client_selection_required"]:
                # Marquer la tâche comme en attente d'interaction
                if self.current_task:
                    self.current_task.status = TaskStatus.PENDING
                    self.current_task.require_user_validation("client_selection", "client_selection", client_result)
                logger.info("⏸️ Workflow interrompu - Interaction utilisateur requise pour sélection client")
                # 🔧 CORRECTION CRITIQUE: Envoyer interaction via WebSocket avec debug amélioré
                interaction_data = client_result.get("interaction_data", client_result)

                # Debug des données
                if not interaction_data.get("client_options"):
                    logger.error("❌ ERREUR: Pas de client_options dans interaction_data")
                    logger.error(f"❌ Structure reçue: {json.dumps(interaction_data, indent=2, default=str)}")
                else:
                    logger.info(f"✅ {len(interaction_data.get('client_options', []))} clients prêts pour sélection")
                    for i, client in enumerate(interaction_data.get('client_options', [])):
                        logger.info(f"Client {i+1}: {client.get('name')} ({client.get('source')}) - ID: {client.get('id')}")

                logger.info(f"📨 Envoi WebSocket pour tâche {self.task_id}")
                await websocket_manager.send_user_interaction_required(self.task_id, interaction_data)
                logger.info(f"⏸️ Tâche {self.task_id} en attente d'interaction utilisateur")
                return client_result
            # 🔧 NOUVEAU: Vérifier autres statuts qui nécessitent un arrêt
            if client_result.get("status") in ["error", "cancelled"]:
                logger.warning(f"❌ Workflow interrompu - Statut client : {client_result.get('status')}")
                return client_result

            self._track_step_complete("search_client", f"✅ Client : {client_result.get('status')}")

            # Étape 2 : récupération des produits
            self._track_step_start("lookup_products", f"📦 Recherche de {len(products)} produit(s)")
            products_result = await self._process_products_retrieval(products)
            found = len(products_result.get("products", []))
            self._track_step_complete("lookup_products", f"✅ {found} produit(s) trouvé(s)")

            # Étape 3 : création du devis
            self._track_step_start("prepare_quote", "📋 Préparation du devis")
            quote_result = await self._create_quote_document(client_result, products_result)
            if not isinstance(quote_result, dict):
                logger.error("❌ _create_quote_document a retourné un résultat invalide")
                quote_result = {"status": "error", "quote_data": {}}

            # Extraction sécurisée de quote_data
            quote_data = quote_result.get("quote_data") or {}
            returned_products = quote_data.get("products") or products_result.get("products", [])
            if not returned_products:
                logger.warning("❌ Aucun produit valide pour le devis")
                return {"success": False, "error": "Aucun produit valide trouvé"}

            # Étape 4 : synchronisation dans les systèmes externes
            # 🔧 FACTORISATION : un seul appel pour SAP et Salesforce
            self._track_step_start("sync_external_systems", "💾 Synchronisation SAP & Salesforce")
            sync_results = {}
            for system in ("sap", "salesforce"):
                key = f"sync_to_{system}"
                self._track_step_start(key, f"{'💾' if system=='sap' else '☁️'} Enregistrement dans {system.upper()}")
                result = await self._sync_quote_to_systems(quote_result, target=system)
                self._track_step_complete(key, f"✅ {system.upper()} mis à jour")
                sync_results[system] = result

            # Calcul du montant total
            total_amount = sum(p.get("total_price", 0) for p in returned_products)

            # Résultat final
            return {
                "success": True,
                "status": quote_result.get("status", "success"),
                "type": "quote_generated",
                "message": "✅ Devis généré avec succès !",
                "task_id": self.task_id,
                "workflow_steps": self.workflow_steps,
                "quote_id": quote_data.get("quote_id", ""),
                "client": quote_data.get("client", client_result.get("client_data", {})),
                "products": returned_products,
                "total_amount": total_amount,
                "currency": quote_data.get("currency", "EUR"),
                "quote_data": quote_data,
                "client_result": client_result,
                "products_result": products_result,
                "sync_results": sync_results,
            }

        except Exception as e:
            logger.error(f"❌ Erreur workflow devis : {e}", exc_info=True)
            raise



    async def _process_other_action(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 MODIFICATION : Traitement des autres types d'actions
        """
        action_type = extracted_info.get("action_type", "UNKNOWN")

        return {
            "status": "success",
            "type": "other_action",
            "message": f"Action {action_type} traitée",
            "data": extracted_info
        }

    # 🔧 NOUVELLE MÉTHODE : Version publique pour les tests
    async def test_connections(self) -> bool:
        """
        🔧 NOUVELLE MÉTHODE : Version publique de _check_connections pour les tests
        """
        return await self._check_connections()

    async def _check_connections(self) -> bool:
        """
        🔧 MODIFICATION CRITIQUE : Vérifier les connexions avec progression avancée
        """
        try:
            self._track_step_progress("validate_input", 10, "🔍 Initialisation des tests...")

            # Exécuter les tests de connexion avec progression intégrée
            connection_results = await test_mcp_connections_with_progress()

            # Analyser les résultats
            overall_status = connection_results.get("overall_status", "unknown")
            connections = connection_results.get("connections", {})

            sf_connected = connections.get("salesforce", {}).get("connected", False)
            sap_connected = connections.get("sap", {}).get("connected", False)

            # Déterminer le message de statut
            if overall_status == "all_connected":
                status_msg = "✅ Toutes les connexions validées"
                connections_ok = True
            elif overall_status == "partial_connection":
                status_msg = f"⚠️ Connexions partielles (SF: {'✅' if sf_connected else '❌'}, SAP: {'✅' if sap_connected else '❌'})"
                connections_ok = self.force_production  # Continuer si mode production forcé
            else:
                status_msg = "❌ Aucune connexion disponible"
                connections_ok = False

            self._track_step_progress("validate_input", 100, status_msg)

            # Log détaillé
            logger.info(f"🔧 Test connexions terminé - Statut: {overall_status}")
            logger.info(f"🔧 SF: {sf_connected}, SAP: {sap_connected}, Force Production: {self.force_production}")

            # En mode production forcé, continuer même avec des connexions partielles
            if self.force_production and not connections_ok:
                logger.warning("🔥 MODE PRODUCTION FORCÉ - Continuation malgré les erreurs de connexion")
                connections_ok = True
                self._track_step_progress("validate_input", 100, "🔥 Mode production forcé - Continuation")

            return connections_ok

        except Exception as e:
            logger.error(f"❌ Erreur vérification connexions: {str(e)}")
            self._track_step_progress("validate_input", 100, f"❌ Erreur: {str(e)}")

            # En mode production forcé, continuer même en cas d'erreur
            if self.force_production:
                logger.warning("🔥 MODE PRODUCTION FORCÉ - Continuation malgré l'erreur")
                return True

            return False
    
    async def _search_client_with_validation(self, client_name: str) -> Dict[str, Any]:
        """Recherche client avec gestion des alternatives et validation"""
        
        # Étape 1: Recherche directe
        self._track_step_start("search_client", f"🔍 Recherche du client '{client_name}'")
        
        # NOUVEAU: Utiliser find_client_everywhere pour recherche exhaustive
        self._track_step_progress("search_client", 30, "Recherche exhaustive dans toutes les bases...")
        client_search_result = await find_client_everywhere(client_name)
        
        self._track_step_complete("client_search_progress", "Bases de données consultées")
        
        # NOUVEAU: Analyser les résultats de find_client_everywhere
        total_found = client_search_result.get("total_found", 0)
        logger.info(f"🔍 Recherche exhaustive terminée: {total_found} client(s) trouvé(s)")
        
        if total_found > 0:
            # CLIENT(S) TROUVÉ(S) - Proposer sélection utilisateur
            self._track_step_complete("search_client", f"✅ {total_found} client(s) trouvé(s) pour '{client_name}'")
            return await self._propose_existing_clients_selection(client_name, client_search_result)

        else:
            # AUCUN CLIENT TROUVÉ - Vérifier une dernière fois avant création
            logger.info(f"❌ Aucun client trouvé pour '{client_name}' - Proposition de création")
            self._track_step_start("client_alternatives", "❌ Aucun client trouvé")
            
            # Rechercher des informations INSEE/Pappers
            enrichment_data = await self._search_company_info(client_name)
            
            self._track_step_start("client_validation", "⏳ Création de client requise")
            
            validation_data = {
                "client_name": client_name,
                "enrichment_data": enrichment_data,
                "options": [
                    {"id": "create_new", "label": "Créer ce nouveau client"},
                    {"id": "retry_search", "label": "Rechercher avec un autre nom"}
                ]
            }
            
            self.current_task.require_user_validation("client_validation", "client_creation", validation_data)
            
            # DÉSACTIVÉ - Retour synchrone utilisé
            # await websocket_manager.send_user_interaction_required(
            #     self.task_id, 
            #     selection_result
            # )
            
            return {
                "found": False,
                "requires_validation": True,
                "validation_type": "client_creation",
                "enrichment_data": enrichment_data
            }
    def _sanitize_soql_string(self, value: str) -> str:
        return value.replace("'", "\\'")
    

    async def _propose_existing_clients_selection(self, client_name: str, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """Propose la sélection du client avec interface utilisateur - AMÉLIORÉ"""
        try:
            option_id = 1
            client_options: List[Dict[str, Any]] = []   
            
            # Utiliser les clients dédupliqués pour éviter les doublons
            deduplicated_clients = search_results.get("deduplicated_clients", [])
            logger.info(f"🔧 Traitement de {len(deduplicated_clients)} clients dédupliqués")
            
            for client in deduplicated_clients:
                if not client:
                    continue
                    
                source = client.get("source", "unknown")
                
                # Déterminer le nom et les IDs selon la source
                if source == "both":
                    # Client présent dans les deux systèmes
                    name = client.get("Name") or client.get("CardName", f"Client {option_id}")
                    source_display = "Salesforce & SAP"
                    sf_id = client.get("Id", "N/A")
                    sap_data = client.get("sap_data", {})
                    sap_code = sap_data.get("CardCode", "N/A")
                    
                    # Fusionner les détails des deux systèmes
                    details = {
                        "sf_id": sf_id,
                        "sap_code": sap_code,
                        "phone": client.get("Phone") or sap_data.get("Phone1", "N/A"),
                        "address": sap_data.get("BillToStreet", "N/A"),
                        "city": sap_data.get("City", client.get("BillingCity", "N/A")),
                        "siret": sap_data.get("FederalTaxID", "N/A"),
                        "industry": client.get("Industry", "N/A")
                    }
                    
                elif source == "salesforce":
                    name = client.get("Name", f"Client SF {option_id}")
                    source_display = "Salesforce"
                    details = {
                        "sf_id": client.get("Id", "N/A"),
                        "phone": client.get("Phone", "N/A"),
                        "address": client.get("BillingStreet", "N/A"),
                        "city": client.get("BillingCity", "N/A"),
                        "industry": client.get("Industry", "N/A"),
                        "siret": "Non disponible en Salesforce"
                    }
                    
                else:  # source == "sap"
                    name = client.get("CardName", f"Client SAP {option_id}")
                    source_display = "SAP"
                    details = {
                        "sap_code": client.get("CardCode", "N/A"),
                        "phone": client.get("Phone1", "N/A"),
                        "address": client.get("BillToStreet", "N/A"),
                        "city": client.get("City", "N/A"),
                        "siret": client.get("FederalTaxID", "N/A"),
                        "country": client.get("Country", "FR")
                    }
                
                # Format dense pour l'affichage
                display_info = []
                if details.get("city") and details["city"] != "N/A":
                    display_info.append(details["city"])
                if details.get("siret") and details["siret"] != "N/A" and "Non disponible" not in details["siret"]:
                    display_info.append(f"SIRET: {details['siret']}")
                if details.get("phone") and details["phone"] != "N/A":
                    display_info.append(f"Tél: {details['phone']}")
                    
                display_detail = " | ".join(display_info) if display_info else "Informations limitées"
                
                client_options.append({
                    "id": option_id,
                    "name": name,
                    "source": source_display,
                    "source_raw": source,
                    "display_detail": display_detail,
                    "sf_id": details.get("sf_id"),
                    "sap_code": details.get("sap_code"), 
                    "details": details
                })
                
                option_id += 1     
                # Vérifier qu'on a des clients à proposer
                if not client_options:
                    return {
                        "status": "client_not_found",
                        "requires_user_selection": False,
                        "message": f"Client '{client_name}' introuvable."
                    }
                validation_data = {
                    "options": client_options,
                    "clients": client_options,
                    "client_options": client_options,
                    "total_options": len(client_options),
                    "original_client_name": client_name,
                    "allow_create_new": True,
                    "interaction_type": "client_selection"
                }

                self.current_task.require_user_validation("client_selection", "client_selection", validation_data)
                logger.info(f"🔍 DEBUG WORKFLOW: selection_result = {json.dumps({'status': 'user_interaction_required', 'client_options_count': len(client_options)}, indent=2, default=str)}")
                logger.info(f"🔍 DEBUG WORKFLOW: interaction_data présent = {'interaction_data' in locals()}")
                return {
                    "status": "user_interaction_required",
                    "requires_user_selection": True,
                    "validation_pending": True,
                    "task_id": self.task_id,
                    "message": f"Sélection client requise - {len(client_options)} options disponibles",
                    "interaction_type": "client_selection",
                    "interaction_data": {
                        "type": "client_selection",
                        "interaction_type": "client_selection",
                        "options": client_options,
                        "clients": client_options,
                        "client_options": client_options,
                        "total_options": len(client_options),
                        "original_client_name": client_name,
                        "allow_create_new": True,
                        "message": f"Sélection client requise - {len(client_options)} options disponibles"
                    },
                    "client_options": client_options,
                    "total_options": len(client_options),
                    "original_client_name": client_name,
                    "allow_create_new": True
                }


        except Exception as e:
            logger.error(f"❌ Erreur proposition sélection clients: {e}")
            return {"status": "error", "found": False, "error": str(e)}



    async def _create_client_automatically(self, client_name: str) -> Dict[str, Any]:
        """
        🆕 NOUVELLE MÉTHODE : Création automatique du client dans SAP et Salesforce
        Basée sur l'exemple "rondot" des logs
        """
        try:
            # Vérifier si déjà en cours de création
            creation_key = f"creating_client_{client_name.lower().strip()}"
            if hasattr(self, '_creation_locks') and creation_key in self._creation_locks:
                logger.warning(f"⚠️ Création client {client_name} déjà en cours")
                return {"created": False, "error": "Création déjà en cours"}
            
            # Verrouiller la création
            if not hasattr(self, '_creation_locks'):
                self._creation_locks = set()
            self._creation_locks.add(creation_key)
            
            try:
                logger.info(f"🚀 Début création automatique client: {client_name}")


                # 1. Génération CardCode unique (éviter les doublons)
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', client_name)[:6].upper()
                timestamp = str(int(time.time()))[-4:]
                card_code = f"C{clean_name}{timestamp}"

                # 2. Données client pour SAP
                sap_client_data = {
                    "CardCode": card_code,
                    "CardName": client_name.title(),  # "rondot" -> "Rondot"
                    "CardType": "cCustomer",
                    "GroupCode": 100,  # Groupe client par défaut
                    "Currency": "EUR",
                    "Valid": "tYES",
                    "Frozen": "tNO",
                    "Notes": f"Client créé automatiquement par NOVA le {datetime.now().strftime('%d/%m/%Y')}"
                }

                logger.info(f"📝 Données SAP préparées: {card_code} - {client_name.title()}")

                # 3. Création dans SAP d'abord
                self._track_step_progress("search_client", 30, f"Création client SAP {card_code}...")
                
                sap_result = await self.mcp_connector.call_mcp(
                    "sap_mcp",
                    "sap_create_customer_complete",
                    {"customer_data": sap_client_data}
                )

                if not sap_result.get("success", False):
                    logger.error(f"❌ Échec création SAP: {sap_result.get('error')}")
                    return {
                        "created": False,
                        "error": f"Erreur SAP: {sap_result.get('error', 'Erreur inconnue')}"
                    }

                logger.info(f"✅ Client SAP créé: {card_code}")

                # 4. Création dans Salesforce ensuite
                self._track_step_progress("search_client", 60, f"Création client Salesforce...")
                
                sf_client_data = {
                    "Name": client_name.title(),
                    "AccountNumber": card_code,
                    "Type": "Customer",
                    "Industry": "Technology",
                    "BillingCountry": "France",
                    "Description": f"Client créé automatiquement depuis SAP ({card_code})"
                }

                sf_result = await self.mcp_connector.call_mcp(
                    "salesforce_mcp",
                    "salesforce_create_record",
                    {
                        "sobject": "Account",
                        "data": sf_client_data
                    }
                )

                if sf_result.get("success"):
                    logger.info(f"✅ Client Salesforce créé: {sf_result.get('id')}")
                    
                    # Construire les données client pour le workflow
                    client_data = {
                        "Id": sf_result.get("id"),
                        "Name": client_name.title(),
                        "AccountNumber": card_code,
                        "Type": "Customer"
                    }

                    return {
                        "created": True,
                        "client_data": client_data,
                        "sap_card_code": card_code,
                        "salesforce_id": sf_result.get("id"),
                        "message": f"Client '{client_name}' créé avec succès (SAP: {card_code}, SF: {sf_result.get('id')[:8]}...)"
                    }
                else:
                    logger.warning(f"⚠️ Client SAP créé mais échec Salesforce: {sf_result.get('error')}")
                    
                    # Retourner quand même le client SAP
                    client_data = {
                        "Id": f"SAP_{card_code}",  # ID temporaire
                        "Name": client_name.title(),
                        "AccountNumber": card_code,
                        "Type": "Customer"
                    }

                    return {
                        "created": True,
                        "client_data": client_data,
                        "sap_card_code": card_code,
                        "salesforce_error": sf_result.get("error"),
                        "message": f"Client '{client_name}' créé dans SAP uniquement (CardCode: {card_code})"
                    }
            except Exception as e:
                logger.exception(f"❌ Exception lors de la création automatique du client: {e}")
                return {
                    "created": False,
                    "error": f"Exception: {str(e)}"
                }
            finally:
                # Libérer le verrou
                if hasattr(self, '_creation_locks') and creation_key in self._creation_locks:
                    self._creation_locks.remove(creation_key)

        except Exception as e:
            logger.exception(f"❌ Exception création automatique client (global): {str(e)}")
            return {
                "created": False,
                "error": f"Exception globale: {str(e)}"
            }


    async def _process_client_validation(self, client_name: str) -> Dict[str, Any]:
        """
        Validation complète du client avec recherche Salesforce, fallback SAP et enrichissement.
        🔧 CORRIGÉ: Détection et arrêt pour interaction utilisateur
        """
        if not client_name or not client_name.strip():
            return {
                "status": "error",
                "data": None,
                "message": "Nom de client vide"
            }

        try:
            safe_client_name = self._sanitize_soql_string(client_name)
            logger.info(f"🔍 Recherche approfondie du client: {client_name}")
            
            # Utiliser find_client_everywhere pour recherche exhaustive
            comprehensive_search = await find_client_everywhere(client_name)
            total_found = comprehensive_search.get("total_found", 0)
            
            if total_found > 0:
                logger.info(f"✅ {total_found} client(s) existant(s) trouvé(s) pour '{client_name}'")
                
                # 🔧 CORRECTION CRITIQUE: Détecter l'interaction utilisateur requise
                selection_result = await self._propose_existing_clients_selection(client_name, comprehensive_search)
                
                
                # Si pas d'interaction requise, continuer normalement
                return selection_result
            # === ÉTAPE 1: RECHERCHE EXACTE ===
            exact_query = f"""
                SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry 
                FROM Account 
                WHERE Name = '{safe_client_name}' 
                LIMIT 1
            """
            self._track_step_progress("search_client", 10, f"🔍 Recherche exacte de '{client_name}'")
            exact_result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": exact_query})

            if exact_result.get("success") and exact_result.get("totalSize", 0) > 0:
                client_data = exact_result["records"][0]
                logger.info(f"✅ Client trouvé (exact): {client_data['Name']}")
                return {
                    "status": "found",
                    "data": client_data,
                    "message": f"Client trouvé dans Salesforce (exact)",
                    "source": "salesforce_exact"
                }

            # === ÉTAPE 2: INSENSIBLE À LA CASSE ===
            ci_query = f"""
                SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry 
                FROM Account 
                WHERE UPPER(Name) = UPPER('{safe_client_name}') 
                LIMIT 5
            """
            self._track_step_progress("search_client", 20, "🔍 Recherche insensible à la casse")
            ci_result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": ci_query})

            if ci_result.get("success") and ci_result.get("totalSize", 0) > 0:
                for record in ci_result["records"]:
                    if record["Name"].upper() == client_name.upper():
                        logger.info(f"✅ Client trouvé (insensible à la casse): {record['Name']}")
                        return {
                            "status": "found",
                            "data": record,
                            "message": f"Client trouvé (insensible à la casse)",
                            "source": "salesforce_case_insensitive"
                        }

            # === ÉTAPE 3: RECHERCHE FLOUE ===
            fuzzy_query = f"""
                SELECT Id, Name, AccountNumber, Phone, BillingCity, BillingCountry 
                FROM Account 
                WHERE Name LIKE '%{safe_client_name}%' 
                LIMIT 10
            """
            self._track_step_progress("search_client", 40, "🔍 Recherche floue dans Salesforce")
            fuzzy_result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": fuzzy_query})

            if fuzzy_result.get("success") and fuzzy_result.get("totalSize", 0) > 0:
                suggestions = fuzzy_result["records"]
                logger.info(f"🔍 {len(suggestions)} suggestions trouvées pour '{client_name}'")
                return {
                    "status": "not_found",
                    "suggestions_available": True,
                    "suggestions": suggestions,
                    "message": f"{len(suggestions)} clients similaires trouvés dans Salesforce"
                }

            # === ÉTAPE 4: RECHERCHE DANS SAP ===
            self._track_step_progress("search_client", 60, "🔍 Recherche dans SAP")
            sap_result = await self.mcp_connector.call_mcp("sap_mcp", "sap_search", {
                "query": client_name,
                "entity_type": "BusinessPartners",
                "limit": 5
            })

            if sap_result.get("success") and sap_result.get("count", 0) > 0:
                for sap_client in sap_result.get("results", []):
                    if sap_client.get("CardName", "").upper() == client_name.upper():
                        logger.info(f"✅ Client trouvé dans SAP: {sap_client['CardName']}")
                        sf_creation = await self._create_salesforce_from_sap(sap_client)
                        if sf_creation.get("success"):
                            return {
                                "status": "found",
                                "data": sf_creation["data"],
                                "message": "Client synchronisé depuis SAP",
                                "source": "sap_sync"
                            }

            # === ÉTAPE 5: ENRICHISSEMENT et DÉDOUBLONNAGE ===
            self._track_step_progress("search_client", 80, "🔍 Enrichissement externe")
            enrichment_data = await self._search_company_enrichment(client_name)
            duplicates = await self._check_duplicates_enhanced(client_name, enrichment_data)

            if duplicates.get("has_duplicates"):
                return await self._handle_potential_duplicates(duplicates, client_name)

            # === ÉTAPE 6: CRÉATION PROPOSÉE ===
            
            self._track_step_progress("search_client", 95, "⚠️ AUCUN client trouvé - Validation requise")
            user_approval = await self._request_user_validation_for_client_creation(client_name, enrichment_data)

            if user_approval.get("status") == "approved":
                creation_result = await self._create_client_automatically(client_name)
                if creation_result.get("created"):
                    return {
                        "status": "created",
                        "data": creation_result.get("client_data"),
                        "source": "auto_created",
                        "message": creation_result.get("message"),
                        "auto_created": True
                    }
                else:
                    logger.warning(f"❌ Création échouée: {creation_result.get('error')}")
                    return {
                        "status": "not_found",
                        "data": None,
                        "message": f"Création échouée: {creation_result.get('error')}",
                        "search_term": client_name
                    }
            else:
                logger.info(f"⏹️ Création annulée par l'utilisateur")
                return {
                    "status": "cancelled",
                    "data": None,
                    "message": "Création annulée par l'utilisateur",
                    "search_term": client_name
                }

        except Exception as e:
            logger.exception(f"❌ Erreur lors de la validation client {client_name}: {str(e)}")
            return {
                "status": "error",
                "data": None,
                "message": f"Erreur système: {str(e)}"
            }

    async def _create_salesforce_from_sap(self, sap_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un enregistrement Salesforce à partir des données SAP"""
        try:
            logger.info("🔄 Création Salesforce depuis données SAP")
            
            # Mapper les données SAP vers Salesforce
            sf_data = {
                "Name": sap_data.get("CardName", "Client SAP"),
                "Type": "Customer",
                "AccountNumber": sap_data.get("CardCode", ""),
                "Description": f"Client synchronisé depuis SAP - CardCode: {sap_data.get('CardCode', '')}",
                "BillingStreet": sap_data.get("BillToStreet", ""),
                "BillingCity": sap_data.get("BillToCity", ""),
                "BillingState": sap_data.get("BillToState", ""),
                "BillingPostalCode": sap_data.get("BillToZipCode", ""),
                "BillingCountry": sap_data.get("BillToCountry", ""),
                "Phone": sap_data.get("Phone1", ""),
                "Fax": sap_data.get("Fax", ""),
                "Website": sap_data.get("Website", ""),
                "Industry": sap_data.get("Industry", "")
            }
            
            # Créer dans Salesforce
            result = await self.mcp_connector.call_salesforce_mcp("salesforce_create_record", {
                "sobject": "Account",
                "data": sf_data
            })
            
            if result.get("success"):
                logger.info(f"✅ Client Salesforce créé depuis SAP: {result.get('id')}")
                return {
                    "success": True,
                    "salesforce_id": result.get("id"),
                    "data": sf_data
                }
            else:
                logger.error(f"❌ Erreur création Salesforce: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Erreur création Salesforce")
                }
                
        except Exception as e:
            logger.exception(f"Erreur _create_salesforce_from_sap: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    async def _handle_potential_duplicates(self, duplicate_check: Dict, client_name: str) -> Dict[str, Any]:
        """Gère les doublons potentiels détectés"""
        
        duplicates = duplicate_check.get("duplicates", [])
        
        return {
            "status": "user_interaction_required",
            "interaction_type": "duplicate_resolution",
            "message": f"Doublons potentiels trouvés pour '{client_name}'",
            "duplicates": duplicates,
            "options": duplicate_check.get("actions", []),
            "context": {
                "client_name": client_name,
                "duplicate_check": duplicate_check
            }
        }
    async def _request_user_validation_for_client_creation(self, client_name: str, enrichment_data: Dict) -> Dict[str, Any]:
        """Demande validation utilisateur pour création client"""
        try:
            logger.info(f"📩 Demande validation création client: {client_name}")
            
            # Pour le POC, auto-approuver si données enrichies disponibles
            if enrichment_data.get("success") and enrichment_data.get("company_data"):
                logger.warning("⚠️ BLOQUAGE: find_client_everywhere n'a trouvé AUCUN client existant")
                return {
                    "status": "requires_explicit_confirmation",
                    "method": "auto_approved_with_data",
                    "enrichment_data": enrichment_data
                }
            
            # Si pas de données enrichies, on refuse la création.
            logger.warning("⚠️ BLOQUAGE: Aucune donnée d'enrichissement ET aucun client trouvé")
            return {
                "status": "requires_explicit_confirmation",
                "method": "auto_approved_fallback",
                "enrichment_data": enrichment_data,
                "note": "Création approuvée automatiquement en mode POC"
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur validation utilisateur: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }


    
    async def _create_client_if_needed(self, client_name: str) -> Dict[str, Any]:
        """Création automatique du client si nécessaire"""
        try:
            import re
            import time

            # Génération CardCode unique
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', client_name)[:8].upper()
            timestamp = str(int(time.time()))[-4:]
            card_code = f"AUTO{clean_name}{timestamp}"[:15]

            # Données client SAP
            sap_client_data = {
                "CardCode": card_code,
                "CardName": client_name,
                "CardType": "cCustomer",
                "GroupCode": 100,
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO",
                "Notes": f"Client créé automatiquement par NOVA"
            }

            logger.info(f"🆕 Création client SAP: {card_code} ({client_name})")

            # Création dans SAP
            create_result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_create_customer_complete",
                {"customer_data": sap_client_data}
            )

            if create_result.get("success", False):
                logger.info(f"✅ Client SAP créé avec succès: {card_code}")
                
                # Création parallèle dans Salesforce
                sf_data = {
                    "Name": client_name,
                    "AccountNumber": card_code,
                    "Type": "Customer",
                    "Industry": "Technology"
                }

                sf_result = await self.mcp_connector.call_mcp(
                    "salesforce_mcp",
                    "salesforce_create_record",
                    {"sobject": "Account", "data": sf_data}
                )

                return {
                    "created": True,
                    "sap_client": create_result.get("data", {"CardCode": card_code, "CardName": client_name}),
                    "salesforce_client": sf_result.get("data") if sf_result.get("success") else None,
                    "message": f"Client '{client_name}' créé avec succès"
                }
            else:
                return {
                    "created": False,
                    "error": create_result.get("error", "Erreur inconnue lors de la création SAP")
                }

        except Exception as e:
            logger.exception(f"Erreur création client: {str(e)}")
            return {"created": False, "error": str(e)}
    def _extract_product_keywords(self, product_name: str) -> List[str]:
        """Extrait des mots-clés intelligents pour la recherche produit"""
        product_lower = product_name.lower()
        keywords = []
        
        # Dictionnaire de synonymes pour élargir la recherche
        synonyms = {
            "imprimante": ["printer", "imprimante", "laser", "jet"],
            "ordinateur": ["computer", "pc", "desktop"],
            "écran": ["monitor", "screen", "display"],
            "clavier": ["keyboard", "clavier"],
            "souris": ["mouse", "souris"]
        }
        
        # Chercher des correspondances
        for word, related in synonyms.items():
            if word in product_lower:
                keywords.extend(related)
                break
        
        # Si pas de correspondance, utiliser le premier mot
        if not keywords:
            first_word = product_name.split()[0].lower()
            if len(first_word) >= 3:
                keywords.append(first_word)
        
        return keywords[:3]  # Limiter à 3 mots-clés
    async def _process_products_retrieval(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Récupération des produits avec progression avancée
        """
        try:
            if not products:
                return {
                    "status": "success",
                    "products": [],
                    "message": "Aucun produit à traiter"
                }

            self._track_step_progress("lookup_products", 10, f"🔍 Recherche de {len(products)} produit(s)...")

            found_products = []
            total_products = len(products)

            for i, product in enumerate(products):
                product_name = product.get("name", "")
                product_code = product.get("code", "")
                quantity = product.get("quantity", 1)

                # Progression
                progress = int(20 + (i / total_products) * 70)
                self._track_step_progress("lookup_products", progress,
                                        f"📦 Recherche '{product_name}' ({i+1}/{total_products})")

                # === RECHERCHE MULTI-CRITÈRES ===
                product_found = None
                
                # 1. Recherche par code exact si disponible
                if product_code:
                    try:
                        code_result = await self.mcp_connector.call_mcp(
                            "sap_mcp",
                            "sap_read",
                            {"endpoint": f"/Items('{product_code}')"}
                        )
                        
                        if not code_result.get("error") and code_result.get("data", {}).get("ItemCode"):
                            product_found = code_result["data"]
                            logger.info(f"✅ Produit trouvé par code: {product_code}")
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur recherche par code {product_code}: {e}")
                
                # 2. Recherche par nom si pas trouvé par code
                if not product_found and product_name:
                    try:
                        # 2.1 Extraction critères intelligents via LLM
                        search_criteria = await self._extract_intelligent_search_criteria(product_name)
                        
                        # 2.2 Recherche principale par critères
                        search_result = await self._smart_product_search(search_criteria)
                        
                        if search_result.get("success") and search_result.get("products"):
                            exact_matches = search_result.get("exact_matches", [])
                            close_matches = search_result.get("close_matches", [])
                            
                            if exact_matches:
                                product_found = exact_matches[0]
                                logger.info(f"✅ Correspondance exacte: {product_name}")
                            elif close_matches:
                                # Proposer alternatives à l'utilisateur
                                return await self._propose_product_alternatives(
                                    product_name, close_matches, i, total_products
                                )
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur recherche par nom {product_name}: {e}")
                
                # 3. Ajouter le produit aux résultats
                if product_found:
                    # Calculer le prix total
                    unit_price = float(product_found.get("Price", 0) or 0)
                    total_price = unit_price * quantity
                    
                    found_products.append({
                        "code": product_found.get("ItemCode", product_code or "UNKNOWN"),
                        "name": product_found.get("ItemName", product_name or "Produit inconnu"),
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "total_price": total_price,
                        "currency": "EUR",
                        "sap_data": product_found,
                        "found": True,
                        "search_method": "code" if product_code else "name"
                    })
                else:
                    # Produit non trouvé - créer une entrée d'erreur
                    logger.warning(f"❌ Produit non trouvé: {product_name or product_code}")
                    found_products.append({
                        "code": product_code or "NOT_FOUND",
                        "name": product_name or "Produit non spécifié",
                        "quantity": quantity,
                        "unit_price": 0.0,
                        "total_price": 0.0,
                        "currency": "EUR",
                        "sap_data": None,
                        "found": False,
                        "error": "Produit non trouvé dans le catalogue SAP"
                    })

            # Finaliser la progression
            self._track_step_progress("lookup_products", 100, f"✅ Recherche terminée")
            
            # Statistiques
            found_count = len([p for p in found_products if p.get("found", False)])
            total_amount = sum(p.get("total_price", 0) for p in found_products)
            
            logger.info(f"📊 Produits: {found_count}/{total_products} trouvés - Total: {total_amount}€")
            
            return {
                "status": "success",
                "products": found_products,
                "stats": {
                    "total_requested": total_products,
                    "found": found_count,
                    "not_found": total_products - found_count,
                    "total_amount": total_amount
                },
                "message": f"{found_count}/{total_products} produit(s) trouvé(s)"
            }
            
        except Exception as e:
            logger.exception(f"Erreur récupération produits: {str(e)}")
            
            # CORRECTION: Protection garantie du format de retour
            return {
                "status": "error",
                "products": [],
                "stats": {
                    "total_requested": len(products) if products else 0,
                    "found": 0,
                    "not_found": len(products) if products else 0,
                    "total_amount": 0
                },
                "message": f"Erreur système: {str(e)}"
            }

    async def _create_quote_document(self, client_result: Dict, products_result: Dict) -> Dict[str, Any]:
        """
        Création document devis avec données réelles
        """
        try:
            logger.info("📋 Création du document de devis")
            
            # === DONNÉES CLIENT ===
            client_data = client_result.get("data", {})
            if not client_data:
                return {
                    "status": "error",
                    "quote_data": None,
                    "message": "Données client manquantes"
                }
            
            # === DONNÉES PRODUITS ===
            products_data = products_result.get("products", [])
            if not products_data:
                return {
                    "status": "error", 
                    "quote_data": None,
                    "message": "Aucun produit à inclure"
                }
            
            # === CALCULS ===
            total_amount = sum(product.get("total_price", 0) for product in products_data)
            products_count = len(products_data)
            found_products_count = len([p for p in products_data if p.get("found", False)])
            
            # === GÉNÉRATION ID DEVIS ===
            quote_id = f"QUOTE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # === DOCUMENT DEVIS COMPLET ===
            quote_document = {
                "quote_id": quote_id,
                "created_date": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "created_timestamp": datetime.now().isoformat(),
                "status": "draft",
                "currency": "EUR",
                
                # Informations client
                "client": {
                    "name": client_data.get("Name", "Client Inconnu"),
                    "account_number": client_data.get("AccountNumber", ""),
                    "salesforce_id": client_data.get("Id", ""),
                    "phone": client_data.get("Phone", ""),
                    "email": client_data.get("Email", ""),
                    "billing_city": client_data.get("BillingCity", ""),
                    "billing_country": client_data.get("BillingCountry", "")
                },
                
                # Produits détaillés
                "products": products_data,
                
                # Totaux et statistiques
                "totals": {
                    "subtotal": total_amount,
                    "tax_rate": 0.20,  # TVA 20%
                    "tax_amount": total_amount * 0.20,
                    "total_amount": total_amount * 1.20,
                    "products_count": products_count,
                    "found_products_count": found_products_count
                },
                
                # Métadonnées
                "metadata": {
                    "generated_by": "NOVA AI Assistant",
                    "workflow_version": "2.0",
                    "task_id": self.task_id,
                    "client_source": client_result.get("source", "unknown"),
                    "products_stats": products_result.get("stats", {})
                }
            }
            
            # === LOG ET RETOUR ===
            logger.info(f"✅ Devis créé: {quote_id}")
            logger.info(f"   Client: {client_data.get('Name')}")
            logger.info(f"   Produits: {found_products_count}/{products_count}")
            logger.info(f"   Total HT: {total_amount:.2f}€")
            logger.info(f"   Total TTC: {total_amount * 1.20:.2f}€")
            
            return {
                "status": "success",
                "quote_data": quote_document,  # s'assurer que quote_document est défini
                "message": f"Devis {quote_id} créé avec {found_products_count}/{products_count} produits"
            }
            
        except Exception as e:
            logger.exception(f"Erreur création devis: {str(e)}")
            return {
                "status": "error",
                "quote_data": None,
                "message": f"Erreur création devis: {str(e)}"
            }

    
    async def _create_salesforce_opportunity_safe(self, quote_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 CRÉATION SÉCURISÉE d'opportunité Salesforce
        """
        try:
            client_data = quote_data.get("client_data", {})
            
            # Validation préalable
            if not client_data or not client_data.get("Id"):
                logger.error("❌ Impossible de créer l'opportunité : client Salesforce requis")
                return {
                    "success": False,
                    "error": "Client Salesforce requis pour créer l'opportunité",
                    "skip_reason": "missing_client"
                }

            # Données minimales pour éviter les erreurs
            opportunity_data = {
                "Name": f"Devis {quote_data.get('quote_id', 'AUTO')} - {client_data.get('Name', 'Client')}",
                "AccountId": client_data["Id"],
                "StageName": "Prospecting",  # Étape existante dans Salesforce
                "CloseDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            }
            
            # Ajouter le montant seulement s'il est valide
            total_amount = quote_data.get("total_amount", 0)
            if total_amount and total_amount > 0:
                opportunity_data["Amount"] = total_amount

            logger.info(f"📋 Création opportunité: {opportunity_data['Name']}")

            result = await self.mcp_connector.call_mcp(
                "salesforce_mcp",
                "salesforce_create_record",
                {
                    "sobject": "Opportunity",
                    "data": opportunity_data
                }
            )

            if result.get("success"):
                logger.info(f"✅ Opportunité créée: {result.get('id')}")
                return {
                    "success": True,
                    "opportunity_id": result.get("id"),
                    "data": opportunity_data
                }
            else:
                logger.error(f"❌ Erreur création opportunité: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Erreur inconnue"),
                    "attempted_data": opportunity_data
                }

        except Exception as e:
            logger.exception(f"❌ Exception création opportunité: {str(e)}")
            return {
                "success": False,
                "error": f"Exception: {str(e)}"
            }
    
    async def _sync_quote_to_systems(self, quote_result: Dict, target: str = None) -> Dict[str, Any]:
        """
        Synchronisation vers SAP/Salesforce - VERSION PRODUCTION
        """
        try:
            quote_data = quote_result.get("quote_data", {})
            # Gestion du paramètre target pour synchronisation spécifique
            if target and target not in ("sap", "salesforce"):
                return {
                "status": "error",
                "message": f"Target '{target}' non supporté. Utilisez 'sap' ou 'salesforce'"
                }
            if not quote_data:
                return {
                    "status": "error",
                    "message": "Pas de données de devis à synchroniser"
                }
            
            quote_id = quote_data.get("quote_id")
            logger.info(f"💾 Synchronisation production du devis {quote_id}")
            
            # === PRÉPARATION DONNÉES SAP ===
            client_data = quote_data.get("client", {})
            products_data = quote_data.get("products", [])
            
            # Préparation structure SAP quotation_data
            sap_quotation_data = {
                "CardCode": client_data.get("CardCode") or client_data.get("sap_code"),
                "CardName": client_data.get("CardName") or client_data.get("name"),
                "DocDate": datetime.now().strftime("%Y-%m-%d"),
                "DocDueDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "DocumentLines": [
                    {
                        "ItemCode": product.get("ItemCode") or product.get("code"),
                        "Quantity": product.get("Quantity") or product.get("quantity", 1),
                        "UnitPrice": product.get("UnitPrice") or product.get("price", 0),
                        "LineTotal": (product.get("UnitPrice") or product.get("price", 0)) * (product.get("Quantity") or product.get("quantity", 1))
                    }
                    for product in products_data
                ]
            }
            
            # === SYNCHRONISATION SAP ===
            logger.info(f"📡 Appel SAP sap_create_quotation_complete")
            sap_result = await self.mcp_connector.sap_create_quotation_complete(sap_quotation_data)
            
            # === PRÉPARATION DONNÉES SALESFORCE ===
            sf_opportunity_data = {
                "Name": f"Devis {client_data.get('name', 'Client')} - {datetime.now().strftime('%Y-%m-%d')}",
                "AccountId": client_data.get("salesforce_id"),
                "CloseDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "StageName": "Quotation",
                "Amount": quote_data.get("total_amount", 0),
                "Description": f"Devis généré automatiquement - {quote_id}"
            }
            
            sf_line_items = [
                {
                    "Product2Id": product.get("salesforce_id"),
                    "Quantity": product.get("Quantity") or product.get("quantity", 1),
                    "UnitPrice": product.get("UnitPrice") or product.get("price", 0)
                }
                for product in products_data
                if product.get("salesforce_id")
            ]
            
            # === SYNCHRONISATION SALESFORCE ===
            logger.info(f"📡 Appel Salesforce salesforce_create_opportunity_complete")
            sf_result = await self.mcp_connector.salesforce_create_opportunity_complete(
                sf_opportunity_data, sf_line_items
            )
            
            # === TRAITEMENT DES RÉSULTATS ===
            sync_results = {
                "sap_sync": {
                    "attempted": True,
                    "success": sap_result.get("success", False),
                    "message": sap_result.get("error", "Synchronisation SAP réussie") if not sap_result.get("success") else "Devis SAP créé",
                    "quote_sap_id": sap_result.get("DocNum") or sap_result.get("DocEntry"),
                    "doc_entry": sap_result.get("DocEntry")
                },
                "salesforce_sync": {
                    "attempted": True,
                    "success": sf_result.get("success", False),
                    "message": sf_result.get("error", "Synchronisation Salesforce réussie") if not sf_result.get("success") else "Opportunité Salesforce créée",
                    "opportunity_id": sf_result.get("id") or sf_result.get("opportunity_id")
                }
            }
            
            # Détermination du statut global
            if sync_results["sap_sync"]["success"] and sync_results["salesforce_sync"]["success"]:
                status = "success"
                message = f"Synchronisation complète réussie pour {quote_id}"
            elif sync_results["sap_sync"]["success"] or sync_results["salesforce_sync"]["success"]:
                status = "partial_success"
                message = f"Synchronisation partielle pour {quote_id}"
            else:
                status = "error"
                message = f"Échec synchronisation pour {quote_id}"
            
            logger.info(f"✅ Synchronisation terminée: {status}")
            
            return {
                "status": status,
                "sync_results": sync_results,
                "message": message
            }
            
        except Exception as e:
            logger.exception(f"Erreur synchronisation: {str(e)}")
            return {
                "status": "error",
                "message": f"Erreur synchronisation: {str(e)}"
            }

    def _initialize_task_tracking(self, prompt: str) -> str:
        """
        🔧 MODIFICATION : Initialiser le tracking si pas déjà fait
        """
        if not self.current_task:
            
            self.current_task = progress_tracker.create_task(
                user_prompt=prompt,
                draft_mode=self.draft_mode
            )
            self.task_id = self.current_task.task_id
            logger.info(f"🔄 Tracking initialisé pour la tâche: {self.task_id}")

        return self.task_id

class EnhancedDevisWorkflow(DevisWorkflow):
    """Workflow enrichi avec recherche parallèle"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.suggestion_engine = SuggestionEngine()
        self.websocket_manager = websocket_manager
        self.task_id = None
    
    async def process_prompt(self, prompt: str, task_id: str = None, draft_mode: bool = False):
        """Traitement avec recherche parallèle"""
        self.task_id = task_id
        
        # Extraction LLM classique
        extracted_info = await self.llm_extractor.extract_devis_info(prompt)
        
        # Recherche parallèle
        if extracted_info.get("client") and extracted_info.get("products"):
            parallel_result = await self._parallel_client_product_search(extracted_info)
            
            # Continuer avec le workflow existant
            return await super().process_prompt(prompt, draft_mode)
        
        return await super().process_prompt(prompt, draft_mode)
    
    async def _parallel_client_product_search(self, extracted_info: dict):
        """Recherche parallèle client et produits"""
        
        # Notification WebSocket
        await self._notify_websocket("parallel_search_started", {
            "client_query": extracted_info.get("client"),
            "product_queries": extracted_info.get("products", [])
        })
        
        # Lancer recherches parallèles
        client_task = asyncio.create_task(
            self._search_client_with_notifications(extracted_info.get("client"))
        )
        product_task = asyncio.create_task(
            self._search_products_with_notifications(extracted_info.get("products", []))
        )
        
        # Attendre résultats
        client_result, product_results = await asyncio.gather(
            client_task, product_task, return_exceptions=True
        )
        
        return {
            "client_result": client_result,
            "product_results": product_results
        }
    async def _search_company_info(self, company_name: str) -> Dict[str, Any]:
        """
        Recherche des informations enrichies sur une entreprise
        """
        logger.info(f"🔍 Recherche informations entreprise: {company_name}")
        
        try:
            # Utiliser le service d'enrichissement existant
            
            
            # Rechercher les informations via INSEE/Pappers
            search_result = await client_creation_workflow.search_company_by_name(company_name)
            
            if search_result.get("success") and search_result.get("companies"):
                # Prendre la première entreprise trouvée
                company_data = search_result["companies"][0]
                
                return {
                    "found": True,
                    "company_name": company_data.get("company_name", company_name),
                    "siret": company_data.get("siret", "Non disponible"),
                    "siren": company_data.get("siren", "Non disponible"),
                    "address": {
                        "street": company_data.get("address", ""),
                        "postal_code": company_data.get("postal_code", ""),
                        "city": company_data.get("city", "")
                    },
                    "activity": {
                        "code": company_data.get("activity_code", ""),
                        "label": company_data.get("activity_label", "")
                    },
                    "status": company_data.get("status", "Inconnu"),
                    "creation_date": company_data.get("creation_date", ""),
                    "source": company_data.get("source", "recherche_automatique")
                }
            else:
                # Données minimales si pas d'enrichissement possible
                return {
                    "found": False,
                    "company_name": company_name,
                    "siret": "À renseigner",
                    "siren": "À renseigner", 
                    "address": {
                        "street": "À renseigner",
                        "postal_code": "À renseigner",
                        "city": "À renseigner"
                    },
                    "activity": {
                        "code": "À renseigner",
                        "label": "À renseigner"
                    },
                    "status": "À vérifier",
                    "creation_date": "",
                    "source": "creation_manuelle"
                }
                
        except Exception as e:
            logger.error(f"Erreur enrichissement données client: {str(e)}")
            return {
                "found": False,
                "company_name": company_name,
                "siret": "Erreur récupération",
                "error": str(e)
            }
    async def _search_client_with_notifications(self, client_name: str):
        """Recherche client avec notifications"""
        
        # Étape 1: Recherche Salesforce
        await self._notify_websocket("client_search_step", {
            "step": "salesforce",
            "status": "searching",
            "message": f"Recherche de '{client_name}' dans Salesforce..."
        })
        
        sf_result = await self._search_salesforce_client(client_name)
        
        if sf_result.get("found"):
            await self._notify_websocket("client_found", {
                "source": "salesforce",
                "client_data": sf_result["data"],
                "message": f"Client '{client_name}' trouvé dans Salesforce"
            })
            return sf_result
        
        # Étape 2: Recherche externe
        await self._notify_websocket("client_search_step", {
            "step": "external_apis",
            "status": "searching",
            "message": f"Recherche externe de '{client_name}'..."
        })
        
        external_result = await company_search_service.search_company(client_name)
        
        if external_result.get("success"):
            await self._notify_websocket("client_external_data", {
                "companies": external_result["companies"],
                "message": f"Données externes trouvées pour '{client_name}'"
            })
            
            return {
                "found": False,
                "external_data": external_result,
                "requires_validation": True
            }
        
        return {"found": False, "message": f"Client '{client_name}' introuvable"}
    async def continue_workflow_with_user_input(self, user_input: Dict[str, Any], interaction_type: str = None) -> Dict[str, Any]:
        """Gère la continuation du workflow après interaction utilisateur"""
        
        try:
            logger.info(f"🔄 Continuation workflow - Type: {interaction_type}")
            
            context = self.context.copy()
            
            if interaction_type == "client_selection":
                return await self._handle_client_selection(user_input, context)
                
            elif interaction_type == "client_creation_confirmation":
                return await self._handle_client_creation_confirmation(user_input, context)
        except Exception as e:
            logger.error(f"❌ Erreur lors de la continuation du workflow: {str(e)}")
            return {"success": False, "error": str(e)}  
        
    async def _handle_client_creation_confirmation(self, user_input: Dict[str, Any], context: Dict) -> Dict[str, Any]:
        """Gère la confirmation de création d'un nouveau client"""
        
        action = user_input.get("action")
        client_name = user_input.get("client_name") or context.get("client_name")
        
        if action == "confirm_create":
            # L'utilisateur confirme la création
            logger.info(f"✅ Utilisateur confirme création client: {client_name}")
            
            # Récupérer les données enrichies du contexte
            enrichment_data = context.get("enrichment_data", {})
            
            # Procéder à la création avec les données validées
            creation_result = await self._create_validated_client(client_name, enrichment_data)
            
            if creation_result.get("created"):
                # Client créé avec succès - continuer le workflow
                self.context["client_info"] = {
                    "data": creation_result["client_data"], 
                    "found": True
                }
                
                # Continuer avec la validation des produits
                original_products = context.get("original_products", [])
                return await self._continue_product_validation(original_products)
            else:
                return {
                    "success": False,
                    "message": f"❌ Erreur lors de la création du client: {creation_result.get('error')}",
                    "type": "error"
                }
        
        elif action == "cancel_create":
            # L'utilisateur annule la création
            return {
                "success": False,
                "message": "❌ Création du client annulée par l'utilisateur",
                "type": "cancelled"
            }
        
        elif action == "modify_search":
            # L'utilisateur veut modifier la recherche
            return {
                "success": False,
                "requires_user_input": True,
                "message": "🔍 Veuillez préciser le nom exact du client:",
                "input_type": "text",
                "placeholder": "Nom exact de l'entreprise"
            }
        
        else:
            return {
                "success": False,
                "message": "❌ Action non reconnue",
                "type": "error"
            }
    async def _create_validated_client(self, client_name: str, enrichment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un client après validation utilisateur avec les données enrichies
        """
        try:
            logger.info(f"🚀 Création client validé: {client_name}")
            
            # Utiliser les données enrichies pour la création
            
            # Génération CardCode unique
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', client_name)[:6].upper()
            timestamp = str(int(time.time()))[-4:]
            card_code = f"C{clean_name}{timestamp}"
            
            # Préparer les données pour SAP avec informations enrichies
            sap_client_data = {
                "CardCode": card_code,
                "CardName": enrichment_data.get("company_name", client_name.title()),
                "CardType": "cCustomer",
                "GroupCode": 100,
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO",
                "FederalTaxID": enrichment_data.get("siret", ""),
                "Notes": f"Client créé avec validation utilisateur le {datetime.now().strftime('%d/%m/%Y')}"
            }
            
            # Ajouter l'adresse si disponible
            address_data = enrichment_data.get("address", {})
            if address_data.get("street"):
                sap_client_data.update({
                    "MailAddress": address_data.get("street", ""),
                    "MailZipCode": address_data.get("postal_code", ""),
                    "MailCity": address_data.get("city", "")
                })
            
            logger.info(f"📝 Données SAP validées préparées: {card_code}")
            
            # Création dans SAP
            sap_result = await self.mcp_connector.call_mcp(
                "sap_mcp",
                "sap_create_customer_complete",
                {"customer_data": sap_client_data}
            )
            
            if not sap_result.get("success", False):
                logger.error(f"❌ Échec création SAP: {sap_result.get('error')}")
                return {
                    "created": False,
                    "error": f"Erreur SAP: {sap_result.get('error', 'Erreur inconnue')}"
                }
            
            logger.info(f"✅ Client SAP créé: {card_code}")
            
            # Préparer les données pour Salesforce
            sf_client_data = {
                "Name": enrichment_data.get("company_name", client_name.title()),
                "AccountNumber": card_code,
                "Type": "Customer",
                "Industry": enrichment_data.get("activity", {}).get("label", ""),
                "BillingStreet": address_data.get("street", ""),
                "BillingPostalCode": address_data.get("postal_code", ""),
                "BillingCity": address_data.get("city", ""),
                "Description": f"Client créé avec validation - SIRET: {enrichment_data.get('siret', 'N/A')}"
            }
            
            # Création dans Salesforce
            sf_result = await self.mcp_connector.call_mcp(
                "salesforce_mcp",
                "salesforce_create_record",
                {
                    "sobject_type": "Account",
                    "data": sf_client_data
                }
            )
            
            if not sf_result.get("success", False):
                logger.error(f"❌ Échec création Salesforce: {sf_result.get('error')}")
                return {
                    "created": False,
                    "error": f"Erreur Salesforce: {sf_result.get('error', 'Erreur inconnue')}"
                }
            
            sf_client_id = sf_result.get("data", {}).get("Id")
            logger.info(f"✅ Client Salesforce créé: {sf_client_id}")
            
            return {
                "created": True,
                "client_data": {
                    "Id": sf_client_id,
                    "Name": enrichment_data.get("company_name", client_name.title()),
                    "AccountNumber": card_code,
                    "SIRET": enrichment_data.get("siret", ""),
                    "BillingStreet": address_data.get("street", ""),
                    "BillingCity": address_data.get("city", "")
                },
                "sap_card_code": card_code,
                "creation_method": "validated_by_user"
            }
            
        except Exception as e:
            logger.exception(f"❌ Erreur création client validé: {str(e)}")
            return {
                "created": False,
                "error": f"Erreur système: {str(e)}"
            }
    async def _search_sap_product(self, product_code: str, product_name: str):
        """Déléguer à product_manager"""
        return await self.product_manager._search_sap_product(product_code, product_name)
    
    async def _search_products_with_notifications(self, products: list):
        """Recherche produits avec notifications"""
        
        results = []
        
        for i, product in enumerate(products):
            product_name = product.get("name", "")
            
            await self._notify_websocket("product_search_started", {
                "product_index": i,
                "product_name": product_name,
                "message": f"Recherche produit {i+1}/{len(products)}"
            })
            
            # Recherche SAP
            sap_result = await self._search_sap_product(product.get("code", ""), product_name)
            
            if sap_result.get("found"):
                await self._notify_websocket("product_found", {
                    "product_index": i,
                    "product_data": sap_result["data"],
                    "message": f"Produit '{product_name}' trouvé"
                })
                results.append({"index": i, "found": True, "data": sap_result["data"]})
            else:
                await self._notify_websocket("product_not_found", {
                    "product_index": i,
                    "product_name": product_name,
                    "message": f"Produit '{product_name}' introuvable"
                })
                results.append({"index": i, "found": False})
        
        return results
    
    async def _notify_websocket(self, event_type: str, data: dict):
        """Notification WebSocket"""
        if self.task_id:
            await self.websocket_manager.send_task_update(self.task_id, {
                "event": event_type,
                "data": data
            })

# Export du routeur pour intégration dans main.py
__all__ = ['DevisWorkflow', 'router_v2']