# workflow/devis_workflow.py - VERSION COMPLÈTE AVEC VALIDATEUR CLIENT

import re
import sys
import io
import os
import json
import time
import logging
import asyncio
from fastapi import APIRouter, HTTPException

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from difflib import SequenceMatcher
from services.llm_extractor import LLMExtractor
from services.mcp_connector import MCPConnector, call_mcp_with_progress, test_mcp_connections_with_progress
from services.progress_tracker import progress_tracker, QuoteTask, TaskStatus
from services.suggestion_engine import SuggestionEngine
from services.websocket_manager import websocket_manager
from services.company_search_service import company_search_service
from utils.client_lister import find_client_everywhere
from services.product_search_engine import ProductSearchEngine
from workflow.client_creation_workflow import client_creation_workflow
from services.price_engine import PriceEngineService
from services.cache_manager import referential_cache
from workflow.validation_workflow import SequentialValidator
from services.local_product_search import LocalProductSearchService
from services.security_helpers import escape_soql

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
        # Initialisation des composants principaux
        self.mcp_connector = MCPConnector()
        self.llm_extractor = LLMExtractor()
        self.client_validator = ClientValidator() if validation_enabled else None
        self.validation_enabled = validation_enabled
        self.draft_mode = draft_mode
        self.force_production = force_production
        self.task_id = task_id
        self.current_task = None
        self.context = {}
        self.workflow_steps = []

        # Configuration mode production/démo
        self.demo_mode = not force_production
        if force_production:
            logger.info("🔥 MODE PRODUCTION FORCÉ - Pas de fallback démo")

        # Gestion de la tâche
        if task_id:
            try:
                self.current_task = progress_tracker.get_task(task_id)
                if self.current_task:
                    logger.info(f"✅ Tâche récupérée: {task_id}")
                    # Synchroniser le contexte existant si disponible
                    if hasattr(self.current_task, 'context') and self.current_task.context:
                        self.context.update(self.current_task.context)
                        logger.info(f"✅ Contexte restauré depuis la tâche: {list(self.context.keys())}")
                    else:
                        logger.info("📝 Tâche existante - contexte vide")
                else:
                    # Création explicite avec l'ID fourni
                    logger.warning(f"⚠️ Tâche {task_id} introuvable - création explicite avec l'ID existant")
                    self.current_task = progress_tracker.create_task(
                        user_prompt="Génération de devis (créée via fallback)",
                        draft_mode=self.draft_mode,
                        task_id=task_id
                    )
            except Exception as e:
                logger.error(f"Erreur lors de la gestion de la tâche {task_id}: {str(e)}")
                self.current_task = None
                self.task_id = None

        # Initialisation des moteurs
        self.suggestion_engine = SuggestionEngine()
        # Service recherche locale produits
        self.local_product_service = LocalProductSearchService()
        self.client_suggestions = None
        self.product_suggestions = []

        # Initialisation des validateurs et cache
        self.cache_manager = referential_cache
        self.sequential_validator = SequentialValidator(self.mcp_connector, self.llm_extractor)

        # Références aux tâches fire-and-forget (évite garbage collection prématurée)
        self._background_tasks: set = set()

        # Pré-chargement asynchrone du cache
        try:
            cache_task = asyncio.create_task(self._initialize_cache())
            self._background_tasks.add(cache_task)
            cache_task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            logger.info("⏳ Initialisation du cache différée (pas d'event loop actif)")
        # Initialiser WebSocket manager
        self.websocket_manager = websocket_manager
        logger.info("✅ Workflow initialisé avec cache et validation séquentielle")

    async def _initialize_cache(self):
        """Initialisation asynchrone du cache"""
        try:
            await self.cache_manager.preload_common_data(self.mcp_connector)
            logger.info("🚀 Cache pré-chargé avec succès")
        except Exception as e:
            logger.warning(f"⚠️ Erreur pré-chargement cache: {str(e)}")
        
    
    def _track_step_start(self, step_id: str, message: str = ""):
        """Démarre le tracking d'une étape"""
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
                ws_task = asyncio.create_task(websocket_manager.broadcast_to_task(
                    self.task_id,  # CORRECTION: Ajouter task_id explicite
                    {
                        "type": "progress_update",
                        "task_id": self.task_id,  # CORRECTION: Inclure task_id dans le message
                        "step_id": step_id,
                        "progress": progress,
                        "message": message
                    }
                ))
                self._background_tasks.add(ws_task)
                ws_task.add_done_callback(self._background_tasks.discard)
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

    def _save_context_to_task(self):
        """Sauvegarde le contexte actuel dans la tâche"""
        if self.current_task:
            if not hasattr(self.current_task, 'context'):
                self.current_task.context = {}
            self.current_task.context.update(self.context)
            logger.info(f"💾 Contexte sauvegardé: {list(self.context.keys())}")
        else:
            logger.warning("⚠️ Impossible de sauvegarder le contexte - pas de tâche courante")

    def _normalize_client_info(self, client_info: Any) -> Dict[str, Any]:
        """Normalise la structure client_info pour éviter les erreurs de type None"""
        if not client_info:
            return {"data": {}, "found": False}

        if not isinstance(client_info, dict):
            return {"data": {}, "found": False}

        # S'assurer que data est toujours un dictionnaire
        if "data" not in client_info:
            client_info["data"] = {}
        elif client_info["data"] is None:
            client_info["data"] = {}
        elif not isinstance(client_info["data"], dict):
            client_info["data"] = {}

        return client_info

    async def _send_final_quote_result(self, result_data: dict):
        """Envoie le résultat final du devis via WebSocket"""
        try:
            if hasattr(self, 'task_id') and self.task_id:

                message = {
                    "type": "quote_generation_completed",
                    "task_id": self.task_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "result": result_data,
                    "status": "completed"
                }
                
                await websocket_manager.broadcast_to_task(self.task_id, message)
                logger.info(f"✅ Résultat final envoyé pour {self.task_id}")
                
                # Attendre pour s'assurer que le message est reçu
                await asyncio.sleep(0.5)
            else:
                logger.warning("⚠️ Impossible d'envoyer le résultat - task_id manquant")
        except Exception as e:
            logger.error(f"❌ Erreur envoi résultat final: {e}")
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

            # IMPORTANT: Sauvegarder extracted_info dans le contexte
            self.context["extracted_info"] = extracted_info
            logger.info(f"✅ Contexte initialisé dans process_quote_request - client: {extracted_info.get('client', '')}, produits: {len(extracted_info.get('products', []))}")

            # Enregistrer les informations extraites dans le contexte
            self.context["extracted_info"] = extracted_info
            # NOUVEAU: Sauvegarder le contexte dans la tâche
            self._save_context_to_task()

            # PHASE 2: Exécution du workflow de devis
            self._track_step_start("quote_workflow", "🚀 Démarrage du workflow de devis")
            workflow_result = await self._process_quote_workflow(extracted_info)

            # Cas : interaction utilisateur nécessaire - ARRÊT COMPLET DU WORKFLOW
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
                # ARRÊT IMMÉDIAT - Ne pas continuer le workflow
                logger.info(f"⏸️ Workflow suspendu en attente d'interaction utilisateur")
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

            elif interaction_type == "duplicate_resolution":
                return await self._handle_duplicate_resolution(user_input, context)

            else:
                return self._build_error_response("Type d'interaction non reconnu", f"Type: {interaction_type}")

        except Exception as e:
            logger.exception(f"Erreur continuation workflow: {str(e)}")
            return self._build_error_response("Erreur continuation", str(e))

    # 🔧 HANDLERS POUR CHAQUE TYPE D'INTERACTION

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
            WHERE FederalTaxID LIKE '%{escape_soql(siren)}%'
        """
        result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": query})
        return result.get("data", []) if result.get("success") else []


    async def _search_duplicates_by_name(self, client_name: str) -> list:
        """🔍 Recherche des doublons par mots significatifs dans le nom"""
        words = {word for word in client_name.split() if len(word) > 3}
        if not words:
            return []
        
        conditions = " OR ".join([f"Name LIKE '%{escape_soql(word)}%'" for word in words])
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
    def _format_client_details(self, client: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Formate les détails client selon la source"""
        details = {
            "sf_id": "",
            "sap_code": "",
            "phone": None,
            "address": "N/A",
            "city": None,
            "postal_code": None,
            "country": None,
            "siret": None,
            "industry": "N/A"
        }
        
        if not client:
            return details
            
        source_lower = source.lower() if source else ""
        
        if "salesforce" in source_lower or "sf" in source_lower:
            # Formatage client Salesforce
            details.update({
                "sf_id": client.get("Id", ""),
                "sap_code": "",
                "phone": client.get("Phone"),
                "address": f"{client.get('BillingStreet', '')}, {client.get('BillingCity', '')}".strip(", "),
                "city": client.get("BillingCity"),
                "postal_code": client.get("BillingPostalCode"),
                "country": client.get("BillingCountry"),
                "siret": client.get("Sic"),
                "industry": client.get("Industry", "N/A")
            })
        elif "sap" in source_lower:
            # Formatage client SAP
            details.update({
                "sf_id": "",
                "sap_code": client.get("CardCode", ""),
                "phone": client.get("Phone1"),
                "address": client.get("BillToStreet", "N/A"),
                "city": client.get("City"),
                "postal_code": client.get("ZipCode"),
                "country": client.get("Country"),
                "siret": client.get("FederalTaxID"),
                "industry": "N/A"
            })
        
        return details
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

        # NOUVEAU: Log de debug pour comprendre l'input utilisateur
        logger.info(f"📦 Input utilisateur dans _handle_product_selection:")
        logger.info(f"   - user_input: {user_input}")
        logger.info(f"   - context keys: {list(context.keys())}")

        # Récupérer les données du produit sélectionné
        # L'interface envoie 'selected_product', pas 'selected_data'
        selected_product_data = user_input.get("selected_product") or user_input.get("selected_data")
        product_code = user_input.get("product_code")
        # Récupérer la quantité ORIGINALE depuis extracted_info (en respectant la priorité à user_input)
        extracted_info = self.context.get("extracted_info", {}) or {}
        original_products = extracted_info.get("products") or []

        # Rechercher la quantité originale en faisant correspondre le nom du produit
        original_quantity = 1  # valeur par défaut
        if selected_product_data and original_products:
            selected_name = (selected_product_data.get("ItemName") or "").lower()
            for orig_product in original_products:
                orig_name = (orig_product.get("name") or "").strip().lower()
                if orig_name and orig_name in selected_name:
                    original_quantity = int(orig_product.get("quantity", 1))
                    logger.info(f"📦 Quantité trouvée pour {orig_name}: {original_quantity}")
                    break

        # Quantité: priorité à user_input s'il est fourni et valide
        quantity = user_input.get("quantity")
        try:
            quantity = int(quantity) if quantity is not None else None
        except (TypeError, ValueError):
            quantity = None

        # Utiliser la quantité originale si user_input ne fournit pas de quantité valide
        if quantity is None or quantity <= 0:
            quantity = original_quantity
            logger.info(f"📦 Utilisation de la quantité originale: {quantity}")

        # Garde-fou final
        if quantity is None or quantity <= 0:
            quantity = 1
            logger.info(f"⚠️ Quantité finale par défaut: {quantity}")

        logger.info(f"📦 Quantité finale utilisée: {quantity}")

        def _norm(s):
            return (s or "").strip().lower()

        selected_name = _norm(selected_product_data.get("ItemName"))
        selected_code = selected_product_data.get("ItemCode")

        current_context = context.get("validation_context", {})

        # Logs détaillés pour debug
        logger.info(f"📦 _handle_product_selection - user_input complet: {user_input}")
        logger.info(f"📦 _handle_product_selection - selected_product_data: {selected_product_data}")

        if selected_product_data:
            # CORRECTION: Récupérer le client depuis le contexte avec validation robuste
            # DIAGNOSTIC: Vérifier l'état du contexte
            logger.info(f"🔍 État du contexte lors sélection produit:")
            logger.info(f"   - client_info présent: {bool(self.context.get('client_info'))}")
            logger.info(f"   - client_info.data présent: {bool(self.context.get('client_info', {}).get('data'))}")
            logger.info(f"   - clés contexte: {list(self.context.keys())}")
            # CORRECTION CRITIQUE: S'assurer que les données client sont bien présentes avant la création du devis
            client_info = context.get("client_info")
            if not client_info or not client_info.get("data"):
                # Tenter de récupérer depuis validated_client ou selected_client
                if self.context.get("validated_client"):
                    client_info = {"data": self.context["validated_client"], "found": True}
                    self.context["client_info"] = client_info
                    logger.info("✅ Client restauré depuis validated_client")
                elif self.context.get("selected_client"):
                    client_info = {"data": self.context["selected_client"], "found": True}
                    self.context["client_info"] = client_info
                    logger.info("✅ Client restauré depuis selected_client")
            client_info = self.context.get("client_info", {})

            # Valider que client_info contient bien les données
            if not client_info or not client_info.get("data"):
                logger.error("❌ Données client manquantes dans le contexte lors de la sélection produit")
                return {
                    "success": False,
                    "error": "Données client perdues - impossible de générer le devis"
                }

            # Calcul du prix unitaire avec fallback (Price -> AvgPrice -> unit_price -> estimation)
            unit_price = float(
            (selected_product_data.get("Price")
                or selected_product_data.get("AvgPrice")
                or selected_product_data.get("unit_price")
                or 0)
            )
            if not unit_price:
                unit_price = float(self._estimate_product_price(selected_product_data.get("ItemName", "")) or 0)
            formatted_product = {
                "code": selected_product_data.get("ItemCode"),
                "name": selected_product_data.get("ItemName"),
                "quantity": quantity,  # Utiliser la quantité récupérée
                # Utiliser Price d'abord, puis AvgPrice, puis estimation
                "unit_price": unit_price,
                "total_price": 0, # Sera calculé après
                "found": True,  # Marquer comme produit trouvé
                "OnHand": selected_product_data.get("OnHand", 0),
                # Garder aussi les champs SAP originaux pour compatibilité
                "ItemCode": selected_product_data.get("ItemCode"),
                "ItemName": selected_product_data.get("ItemName"),
                "UnitPrice": unit_price,
            }

            # Calculer le prix total
            formatted_product["total_price"] = unit_price * quantity            
            logger.info(f"✅ Produit formaté: {formatted_product['name']} - Code: {formatted_product['code']} - Prix: {formatted_product['unit_price']}€ - Quantité: {quantity}")
            # CORRECTION: S'assurer que les données client sont bien présentes
            validated_data = {
                "client": client_info.get("data"),
                "products": [formatted_product]
            }

            # NOUVELLE VALIDATION: Vérifier que client_data n'est pas None
            if not validated_data.get("client"):
                logger.error("❌ validated_data.client est None - tentative de récupération alternative")
                # Essayer de récupérer depuis d'autres sources du contexte
                alternative_client = (
                    self.context.get("selected_client") or
                    self.context.get("validated_client") or
                    self.context.get("client_data")
                )
                if alternative_client:
                    validated_data["client"] = alternative_client
                    logger.info("✅ Client récupéré depuis source alternative")
                else:
                    return {
                        "success": False,
                        "error": "Impossible de récupérer les données client pour la génération du devis"
                    }

            logger.info(f"📦 validated_data pour génération: {validated_data}")

            # Continuer directement vers la génération du devis
            logger.info(f"✅ Produit sélectionné avec prix {formatted_product['unit_price']}€, génération du devis.")
            # Préparer quote_data pour la création SAP
            quote_data = {
                "client": validated_data["client"],
                "products": validated_data["products"],
                "total_amount": formatted_product["total_price"],
                "DocumentLines": [{
                    "ItemCode": formatted_product["code"],
                    "ItemName": formatted_product["name"],
                    "ItemDescription": formatted_product["name"],
                    "Quantity": formatted_product["quantity"],
                    "Price": formatted_product["unit_price"],
                    "LineNum": 0
                }]
            }
            # Générer le devis en utilisant les données validées
            return await self._continue_quote_generation(validated_data, quote_data)

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
    async def _continue_quote_generation(self, validated_data: Dict, quote_data: Dict = None) -> Dict[str, Any]:
        """Continue la génération du devis avec les données validées"""
        # Robustesse: garantir un dict pour quote_data
        quote_data = quote_data or {}
        try:
            # S'assurer que les données produits sont complètes avant génération
            if not validated_data.get("products"):
                logger.error("❌ Aucun produit validé pour la génération")
                return self._build_error_response("Données manquantes", "Aucun produit validé")
            
            # Compléter les informations produits si quote_data est fourni
            if quote_data and quote_data.get("DocumentLines"):
                for product in validated_data["products"]:
                    if not product.get("name") and quote_data["DocumentLines"]:
                        doc_line = quote_data["DocumentLines"][0]
                        product.update({
                            "name": doc_line.get("ItemName", product.get("code", "Produit")),
                            "description": doc_line.get("ItemDescription", ""),
                            "ItemName": doc_line.get("ItemName", product.get("code", "Produit")),
                            "ItemCode": product.get("code", doc_line.get("ItemCode", "")),
                            "unit_price": product.get("unit_price", doc_line.get("Price", 0)),
                            "UnitPrice": product.get("unit_price", doc_line.get("Price", 0)),
                            "Price": product.get("unit_price", doc_line.get("Price", 0))
                        })
            # PHASE 3: Génération du devis avec données validées
            # Gérer le cas où validated_data peut être une liste ou un dict
            if isinstance(validated_data, list):
                # Si c'est une liste, la transformer en dict avec clé "products"
                validated_data = {"products": [p.get("data", p) for p in validated_data]}

            # CORRECTION: Récupération robuste des données client
            client_data = validated_data.get("client")
            if not client_data:
                # Fallback vers le contexte
                client_info = self.context.get("client_info", {})
                client_data = client_info.get("data")
                
                # Si toujours pas de données, essayer d'autres sources
                if not client_data:
                    client_data = (
                        self.context.get("selected_client") or
                        self.context.get("validated_client") or
                        self.context.get("client_data")
                    )
                    
                    if client_data:
                        logger.info("✅ Données client récupérées depuis source alternative dans _continue_quote_generation")
                    else:
                        logger.error("❌ Aucune donnée client disponible pour la génération")
                        return self._build_error_response(
                            "Données client manquantes", 
                            "Impossible de générer le devis sans informations client"
                        )
            products_data = validated_data.get("products", self.context.get("products_info", []))

            # Calculs finaux
            # Validation des données avant calculs
            if not isinstance(products_data, list):
                logger.warning("⚠️ products_data n'est pas une liste, correction...")
                products_data = []

            # Initialiser la liste des produits validés
            validated_products_data = []

            # Normaliser et valider chaque produit
            for product in products_data:
                logger.info(f"🔍 Traitement du produit: {product}")

                # Normaliser les champs de prix pour tous types de produits
                normalized_product = dict(product)

                # Gérer les différents formats de prix
                # D'abord essayer UnitPrice (depuis la sélection)
                price = product.get("UnitPrice", 0) or product.get("unit_price", 0)

                # Si pas de UnitPrice/unit_price, essayer AvgPrice
                if not price and product.get("AvgPrice") is not None:
                    price = product.get("AvgPrice")

                # Puis essayer Price
                if not price and product.get("Price") is not None:
                    price = product.get("Price")

                # Convertir en float et s'assurer que c'est un nombre valide
                try:
                    price = float(price) if price else 0
                except:
                    price = 0

                # Définir le prix normalisé
                normalized_product["Price"] = price
                normalized_product["UnitPrice"] = price
                normalized_product["unit_price"] = price  # Pour compatibilité avec _create_quote_in_salesforce

                # Si toujours pas de prix, essayer une estimation
                if price == 0:
                    # Estimation en dernier recours
                    estimated = self._estimate_product_price(product.get("ItemName", product.get("name", "")))
                    normalized_product["Price"] = estimated
                    normalized_product["UnitPrice"] = estimated
                    normalized_product["unit_price"] = estimated
                    logger.info(f"Prix estimé appliqué: {estimated}€ pour {product.get('ItemName', product.get('name', 'produit'))}")

                # Calculer le LineTotal
                quantity = float(product.get("Quantity", product.get("quantity", 1)))
                normalized_product["LineTotal"] = normalized_product["Price"] * quantity
                normalized_product["total_price"] = normalized_product["Price"] * quantity  # Pour compatibilité

                # Vérifier les champs requis après normalisation
                if isinstance(normalized_product, dict) and normalized_product.get("Price", 0) > 0:
                    validated_products_data.append(normalized_product)
                    logger.info(f"✅ Produit validé: {normalized_product.get('ItemName', normalized_product.get('name'))} - Prix: {normalized_product.get('Price')}€")
                else:
                    logger.warning(f"⚠️ Produit sans prix valide ignoré: {product}")

            # Vérifier qu'au moins un produit est valide
            if not validated_products_data:
                logger.error("❌ Aucun produit valide après normalisation des prix")
                return {
                    "success": False,
                    "error": "Aucun produit valide trouvé. Vérifiez que tous les produits ont un prix."
                }

            # Utiliser les produits validés pour la suite
            products_data = validated_products_data
            total_amount = sum(p.get("LineTotal", 0) for p in products_data)

            # Génération SAP (passer quote_data si disponible)
            sap_quote = await self._create_sap_quote(client_data, products_data, quote_data)

            # Devis créé dans SAP (source de vérité) — plus de miroir Salesforce
            if sap_quote.get("success"):
                self._track_step_complete("generate_quote", f"✅ Devis généré - Total: {total_amount:.2f}€")
                # Normaliser les identifiants avant retour
                sap_doc_num = (
                sap_quote.get("quote_number")
                    or quote_data.get("DocNum")
                    or validated_data.get("quote_number")
                    or "UNKNOWN"
                )
                sf_id = None
                # Récupérer les résultats des systèmes

                # Si pas de doc_num dans sap, essayer d'autres sources
                if not sap_doc_num:
                    sap_doc_num = quote_data.get("sap_doc_num") or quote_data.get("quote_number") or "UNKNOWN"

                return {
                    "success": True,
                    "status": "success",
                    "quote_id": f"SAP-{sap_doc_num}",
                    "client": validated_data.get("client", {}),
                    "products": validated_data.get("products", []),
                    "quote_data": {
                        "products": validated_data.get("products", []),
                        "client": validated_data.get("client", {}),
                        "total_amount": validated_data.get("total_amount", total_amount)
                    },
                    "validated_data": {
                        "products": validated_data.get("products", []),
                        "client": validated_data.get("client", {}),
                        "total_amount": validated_data.get("total_amount", total_amount)
                    },
                    "total_amount": validated_data.get("total_amount", total_amount),
                    "currency": "EUR",
                    "sap_doc_num": sap_doc_num,
                    "salesforce_opportunity_id": sf_id,
                    "opportunity_id": sf_id,
                    "salesforce_quote_id": sf_id,
                    "date": datetime.now().strftime('%Y-%m-%d'),
                    "quote_status": "Créé",
                    "message": f"Devis créé avec succès pour {validated_data.get('client', {}).get('name', 'le client')}"
                }
            else:
                self._track_step_fail("generate_quote", "Erreur SAP", sap_quote.get("error"))
                return self._build_error_response("Erreur génération", sap_quote.get("error"))

        except Exception as e:
            logger.exception(f"Erreur génération finale: {str(e)}")
            return self._build_error_response("Erreur génération", str(e))

    # Méthodes auxiliaires pour la génération
    async def _create_sap_quote(self, client_data: Dict, products_data: List[Dict], quote_data: Dict = None) -> Dict[str, Any]:
        """Crée le devis dans SAP"""
        try:
            # Utiliser la méthode existante _create_quote_in_salesforce qui gère SAP et Salesforce
            self.context["client_info"] = {"data": client_data, "found": True}
            self.context["products_info"] = products_data

            result = await self._create_quote_in_salesforce(client_data, products_data, quote_data)
            return {
                "success": result.get("success", False),
                "quote_number": result.get("sap_quote_number"),
                "error": result.get("error")
            }
        except Exception as e:
            logger.exception(f"Erreur création devis SAP: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _handle_duplicate_resolution(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la résolution des doublons de devis"""

        action = user_input.get("action")
        client_name = context.get("extracted_info", {}).get("client", "")

        logger.info(f"Résolution doublons: action={action}, client={client_name}")

        if action == "proceed":
            # Forcer la création malgré les doublons
            logger.info("✅ Utilisateur décide de créer un nouveau devis malgré les doublons")
            self.context["skip_duplicate_check"] = True
            extracted_info = context.get("extracted_info", {})
            return await self._process_quote_workflow(extracted_info)

        elif action == "consolidate":
            # Permettre de choisir un devis à consolider
            selected_quote_id = user_input.get("selected_quote_id")
            if selected_quote_id:
                # TODO: Implémenter la logique de consolidation
                return {
                    "status": "consolidation_in_progress",
                    "message": f"Consolidation avec devis {selected_quote_id} en cours...",
                    "selected_quote": selected_quote_id
                }
            else:
                return {
                    "status": "user_interaction_required",
                    "interaction_type": "quote_selection",
                    "message": "Sélectionnez le devis à consolider",
                    "available_quotes": context.get("recent_quotes", []) + context.get("draft_quotes", [])
                }

        elif action == "review":
            # Rediriger vers l'interface de gestion des devis
            return {
                "status": "redirect_to_management",
                "message": "Redirection vers la gestion des devis existants",
                "redirect_url": "/quote-management",
                "client_filter": client_name
            }

        elif action == "cancel":
            return {
                "status": "cancelled",
                "message": "Demande de devis annulée par l'utilisateur"
            }

        return {"status": "error", "message": "Action non reconnue"}

    async def process_prompt(self, user_prompt: str, task_id: str = None) -> Dict[str, Any]:
        """IMPORTANT: Utiliser le task_id fourni, ne jamais le régénérer"""
        """
        Traite un prompt avec tracking de progression
        """
        extracted_info: Optional[Dict[str, Any]] = None
        """Process le prompt utilisateur via LLM et workflow"""
        try:
            # 🔧 MODIFICATION : Utiliser le task_id fourni si disponible
            if task_id:
                self.task_id = task_id
                logger.info(f"✅ Utilisation du task_id fourni: {task_id}")
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
                    # ARRÊT COMPLET - Pas d'appel à complete_task ni de broadcast
                    return result
        
            # Assurer que le résultat final est envoyé via WebSocket SEULEMENT si terminé
            if result.get("status") != "user_interaction_required":
                try:
                    # Envoyer le résultat via WebSocket
                    await websocket_manager.broadcast_to_task(
                        self.task_id,
                        {
                            "type": "quote_generation_completed",
                            "task_id": self.task_id,
                            "result": result,
                            "status": "completed",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    logger.info(f"🔔 Résultat final envoyé via WebSocket pour la tâche {self.task_id}")

                    # Attendre brièvement pour s'assurer que le client a reçu le message
                    await asyncio.sleep(1.0)

                except Exception as ws_error:
                    logger.error(f"❌ Erreur lors de l'envoi du résultat via WebSocket pour {self.task_id}: {ws_error}")
                    raise  # Relever l'erreur pour éviter de marquer la tâche comme terminée si l'envoi échoue

                # Marquer la tâche comme terminée uniquement si l'envoi WebSocket a réussi
                if self.current_task:
                    try:
                        progress_tracker.complete_task(self.task_id, result)
                        logger.info(f"✅ Tâche {self.task_id} marquée comme terminée avec succès.")
                    except Exception as complete_error:
                        logger.error(f"❌ Erreur lors de la finalisation de la tâche {self.task_id}: {complete_error}")
                        raise  # Relever l'erreur pour éviter de laisser la tâche dans un état incohérent

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
            
            # === ÉTAPE 3: VALIDATION UTILISATEUR ===
            logger.info("🔍 Étape 3: Validation utilisateur")
            
            # Demande validation utilisateur OBLIGATOIRE
            try:
                validation_request = await self._request_user_validation_for_client_creation(
                    client_name, 
                    {
                        "enrichment_data": enrichment_data,
                        "validation_result": validation_result,
                        "duplicate_check": duplicate_check
                    }
                )
                
                # PLUS D'AUTO-APPROBATION - Toujours demander validation utilisateur
                logger.warning("⚠️ BLOQUAGE: find_client_everywhere n'a trouvé AUCUN client existant")
                validation_request["status"] = "requires_user_confirmation"
                validation_request["requires_explicit_approval"] = True
                    
            except Exception as e:
                logger.warning(f"⚠️ Erreur validation utilisateur: {str(e)}")
                # Pas de fallback auto-approuvé - on bloque
                validation_request = {"status": "requires_user_confirmation", "requires_explicit_approval": True, "error": str(e)}
            
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
                # === VALIDATION UTILISATEUR REQUISE ===
                logger.info("⏸️ Validation utilisateur requise - Aucune auto-approbation")
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
                    "user_action_required": True,
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

    async def _request_user_validation_for_client_creation(self, client_name: str, context_data: Dict) -> Dict[str, Any]:
        """Demande validation utilisateur pour création client"""
        logger.info(f"📤 Demande validation création client: {client_name}")
        
        try:
            # Construire le message d'interaction utilisateur
            interaction_data = {
                "type": "client_creation_request",
                "client_name": client_name,
                "context_data": context_data,
                "message": f"Client '{client_name}' non trouvé. Souhaitez-vous le créer ?",
                "options": [
                    {"action": "create", "label": "Créer le client"},
                    {"action": "cancel", "label": "Annuler"}
                ]
            }
            
            # Envoyer via WebSocket pour interaction utilisateur
            if self.current_task:
                self.current_task.require_user_validation("client_creation", "client_creation_validation", interaction_data)
            
            try:
                await websocket_manager.send_user_interaction_required(self.task_id, interaction_data)
            except Exception as ws_error:
                logger.warning(f"⚠️ Erreur envoi WebSocket: {ws_error}")
            
            # En mode POC, retourner requires_user_confirmation au lieu d'approved
            logger.warning("⚠️ BLOQUAGE: find_client_everywhere n'a trouvé AUCUN client existant")
            return {
                "status": "requires_user_confirmation",
                "requires_explicit_approval": True,
                "interaction_sent": True
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur validation utilisateur: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
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
                WHERE Id = '{escape_soql(client_id)}'
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
                "Notes": f"Client cree automatiquement par NOVA le {datetime.now().strftime('%d/%m/%Y')}",
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
    
    async def _create_quote_in_salesforce(self, client_info: Dict = None, products_info: List[Dict] = None,
                                     quote_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Crée un devis dans Salesforce"""
        # CORRECTION: Définir valid_products au début
        valid_products = []
        salesforce_quote = None
        try:
            """Crée un devis dans Salesforce"""
            # CORRECTION: Utiliser les paramètres fournis si disponibles, sinon récupérer du contexte
            if not client_info:
                client_info = self.context.get("client_info", {})
            if not products_info:
                products_info = self.context.get("products_info", [])
            # NOUVELLE VÉRIFICATION : S'assurer que client_info n'est pas None
            if client_info is None:
                logger.error("❌ client_info est None, impossible de créer le devis")
                return {
                    "success": False,
                    "error": "Informations client manquantes pour créer le devis"
                }

            logger.info("=== DÉBUT CRÉATION DEVIS SAP ET SALESFORCE ===")

            # Récupération des données du contexte
            # Utiliser client_info déjà défini au lieu de le redéfinir
            sap_client = self.context.get("sap_client", {})

            # Log du contexte disponible
            logger.info(f"Client info disponible: {bool(client_info.get('found'))}")
            logger.info(f"Produits disponibles: {len(products_info)}")
            logger.info(f"Client SAP disponible: {bool(sap_client.get('data'))}")

            try:
                # ========== ÉTAPE 1: PRÉPARATION DES DONNÉES DE BASE ==========

                # Récupérer les données client Salesforce - maintenant garanti d'être un dictionnaire
                sf_client_data = client_info.get("data") if client_info else None
                # CORRECTION: Vérifier aussi dans validated_client et selected_client
                if sf_client_data is None and not self.context.get("validated_client") and not self.context.get("selected_client"):
                    # Tenter de reconstituer depuis le contexte du workflow
                    if hasattr(self, 'current_task') and self.current_task:
                        if hasattr(self.current_task, 'context'):
                            task_context = self.current_task.context
                            if task_context.get("client_info", {}).get("data"):
                                sf_client_data = task_context["client_info"]["data"]
                                client_info = task_context["client_info"]
                                self.context["client_info"] = client_info
                                logger.info("✅ Client récupéré depuis le contexte de la tâche")
                # NOUVELLE VÉRIFICATION : Si sf_client_data est toujours None, essayer de le récupérer autrement
                if sf_client_data is None:
                    logger.warning("⚠️ sf_client_data est None, tentative de récupération depuis le contexte")
                    # Essayer différentes sources possibles
                    if self.context.get("validated_client"):
                        sf_client_data = self.context["validated_client"]
                        logger.info("✅ Client récupéré depuis validated_client")
                    elif self.context.get("selected_client"):
                        sf_client_data = self.context["selected_client"]
                        logger.info("✅ Client récupéré depuis selected_client")
                    else:
                        # En dernier recours, chercher dans les tâches
                        from services.progress_tracker import progress_tracker
                        task = progress_tracker.get_task(self.task_id) if self.task_id else None
                        if task and hasattr(task, 'context') and task.context.get("client_data"):
                            sf_client_data = task.context["client_data"]
                            logger.info("✅ Client récupéré depuis la tâche")
                        else:
                            logger.error("❌ Impossible de récupérer les données client depuis aucune source")
                            return {
                                "success": False,
                                "error": "Données client introuvables dans le contexte - veuillez relancer le processus"
                            }

                client_name = sf_client_data.get("Name", "Client Unknown") if sf_client_data else "Client Unknown"
                client_id = sf_client_data.get("Id", "") if sf_client_data else ""

                logger.info(f"Client Salesforce: {client_name} (ID: {client_id})")
                # Vérifier si le client a un code SAP dans ses données
                # CORRECTION: Vérifier dans plusieurs emplacements possibles

                client_sap_code = (
                    client_info.get("data", {}).get("sap_code")
                    or client_info.get("sap_code")
                    or self.context.get("client_sap_code")
                    or (client_info.get("data", {}).get("details", {}) or {}).get("sap_code")
                )
                if client_sap_code:
                    logger.info(f"Client SAP trouvé dans les données: {client_sap_code}")
                else:
                    logger.info("Client SAP non trouvé, création nécessaire...")
                # Créer le client SAP si nécessaire
                logger.info("=== CRÉATION/VÉRIFICATION CLIENT SAP ===")
                sap_card_code = client_sap_code  # Initialisation explicite

                if not sap_client or not sap_client.get("data"):
                    if sap_card_code:
                        logger.info(f"✅ [SAP] Client existant utilisé: {sap_card_code}")
                        self.context["sap_client"] = {
                            "data": {"CardCode": sap_card_code},
                            "created": False
                        }
                        sap_client = self.context["sap_client"]
                        logger.info(f"✅ [SAP] Client configuré: {sap_card_code}")
                    else:
                        logger.info("⚠️ [SAP] Client non trouvé, création nécessaire...")
                        sap_client_result = await self._create_sap_client_if_needed(client_info)
                        if sap_client_result.get("success") and sap_client_result.get("client"):
                            self.context["sap_client"] = {
                                "data": sap_client_result["client"],
                                "created": True
                            }
                            sap_client = self.context["sap_client"]
                            logger.info(f"✅ [SAP] Client disponible: {sap_client_result['client'].get('CardCode')}")
                else:
                    logger.info(f"✅ [SAP] Client déjà disponible dans le contexte")

                
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
                
                # Séparer les produits trouvés des produits personnalisés
                found_products = [p for p in products_info if isinstance(p, dict) and p.get("found", False)]
                custom_products = [p for p in products_info if isinstance(p, dict) and p.get("custom_product", False)]
                
                # Traiter TOUS les produits pour s'assurer d'avoir des prix
                all_products = found_products + custom_products
                for product in all_products:
                    unit_price = product.get("unit_price", 0)

                    # Si prix = 0, essayer de récupérer depuis sap_data
                    if unit_price == 0 and product.get("sap_data"):
                        sap_price = product["sap_data"].get("AvgPrice", 0)
                        if sap_price > 0:
                            unit_price = sap_price
                            product["unit_price"] = unit_price
                            product["total_price"] = unit_price * product.get("quantity", 1)
                            logger.info(f"Prix SAP utilisé pour {product.get('name')}: {sap_price}€")
                            continue

                    # Si toujours pas de prix, utiliser l'estimation
                    if unit_price == 0:
                        logger.warning(f"⚠️ Produit sans prix détecté: {product.get('name')} - Utilisation estimation")
                        default_price = self._estimate_product_price(product.get("name", ""))
                        product["unit_price"] = default_price
                        product["Price"] = default_price  # AJOUT: Définir aussi le champ Price pour la validation
                        product["total_price"] = default_price * product.get("quantity", 1)
                        logger.info(f"Prix estimé pour {product['name']}: {default_price}€")

                # Combiner tous les produits
                valid_products = all_products
                
                if not valid_products:
                    logger.error("❌ AUCUN PRODUIT VALIDE - Impossible de créer un devis")
                    return {
                        "success": False,
                        "error": "Aucun produit valide disponible pour créer le devis. Veuillez sélectionner des produits du catalogue.",
                        "requires_product_selection": True
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
                        "ItemCode": product.get("code") or f"UNKNOWN-{idx}",
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
                if not sap_card_code:
                    logger.error("❌ CardCode SAP manquant")
                    return {"success": False, "error": "Code client SAP requis"}
                if not document_lines:
                    logger.error("❌ Aucune ligne de produit")
                    return {"success": False, "error": "Au moins un produit requis"}
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
                    "Comments": f"Devis cree automatiquement via NOVA le {today.strftime('%d/%m/%Y %H:%M')} - Mode: {'DRAFT' if self.draft_mode else 'NORMAL'}",
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
                        # Validation finale des prix avant envoi à SAP
                        # Vérifier que quote_data contient DocumentLines avant d'itérer
                        if not quote_data or not isinstance(quote_data, dict):
                            logger.error("❌ quote_data invalide pour Salesforce")
                            return {
                                "success": False,
                                "error": "Données de devis invalides pour Salesforce"
                            }

                        document_lines = quote_data.get("DocumentLines", [])
                        if not document_lines:
                            logger.warning("⚠️ Aucune ligne de document dans quote_data")
                            return {
                                "success": False,
                                "error": "Aucune ligne de produit à synchroniser avec Salesforce"
                            }
                            # Traitement des lignes existant
                        for line in document_lines:
                            if line.get("Price", 0) == 0:
                                estimated = self._estimate_product_price(line.get("ItemDescription", ""))
                                line["Price"] = estimated
                                logger.warning(f"⚠️ Prix 0 détecté pour {line.get('ItemCode')} - Application prix estimé: {estimated}€")

                        logger.info("Appel SAP en mode NORMAL...")
                        sap_quote = await MCPConnector.call_sap_mcp("sap_create_quotation_complete", {
                            "quotation_data": quotation_data
                        })
                    
                    logger.info("=== RÉSULTAT APPEL SAP ===")
                    # Vérification et traitement du résultat SAP
                    if sap_quote is None:
                        logger.error("❌ SAP a retourné None!")
                        return {
                            "success": False,
                            "error": "L'appel SAP a retourné None",
                            "sap_attempted": True,
                            "salesforce_attempted": False
                        }

                    if isinstance(sap_quote, dict) and "error" in sap_quote:
                        logger.error(f"❌ Erreur SAP: {sap_quote.get('error')}")
                        return {
                            "success": False,
                            "error": f"Erreur SAP: {sap_quote.get('error')}",
                            "sap_attempted": True,
                            "salesforce_attempted": False
                        }

                    if not isinstance(sap_quote, dict):
                        logger.error(f"❌ SAP a retourné un type invalide: {type(sap_quote)}")
                        return {
                            "success": False,
                            "error": f"Type de réponse SAP invalide: {type(sap_quote)}",
                            "sap_attempted": True,
                            "salesforce_attempted": False
                        }
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
                        # Notification WebSocket du succès
                        await websocket_manager.send_task_update(self.task_id, {
                            "type": "quote_created",
                            "status": "success",
                            "quote_data": {
                                "sap_doc_num": sap_quote.get("doc_num"),
                                "sf_opportunity_id": salesforce_quote.get("id") if salesforce_quote else None,
                                "total": total_amount if total_amount > 0 else 0
                            }
                        })
                except Exception as e:
                    logger.exception(f"❌ EXCEPTION lors de l'appel SAP: {str(e)}")
                    sap_quote = {"success": False, "error": f"Exception lors de l'appel SAP: {str(e)}"}
                
                # ========== ÉTAPE 6: CONSTRUCTION DE LA RÉPONSE ==========
                
                logger.info("=== CONSTRUCTION RÉPONSE FINALE ===")
                
                # Déterminer le succès global
                sap_success = sap_quote and sap_quote.get("success", False)
                sf_success = False

                # SAP est la source de vérité : le succès dépend uniquement de SAP
                overall_success = sap_success

                # Construire la réponse finale
                result = {
                    "success": overall_success,
                    "quote_id": f"SAP-{sap_quote.get('doc_num', 'FAILED')}" if sap_success else f"FAILED-{today.strftime('%Y%m%d-%H%M%S')}",
                    "sap_doc_entry": sap_quote.get("doc_entry") if sap_success else None,
                    "sap_doc_num": sap_quote.get("doc_num") if sap_success else None,
                    "salesforce_quote_id": salesforce_quote.get("id") if sf_success else None,
                    "opportunity_id": salesforce_quote.get("id") if sf_success else None,
                    "status": "Created" if overall_success else "Failed",
                    "total_amount": total_amount,
                    "currency": "EUR",
                    "draft_mode": self.draft_mode,
                    "sap_results": sap_quote,
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
                # Envoyer le résultat final via WebSocket
                await self._send_final_quote_result({
                    "success": overall_success,
                    "quote_id": result["quote_id"],
                    "sap_doc_num": sap_quote.get('doc_num') if sap_success else None,
                    "salesforce_opportunity_id": salesforce_quote.get('id') if sf_success else None,
                    "client": client_name,
                    "products": valid_products,
                    "total_amount": total_amount,
                    "message": result["message"]
                    })
                
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
            except asyncio.CancelledError:
                logger.warning("⚠️ Création devis interrompue par l'utilisateur")
                return {"success": False, "error": "Opération interrompue", "cancelled": True}
        except Exception as e:
                logger.exception(f"❌ ERREUR CRITIQUE dans _create_quote_in_salesforce: {str(e)}")
        
    def _estimate_product_price(self, product_name: str) -> float:
        """Estime un prix par défaut basé sur le nom du produit"""
        if not product_name:
            return 100.0
        product_lower = product_name.lower()

        # Règles d'estimation améliorées
        if "imprimante" in product_lower or "printer" in product_lower:
            if any(word in product_lower for word in ["laser", "professional", "pro", "bureau"]):
                return 450.0
            elif "couleur" in product_lower or "color" in product_lower:
                return 320.0
            else:
                return 180.0
        elif any(word in product_lower for word in ["ordinateur", "pc", "computer", "desktop"]):
            if "portable" in product_lower or "laptop" in product_lower:
                return 950.0
            else:
                return 750.0
        elif any(word in product_lower for word in ["écran", "moniteur", "screen", "monitor"]):
            if "4k" in product_lower or "uhd" in product_lower:
                return 380.0
            else:
                return 220.0
        elif any(word in product_lower for word in ["serveur", "server"]):
            return 2500.0
        elif any(word in product_lower for word in ["switch", "routeur", "router", "réseau"]):
            return 180.0
        elif any(word in product_lower for word in ["clavier", "keyboard", "souris", "mouse"]):
            return 45.0
        else:
            # Prix par défaut basé sur des mots-clés génériques
            if "enterprise" in product_lower or "professionnel" in product_lower:
                return 250.0
            else:
                return 120.0
            
    async def _create_sap_client_if_needed(self, client_info):
        """Crée un client SAP si nécessaire (robuste, schéma de retour stable)"""
        import logging
        from datetime import datetime
        logger = logging.getLogger(__name__)

        # Helpers
        def _has_method(obj, name: str) -> bool:
            return hasattr(obj, name) and callable(getattr(obj, name))

        async def _sap_call_search(query: str):
            payload = {"query": query, "entity_type": "BusinessPartners", "limit": 5}
            if _has_method(self.mcp_connector, "call_sap_mcp"):
                return await self.mcp_connector.call_sap_mcp("sap_search", payload)
            # fallback ancien schéma
            if _has_method(self.mcp_connector, "call_mcp"):
                return await self.mcp_connector.call_mcp("sap_mcp", "sap_search", payload)
            raise RuntimeError("Aucune méthode SAP MCP disponible")

        async def _sap_call_create(customer_data: dict):
            if _has_method(self.mcp_connector, "call_sap_mcp"):
                # tenter l’endpoint complet puis fallback
                try:
                    return await self.mcp_connector.call_sap_mcp(
                        "sap_create_customer_complete", {"customer_data": customer_data}
                    )
                except Exception:
                    return await self.mcp_connector.call_sap_mcp(
                        "sap_create_customer", {"customer_data": customer_data}
                    )
            if _has_method(self.mcp_connector, "call_mcp"):
                # fallback ancien schéma
                try:
                    return await self.mcp_connector.call_mcp(
                        "sap_mcp", "sap_create_customer_complete", {"customer_data": customer_data}
                    )
                except Exception:
                    return await self.mcp_connector.call_mcp(
                        "sap_mcp", "sap_create_customer", {"customer_data": customer_data}
                    )
            raise RuntimeError("Aucune méthode SAP MCP disponible")

        try:
            client_data = (client_info or {}).get("data", {})
            client_name = (client_data.get("Name") or "").strip()

            if not client_name:
                return {"success": False, "error": "Nom client manquant"}

            # 1) Recherche existant
            search_result = await _sap_call_search(client_name)
            if isinstance(search_result, dict) and "error" not in search_result:
                candidates = []
                if isinstance(search_result.get("value"), list):
                    candidates = search_result["value"]
                elif isinstance(search_result.get("results"), list):
                    candidates = search_result["results"]
                elif search_result.get("count", 0) > 0 and isinstance(search_result.get("results"), list):
                    candidates = search_result["results"]

                if candidates:
                    found = candidates[0]
                    logger.info("✅ Client SAP trouvé: %s - %s",
                                found.get("CardCode"), found.get("CardName"))
                    return {"success": True, "client": found, "created": False}

            # 2) Création
            # CardCode <= 15, unique à la seconde: "C" + YYMMDDHHMMSS + 2 digits µs
            card_code = f"C{datetime.now():%y%m%d%H%M%S}{datetime.now():%f}"[:15]

            customer_data = {
                "CardCode": card_code,
                "CardName": client_name,
                "CardType": "cCustomer",
                "Currency": "EUR",
            }
            # Conserver GroupCode si présent côté v1
            if "GroupCode" in client_data:
                customer_data["GroupCode"] = client_data["GroupCode"]
            else:
                # valeur raisonnable si besoin de groupe
                customer_data["GroupCode"] = 100

            create_result = await _sap_call_create(customer_data)
            if isinstance(create_result, dict) and create_result.get("success"):
                logger.info("✅ Client SAP créé: %s", card_code)
                return {
                    "success": True,
                    "client": {"CardCode": card_code, "CardName": client_name},
                    "created": True,
                }

            err = (create_result or {}).get("error", "Erreur inconnue")
            logger.error("❌ Échec création client SAP: %s", err)
            return {"success": False, "error": err}

        except Exception as e:
            logger.error("❌ Exception création client SAP: %s", e)
            return {"success": False, "error": str(e)}

    
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
        """🔧 Construit la réponse finale avec nom client correct (compat + optimisations légères)"""
        logger.info("Construction de la réponse finale enrichie")
        client_info = self.context.get("client_info", {}) or {}
        quote_result = self.context.get("quote_result", {}) or {}
        sap_client = self.context.get("sap_client", {}) or {}
        client_validation = self.context.get("client_validation", {}) or {}
        products_info = self.context.get("products_info", []) or []
        extracted_info = self.context.get("extracted_info", {}) or {}
        validated_data = self.context.get("validated_data", {}) or {}

        # Erreurs bloquantes en amont
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

        # Extraction robuste du nom client
        client_name = "Client extrait"
        if self.context.get("client_info", {}).get("data", {}).get("Name"):
            client_name = self.context.get("client_info", {}).get("data", {}).get("Name", "")
            logger.info(f"✅ Nom client depuis context Salesforce: {client_name}")
        elif self.context.get("client_info", {}).get("data", {}).get("CardName"):
            sap_name = self.context.get("client_info", {}).get("data", {}).get("CardName", "")
            client_name = sap_name.split(" - ", 1)[1].strip() if " - " in sap_name else sap_name
            logger.info(f"✅ Nom client depuis context SAP (nettoyé): {client_name}")
        elif self.context.get("extracted_info", {}).get("client"):
            client_name = self.context["extracted_info"]["client"]
            logger.info(f"✅ Nom client depuis extraction LLM: {client_name}")
        elif extracted_info.get("client"):
            client_name = extracted_info["client"]
            logger.info(f"✅ Nom client depuis extraction LLM: {client_name}")
        elif quote_result.get("sap_results", {}).get("raw_result", {}).get("CardName"):
            client_name = quote_result["sap_results"]["raw_result"]["CardName"]
            logger.info(f"✅ Nom client depuis SAP raw result: {client_name}")
        logger.info(f"🎯 Nom client final pour interface: '{client_name}'")

        # Données client (compat + address structurée + fallback SAP)
        vcli = validated_data.get("client", {}) or {}
        cdata = client_info.get("data", {}) or {}
        account_number = (
            vcli.get("AccountNumber")
            or cdata.get("AccountNumber")
            or (sap_client.get("data", {}) or {}).get("CardCode")
            or ""
        )
        salesforce_id = vcli.get("Id") or cdata.get("Id") or ""
        client_response = {
            "name": client_name,
            "id": vcli.get("Id", salesforce_id),
            "salesforce_id": salesforce_id,
            "account_number": account_number,
            "address": {
                "street": vcli.get("BillingStreet") or cdata.get("BillingStreet"),
                "city": vcli.get("BillingCity") or cdata.get("BillingCity"),
                "postal_code": vcli.get("BillingPostalCode") or cdata.get("BillingPostalCode"),
                "country": vcli.get("BillingCountry") or cdata.get("BillingCountry"),
            },
            "email": vcli.get("Email") or cdata.get("Email"),
            "city": vcli.get("BillingCity") or cdata.get("BillingCity"),
            "country": vcli.get("BillingCountry") or cdata.get("BillingCountry"),
            "phone": vcli.get("Phone") or cdata.get("Phone"),
            "industry": (vcli.get("details", {}) or {}).get("industry"),
        }

        # Produits (fallback: validated_data.products puis products_info, en filtrant les erreurs)
        source_products = (validated_data.get("products") or []) or products_info
        products_response = []
        for product in source_products:
            if not isinstance(product, dict) or ("error" in product):
                continue
            product_code = product.get("code") or product.get("item_code") or product.get("ItemCode")
            product_name = product.get("name") or product.get("item_name") or product.get("ItemName")
            # coercition sûre
            try:
                quantity = float(product.get("quantity", 1) or 1)
            except (TypeError, ValueError):
                quantity = 1.0
            try:
                unit_price = float(product.get("unit_price", product.get("UnitPrice", 0)) or 0)
            except (TypeError, ValueError):
                unit_price = 0.0
            line_total = quantity * unit_price

            product_data = {
                "code": product_code or "",
                "name": product_name or "Sans nom",
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
                "stock_available": self._get_stock_value(product),
                "available": self._get_stock_safely(product) >= quantity,
                "description": product.get("U_Description", ""),
                "manufacturer": product.get("Manufacturer", ""),
                "sales_unit": product.get("SalesUnit", "UN")
            }
            products_response.append(product_data)
            logger.info(f"✅ Produit formaté dans réponse: {product_data['code']} x{quantity} = {line_total}€")

        total_amount = round(sum(float(p.get("line_total", 0) or 0) for p in products_response), 2)
        all_available = all(bool(p.get("available", False)) for p in products_response)

        # Quote ID hybride: priorité SAP, puis SF, puis NOVA-TS
        quote_id = (
            (f"SAP-{quote_result.get('sap_doc_num')}" if quote_result.get('sap_doc_num') else None)
            or (f"SAP-{quote_result.get('doc_num')}" if quote_result.get('doc_num') else None)
            or quote_result.get("opportunity_id")
            or f"NOVA-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )

        # Réponse
        response = {
            "success": True,
            "status": "success",
            "quote_id": quote_id,
            "client": client_response,
            "products": products_response,
            "total_amount": total_amount,
            "currency": "EUR",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "quote_status": "Created",
            "all_products_available": all_available,
            "sap_doc_num": quote_result.get("sap_doc_num"),
            "salesforce_quote_id": quote_result.get("opportunity_id"),
            "message": f"Devis généré avec succès pour {client_name}",
            "draft_mode": self.draft_mode
        }

        # Validation client
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

        # Doublons devis
        duplicate_check = self.context.get("duplicate_check", {}) or {}
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

        # Références système
        response["system_references"] = {
            "sap_client_created": sap_client.get("created", False) if sap_client else False,
            "sap_client_card_code": (sap_client.get("data", {}) or {}).get("CardCode") if sap_client else None,
            "quote_creation_timestamp": datetime.now().isoformat(),
            "validation_enabled": self.validation_enabled
        }

        logger.info(f"✅ Réponse finale enrichie construite avec nom client: {client_name}")
        response["workflow_steps"] = self.workflow_steps

        # Visualisation
        if quote_result.get("success") and response.get("success"):
            response["quote_visualization"] = {
                "display_mode": "detailed",
                "document_data": {
                    "quote_number": response.get("quote_id", (
                        "SAP-" + (quote_result.get('sap_doc_num') or quote_result.get('doc_num') or 'DRAFT')
                    )),
                    "issue_date": datetime.now().strftime("%d/%m/%Y"),
                    "due_date": (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y"),
                    "validity": "30 jours",
                    "client_info": client_response,
                    "products_list": products_response,
                    "totals": {
                        "subtotal_ht": total_amount,
                        "tva_rate": 20.0,
                        "tva_amount": round(total_amount * 0.2, 2),
                        "total_ttc": round(total_amount * 1.2, 2)
                    },
                    "terms": "Devis valable 30 jours - Paiement a 30 jours",
                    "created_by": "NOVA Assistant",
                    "company_info": {
                        "name": "IT SPIRIT",
                        "address": "305, rue Gabriel Voisin, 69400 Villefranche-sur-Saône",
                        "phone": "06 26 26 74 21",
                        "website": "www.it-spirit.fr"
                    }
                },
                "template": "nova_interface_final",
                "actions": [
                    {"id": "download_pdf", "label": "Télécharger PDF", "icon": "download"},
                    {"id": "send_email", "label": "Envoyer par email", "icon": "mail"},
                    {"id": "create_new", "label": "Nouveau devis", "icon": "plus"}
                ]
            }

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
            query = f"SELECT Id, Name, AccountNumber, AnnualRevenue, LastActivityDate FROM Account WHERE Name LIKE '%{escape_soql(client_name)}%' LIMIT 10"
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
            
            # 1. Vérifier les devis SAP récents (dernières 1440h = 2 mois)
            recent_quotes = await self._get_recent_sap_quotes(client_name, hours=1440)
            
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

                # Créer le message d'alerte personnalisé et demander décision utilisateur
                if duplicate_check.get("duplicates_found"):
                    alert_message = f"⚠️ ATTENTION: Devis existants détectés pour {client_name}"

                    if recent_quotes:
                        alert_message += f"\n📋 {len(recent_quotes)} devis récent(s) d'imprimantes"
                    if draft_quotes:
                        alert_message += f"\n✏️ {len(draft_quotes)} devis en brouillon"
                    if similar_quotes:
                        alert_message += f"\n🔄 {len(similar_quotes)} devis avec produits similaires"

                    duplicate_check["alert_message"] = alert_message
                    duplicate_check["requires_user_decision"] = True

                    logger.warning(f"⚠️ {len(duplicate_check.get('warnings', []))} doublons détectés")

                    return duplicate_check
            
            else:
                duplicate_check["suggestions"].append("✅ Aucun doublon détecté - Création sécurisée")
                
            logger.info(f"Vérification doublons terminée: {total_findings} potentiel(s) doublon(s)")
            return duplicate_check
            
        except Exception as e:
            logger.exception(f"Erreur vérification doublons devis: {str(e)}")
            duplicate_check["warnings"].append(f"❌ Erreur vérification doublons: {str(e)}")
            return duplicate_check

    async def _get_recent_sap_quotes(self, client_name: str, hours: int = 1440) -> List[Dict[str, Any]]:
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
            from sap_mcp import sap_list_draft_quotes
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
            
            # Extraire les codes et noms produits demandés pour comparaison
            requested_codes = set()
            requested_names = set()

            for product in requested_products:
                if product.get("code"):
                    requested_codes.add(product.get("code", "").upper())
                if product.get("name"):
                    # Rechercher par mots-clés dans le nom (ex: "imprimante")
                    name_keywords = product.get("name", "").lower().split()
                    requested_names.update(name_keywords)

            logger.info(f"Recherche produits similaires pour {client_name}: codes={requested_codes}, mots-clés={requested_names}")

            # Rechercher dans les devis récents du client (ex: 7 jours)
            recent_quotes = await self._get_recent_sap_quotes(client_name, hours=168)
            similar_quotes = []

            for quote in recent_quotes:
                quote_has_similar = False
                matching_products = []
                # Analyser les lignes du devis pour détecter les produits similaires
                for line in quote.get("DocumentLines", []):
                    item_code = line.get("ItemCode", "").upper()
                    item_name = line.get("ItemDescription", "").lower()

                    # Vérification par code exact
                    if item_code and item_code in requested_codes:
                        quote_has_similar = True
                        matching_products.append(line.get("ItemDescription"))
                        # On continue pour collecter d'éventuels autres produits correspondants
                        continue

                    # Vérification par mots-clés dans le nom
                    for keyword in requested_names:
                        if len(keyword) > 3 and keyword in item_name:  # Éviter les mots trop courts
                            quote_has_similar = True
                            matching_products.append(line.get("ItemDescription"))
                            break

                if quote_has_similar:
                    similar_quotes.append({
                        "doc_entry": quote.get("DocEntry"),
                        "doc_num": quote.get("DocNum"),
                        "doc_date": quote.get("DocDate"),
                        "total": quote.get("DocTotal"),
                        "status": quote.get("DocumentStatus"),
                        "matching_products": matching_products
                    })

            return similar_quotes

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

                # ✅ NOUVEAU : Produit enrichi SANS calcul de prix
                enriched_product = {
                "code": product_code,
                "quantity": product.get("quantity", 1),
                "name": product_details.get("ItemName", "Unknown"),
                "stock": total_stock,
                "salesforce_id": None,
                "sap_raw_data": product_details,
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
                        "query": keyword,
                        "entity_type": "Items",
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
                    "query": product_name,
                    "entity_type": "Items",
                    "limit": 10
                }
            )
            
            if search_result.get("success") and search_result.get("results"):
                # CORRECTION: Améliorer la sélection du meilleur résultat
                results = search_result.get("results", [])
                
                # Trier par score de pertinence si disponible
                if results and "_relevance_score" in results[0]:
                    results.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)
                
                best_match = results[0]
                
                logger.info(f"✅ Produit trouvé par nom: {best_match.get('ItemName')} ({best_match.get('ItemCode')}) - Score: {best_match.get('_relevance_score', 'N/A')}")
                
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
                logger.error(f"❌ Erreur recherche MCP: {search_result.get('error') if search_result else 'Résultat None'}")
                
                # CORRECTION: Gérer le cas None et ajouter recherche intelligente
                if search_result is None:
                    logger.warning("⚠️ search_result est None, tentative recherche alternative")
                    # Recherche avec termes anglais
                    english_terms = self._get_english_search_terms(product_name)
                    for term in english_terms:
                        logger.info(f"🔍 Recherche alternative: {term}")
                        alt_result = await self.mcp_connector.call_mcp(
                            "sap_mcp",
                            "sap_search",
                            {"search_term": term, "search_fields": ["ItemName", "U_Description"], "limit": 5}
                        )
                        if alt_result and alt_result.get("success") and alt_result.get("results"):
                            best_match = alt_result["results"][0]
                            return {
                                "ItemCode": best_match.get("ItemCode"),
                                "ItemName": best_match.get("ItemName"),
                                "OnHand": best_match.get("OnHand", 0),
                                "AvgPrice": best_match.get("AvgPrice", 0),
                                "U_Description": best_match.get("U_Description", ""),
                                "found_by": f"alternative_{term}"
                            }
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
        
    async def continue_with_products(self, selected_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Initialisation sécurisée du contexte
        if not hasattr(self, 'context') or self.context is None:
            self.context = {}
        """Continue le workflow après sélection de produits par l'utilisateur"""
        try:
            logger.info(f"🔄 Continuation workflow avec {len(selected_products)} produit(s) sélectionné(s)")
            
            if not selected_products or not isinstance(selected_products, list):
                return self._build_error_response("Données invalides", "selected_products doit être une liste non vide")
            
            # Récupérer le contexte de la tâche
            if not self.context:
                logger.warning("⚠️ Contexte manquant, récupération depuis la tâche...")
                task = progress_tracker.get_task(self.task_id) if self.task_id else None
                if task and hasattr(task, 'context') and task.context:
                    self.context = task.context
                else:
                    self.context = {}
            
            # Import unique du Price Engine
            price_engine = None
            try:
                from services.price_engine import price_engine
                logger.info("✅ Price Engine disponible")
            except ImportError:
                logger.warning("⚠️ Price Engine non disponible, utilisation des prix de fallback")
            
            # Récupération unique du CardCode client pour tous les produits
            client_sap_code = None
            if self.context.get("client_info"):
                client_data = self.context["client_info"].get("data", {})
                client_sap_code = (
                    client_data.get("sap_code") or 
                    self.context.get("selected_client", {}).get("sap_code")
                )
                if client_sap_code:
                    logger.info(f"✅ CardCode client trouvé: {client_sap_code}")
            
            # Reformater les produits sélectionnés pour le workflow
            formatted_products = []
            for i, selected_product in enumerate(selected_products):
                # Extraire les données du produit sélectionné
                product_data = selected_product.get("product_data") or selected_product.get("data") or selected_product
                quantity = selected_product.get("quantity", selected_product.get("requested_quantity", 1))
                
                # Calcul du prix avec Price Engine si disponible
                unit_price = 0
                if price_engine and client_sap_code and product_data.get("ItemCode"):
                    try:
                        price_result = await price_engine.get_item_price(
                            card_code=client_sap_code,
                            item_code=product_data["ItemCode"], 
                            quantity=quantity
                        )
                        if price_result.get("success"):
                            unit_price = price_result["unit_price_after_discount"]
                            logger.info(f"✅ Prix Price Engine {product_data['ItemCode']}: {unit_price}€")
                        else:
                            logger.warning(f"⚠️ Price Engine échec {product_data['ItemCode']}: {price_result.get('error')}")
                    except Exception as pe_error:
                        logger.warning(f"⚠️ Erreur Price Engine {product_data['ItemCode']}: {pe_error}")
                
                # Fallback sur AvgPrice puis estimation
                if unit_price == 0:
                    unit_price = product_data.get("AvgPrice", 0) or product_data.get("unit_price", 0)
                    if unit_price == 0:
                        unit_price = self._estimate_product_price(product_data.get("ItemName", ""))
                        logger.info(f"💰 Prix estimé {product_data.get('ItemName')}: {unit_price}€")
                
                formatted_product = {
                    "code": product_data.get("ItemCode", ""),
                    "name": product_data.get("ItemName", ""),
                    "quantity": quantity,
                    "unit_price": product_data.get("AvgPrice", 0) or product_data.get("unit_price", 0) or self._estimate_product_price(product_data.get("ItemName", "")),
                    "total_price": 0,  # Sera calculé après
                    "currency": "EUR",
                    "stock": product_data.get("OnHand", 0),
                    "description": product_data.get("U_Description", ""),
                    "sap_data": product_data,
                    "search_method": "user_selected",
                    "found": True
                }
                # Recalculer total_price avec le prix final
                formatted_product["total_price"] = formatted_product["unit_price"] * quantity
                formatted_products.append(formatted_product)
                logger.info(f"✅ Produit {i+1}: {formatted_product['name']} x{quantity}")
            
            # Mettre à jour le contexte avec les produits sélectionnés
            self.context["products_info"] = formatted_products
            self.context["products_selected"] = True
            
            # Préparer les données pour _create_quote_document
            client_result = self.context.get("client_info", {})
            products_result = {"products": formatted_products}
            
            # Continuer directement vers la création du devis
            self._track_step_complete("lookup_products", f"✅ {len(formatted_products)} produit(s) sélectionné(s)")
            
            # Créer le devis
            self._track_step_start("create_quote", "🧾 Création du devis")
            quote_result = await self._create_quote_document(client_result, products_result)
            
            if not isinstance(quote_result, dict):
                logger.error("❌ _create_quote_document a retourné un résultat invalide")
                return self._build_error_response("Erreur création devis", "Résultat invalide")
            
            # Marquer la tâche comme terminée
            self._track_step_complete("create_quote", "✅ Devis créé")
            if self.current_task:
                progress_tracker.complete_task(self.task_id, quote_result)
            
            return quote_result
            
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            logger.exception(f"❌ Erreur données continuation workflow: {str(e)}")
            self._track_step_fail("continue_with_products", "Erreur données", str(e))
            return self._build_error_response("Erreur données workflow", str(e))
        except ImportError as e:
            logger.exception(f"❌ Erreur import continuation workflow: {str(e)}")
            self._track_step_fail("continue_with_products", "Erreur import", str(e))
            return self._build_error_response("Service indisponible", str(e))
        except Exception as e:
            logger.exception(f"❌ Erreur inattendue continuation workflow: {str(e)}")
            self._track_step_fail("continue_with_products", "Erreur inattendue", str(e))
            return self._build_error_response("Erreur système", str(e))
        
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
        # Vérifier d'abord les données de prix structurées
        if isinstance(sap_data, dict):
            # Prix depuis Price Engine si disponible
            if "price_details" in sap_data and sap_data["price_details"].get("price_engine"):
                pe = sap_data["price_details"]["price_engine"]
                price = float(pe.get("unit_price_after_discount", 0.0))
                if price > 0:
                    return price
            
            # Prix direct SAP
            if sap_data.get("Price") is not None and float(sap_data.get("Price", 0)) > 0:
                return float(sap_data.get("Price"))
            
            # Prix de liste SAP
            if sap_data.get("AvgPrice") is not None and float(sap_data.get("AvgPrice", 0)) > 0:
                return float(sap_data.get("AvgPrice"))
            
            # Prix dans ItemPrices
            if "ItemPrices" in sap_data and len(sap_data["ItemPrices"]) > 0:
                for price_entry in sap_data["ItemPrices"]:
                    price = float(price_entry.get("Price", 0.0))
                    if price > 0:
                        return price
            
            # Prix de dernier achat
            if sap_data.get("LastPurchasePrice") is not None and float(sap_data.get("LastPurchasePrice", 0)) > 0:
                return float(sap_data.get("LastPurchasePrice"))
        
        # Si aucun prix trouvé, utiliser estimation par nom de produit
        product_name = sap_data.get("ItemName", "") if isinstance(sap_data, dict) else ""
        return self._estimate_product_price(product_name)

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

                    # AJOUT: Aussi vérifier les chiffres en début de phrase
                    if quantity == 1:
                        number_matches = re.findall(r'\b(\d+)\b', prompt_lower)
                        if number_matches:
                            try:
                                first_number = int(number_matches[0])
                                if 1 <= first_number <= 999:  # Quantité raisonnable
                                    quantity = first_number
                            except ValueError:
                                pass

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
        quantities = []
        for word in words:
            if word.isdigit():
                try:
                    num = int(word)
                    if 1 <= num <= 999:  # Filtre quantités raisonnables
                        quantities.append(num)
                except ValueError:
                    pass

        # Prendre le premier nombre valide ou 1 par défaut
        default_quantity = quantities[0] if quantities else 1
        logger.info(f"📦 Quantité extraite en mode minimal: {default_quantity}")

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
        """Extrait critères de recherche intelligents pour produits SAP"""
        
        try:
            # Utiliser une approche directe pour l'analyse de produits
            # au lieu de extract_quote_info qui confond avec l'analyse de devis
            
            # Catégorisation simple basée sur des mots-clés
            product_lower = product_name.lower()
            
            # Détection de catégorie
            if any(term in product_lower for term in ["imprimante", "printer"]):
                category = "imprimante"
                characteristics = ["imprimante"]
            elif any(term in product_lower for term in ["ordinateur", "pc", "computer"]):
                category = "ordinateur"
                characteristics = ["ordinateur", "pc"]
            elif any(term in product_lower for term in ["écran", "monitor", "screen"]):
                category = "écran"
                characteristics = ["écran", "monitor"]
            else:
                category = "général"
                characteristics = [product_name]
            
            return {
                "action_type": "RECHERCHE_PRODUIT",
                "search_criteria": {
                    "category": category,
                    "characteristics": characteristics,
                    "specifications": {}
                },
                "query_details": f"Recherche de produits de type '{category}'"
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse critères produit: {e}")
            return {
                "action_type": "RECHERCHE_PRODUIT",
                "search_criteria": {
                    "category": "général",
                    "characteristics": [product_name],
                    "specifications": {}
                },
                "query_details": f"Recherche générale pour '{product_name}'"
            }
    def _extract_category_from_name(self, product_name: str) -> str:
        """Extrait la catégorie d'un nom de produit"""
        product_lower = product_name.lower()
        
        if any(term in product_lower for term in ["imprimante", "printer"]):
            return "imprimante"
        elif any(term in product_lower for term in ["ordinateur", "pc", "computer"]):
            return "ordinateur"
        elif any(term in product_lower for term in ["écran", "monitor", "screen"]):
            return "écran"
        else:
            return "général"

    async def _smart_product_search(self, product_name: str, product_code: str = "") -> Dict[str, Any]:
        """Recherche produits avec critères intelligents - VERSION OPTIMISÉE AVEC BASE LOCALE"""
        start_time = datetime.now()
        logger.info(f"🔍 Recherche optimisée démarrée: '{product_name}' (code: '{product_code}')")

        try:
            # Garde simple
            if not (product_name or product_code):
                return {"found": False, "products": [], "method": "no_input", "error": "Aucun critère fourni"}

            # Construire les critères
            criteria = {
                "product_name": product_name,
                "product_code": product_code,
                "category": self._extract_category_from_name(product_name) if product_name else "général",
                "keywords": self._extract_product_keywords(product_name) if product_name else []
            }

            # ===== ÉTAPE 1: RECHERCHE LOCALE PRIORITAIRE (< 500ms) =====

            # 1.1 Recherche exacte par code si fourni
            if product_code:
                try:
                    local_exact = await self._search_local_by_code(product_code)
                    if local_exact:
                        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                        logger.info(f"✅ Produit trouvé en local par code en {duration_ms:.0f}ms: {local_exact.get('ItemName')}")
                        return {"found": True, "products": [local_exact], "method": "exact_code_local", "duration_ms": duration_ms}
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche locale par code: {str(e)}")

            # 1.2 Recherche intelligente locale par nom
            if product_name:
                try:
                    local_smart_results = await self._search_local_intelligent(product_name, criteria)
                    if local_smart_results:
                        # dédup locale par ItemCode
                        seen = set()
                        dedup = []
                        for it in local_smart_results:
                            code = it.get("ItemCode")
                            if code and code not in seen:
                                seen.add(code)
                                dedup.append(it)
                        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                        logger.info(f"✅ {len(dedup)} produits trouvés en local en {duration_ms:.0f}ms")
                        return {"found": True, "products": dedup[:10], "method": "intelligent_local", "duration_ms": duration_ms}
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche locale intelligente: {str(e)}")

            # 1.3 Recherche fuzzy locale
            if product_name:
                try:
                    local_fuzzy_results = await self._search_local_fuzzy(product_name)
                    if local_fuzzy_results:
                        # dédup
                        seen = set()
                        dedup = []
                        for it in local_fuzzy_results:
                            code = it.get("ItemCode")
                            if code and code not in seen:
                                seen.add(code)
                                dedup.append(it)
                        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                        logger.info(f"✅ {len(dedup)} produits trouvés en fuzzy local en {duration_ms:.0f}ms")
                        return {"found": True, "products": dedup[:5], "method": "fuzzy_local", "duration_ms": duration_ms}
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche fuzzy locale: {str(e)}")

            # ===== ÉTAPE 2: FALLBACK SAP (LIMITÉ POUR ÉVITER BOUCLES) =====
            logger.warning("🔄 Recherche locale vide - Activation fallback SAP limité")

            # 2.1 Recherche exacte par code SAP
            if product_code:
                try:
                    exact_result = await self.mcp_connector.call_sap_mcp("sap_read", {
                        "endpoint": f"/Items('{product_code}')",
                        "method": "GET"
                    })
                    if "error" not in exact_result and exact_result.get("ItemCode"):
                        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                        logger.info(f"✅ Produit trouvé via SAP par code: {exact_result.get('ItemName')}")
                        return {"found": True, "products": [exact_result], "method": "exact_code_sap", "duration_ms": duration_ms}
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche SAP par code: {str(e)}")

            # 2.2 Recherche SAP par nom (LIMITÉE À 1 TENTATIVE)
            if product_name:
                try:
                    search_timeout = asyncio.create_task(asyncio.sleep(15))  # 15s max
                    search_task = asyncio.create_task(
                        self.mcp_connector.call_mcp(
                            "sap_mcp",
                            "sap_search",
                            {"query": product_name, "entity_type": "Items", "limit": 3}
                        )
                    )
                    done, pending = await asyncio.wait([search_task, search_timeout], return_when=asyncio.FIRST_COMPLETED)
                    for task in pending:
                        task.cancel()

                    if search_task in done:
                        search_result = search_task.result()
                        if search_result and search_result.get("success") and search_result.get("results"):
                            results = search_result["results"][:3]
                            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                            logger.info(f"✅ Produit trouvé via SAP par nom ({len(results)} résultats)")
                            return {"found": True, "products": results, "method": "name_search_sap", "duration_ms": duration_ms}
                    else:
                        logger.warning(f"⏰ Timeout recherche SAP pour '{product_name}' (15s dépassées)")
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche SAP par nom: {str(e)}")

            # 2.3 Recherche SAP alternative avec termes anglais (DERNIÈRE CHANCE)
            if product_name:
                try:
                    english_terms = self._get_english_search_terms(product_name)
                    for term in english_terms[:2]:
                        logger.info(f"🔍 Recherche SAP alternative: {term}")
                        alt_task = asyncio.create_task(
                            self.mcp_connector.call_mcp(
                                "sap_mcp",
                                "sap_search",
                                {"search_term": term, "search_fields": ["ItemName", "U_Description"], "limit": 2}
                            )
                        )
                        try:
                            alt_result = await asyncio.wait_for(alt_task, timeout=10.0)
                            if alt_result and alt_result.get("success") and alt_result.get("results"):
                                results = alt_result["results"][:2]
                                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                                logger.info(f"✅ Produit trouvé via terme alternatif '{term}'")
                                return {"found": True, "products": results, "method": f"alternative_{term}", "duration_ms": duration_ms}
                        except asyncio.TimeoutError:
                            logger.warning(f"⏰ Timeout recherche alternative '{term}' (10s)")
                            alt_task.cancel()
                            continue
                        except Exception as e:
                            logger.warning(f"⚠️ Erreur recherche alternative '{term}': {str(e)}")
                            continue
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche termes alternatifs: {str(e)}")

            # ===== AUCUN RÉSULTAT TROUVÉ =====
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.warning(f"❌ Aucun produit trouvé pour '{product_name}' après {duration_ms:.0f}ms")
            return {"found": False, "products": [], "method": "no_match", "searched_criteria": criteria, "duration_ms": duration_ms}

        except Exception as e:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"❌ Erreur critique _smart_product_search après {duration_ms:.0f}ms: {str(e)}")
            return {"found": False, "products": [], "method": "error", "error": str(e), "duration_ms": duration_ms}
    
    def _is_generic_search(self, product_name: str) -> bool:
        """Détecte si le terme de recherche est trop générique pour auto-sélection"""
        if not product_name:
            return False
            
        generic_terms = [
            "imprimante", "ordinateur", "écran", "clavier", "souris", 
            "scanner", "serveur", "switch", "routeur", "câble",
            "cartouche", "toner", "papier", "moniteur", "pc"
        ]
        
        # Vérifier si le nom contient seulement des termes génériques et des chiffres/unités
        name_lower = product_name.lower()
        words = name_lower.split()
        
        # Si tous les mots sont soit génériques, soit des nombres/unités
        for word in words:
            if not (any(term in word for term in generic_terms) or 
                   word.isdigit() or 
                   word in ["ppm", "go", "gb", "tb", "mo", "mb", "pouces", "inch"]):
                return False
        
        return True
    async def _search_local_by_code(self, item_code: str) -> Optional[Dict[str, Any]]:
        """Recherche exacte par ItemCode en base locale PostgreSQL"""
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                logger.warning("DATABASE_URL manquant pour recherche locale par code")
                return None
            engine = create_engine(db_url, pool_pre_ping=True)
            SessionLocal = sessionmaker(bind=engine)
            with SessionLocal() as session:
                result = session.execute(
                    text("""
                    SELECT item_code, item_name, u_description, avg_price, on_hand,
                        items_group_code, manufacturer, sales_unit
                    FROM produits_sap 
                    WHERE item_code = :code AND valid = true
                    """),
                    {"code": item_code}
                ).fetchone()
                if result:
                    return {
                        "ItemCode": result.item_code,
                        "ItemName": result.item_name,
                        "U_Description": result.u_description or "",
                        "AvgPrice": float(result.avg_price or 0),
                        "OnHand": int(result.on_hand or 0),
                        "QuantityOnStock": int(result.on_hand or 0),
                        "ItemsGroupCode": result.items_group_code or "",
                        "Manufacturer": result.manufacturer or "",
                        "SalesUnit": result.sales_unit or "UN",
                        "source": "local_db"
                    }
        except Exception as e:
            logger.error(f"❌ Erreur recherche locale par code: {str(e)}")
        return None

    async def _search_local_intelligent(self, product_name: str, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Recherche intelligente locale avec LLM et SQL optimisé"""
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker

            keywords = criteria.get("keywords", []) or []
            category = criteria.get("category", "autre") or "autre"

            # Conditions SQL
            search_conditions = ["(LOWER(item_name) LIKE :search_term OR LOWER(u_description) LIKE :search_term)"]
            params = {"search_term": f"%{product_name.lower()}%"}

            for i, keyword in enumerate(keywords[:3]):
                param_name = f"keyword_{i}"
                search_conditions.append(f"(LOWER(item_name) LIKE :{param_name} OR LOWER(u_description) LIKE :{param_name})")
                params[param_name] = f"%{keyword.lower()}%"

            if category != "autre":
                search_conditions.append("(LOWER(item_name) LIKE :category OR LOWER(u_description) LIKE :category)")
                params["category"] = f"%{category.lower()}%"

            query = f"""
            SELECT item_code, item_name, u_description, avg_price, on_hand,
                items_group_code, manufacturer, sales_unit,
                (
                    CASE 
                    WHEN LOWER(item_name) LIKE :search_term THEN 100
                    WHEN LOWER(u_description) LIKE :search_term THEN 80
                    WHEN :category IS NOT NULL AND LOWER(item_name) LIKE :category THEN 60
                    ELSE 40
                    END
                ) as relevance_score
            FROM produits_sap 
            WHERE valid = true 
            AND on_hand > 0
            AND ({' OR '.join(search_conditions)})
            ORDER BY relevance_score DESC, on_hand DESC
            LIMIT 10
            """

            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                logger.warning("DATABASE_URL manquant pour recherche locale intelligente")
                return []
            engine = create_engine(db_url, pool_pre_ping=True)
            SessionLocal = sessionmaker(bind=engine)
            with SessionLocal() as session:
                results = session.execute(text(query), params).fetchall()
                formatted_results: List[Dict[str, Any]] = []
                for row in results or []:
                    formatted_results.append({
                        "ItemCode": row.item_code,
                        "ItemName": row.item_name,
                        "U_Description": row.u_description or "",
                        "AvgPrice": float(row.avg_price or 0),
                        "OnHand": int(row.on_hand or 0),
                        "QuantityOnStock": int(row.on_hand or 0),
                        "ItemsGroupCode": row.items_group_code or "",
                        "Manufacturer": row.manufacturer or "",
                        "SalesUnit": row.sales_unit or "UN",
                        "source": "local_db",
                        "relevance_score": float(row.relevance_score or 0.0)
                    })
                return formatted_results
        except Exception as e:
            logger.error(f"❌ Erreur recherche locale intelligente: {str(e)}")
        return []

    async def _search_local_fuzzy(self, product_name: str) -> List[Dict[str, Any]]:
        """Recherche fuzzy locale - Version compatible sans pg_trgm"""
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                logger.warning("DATABASE_URL manquant pour recherche fuzzy locale")
                return []
            engine = create_engine(db_url, pool_pre_ping=True)
            SessionLocal = sessionmaker(bind=engine)
            with SessionLocal() as session:
                # Recherche par sous-chaînes multiples sans pg_trgm
                search_terms = product_name.lower().split()
                where_clauses = []
                params = {"name": product_name}
                
                for i, term in enumerate(search_terms[:3]):  # Limite à 3 termes
                    if len(term) > 2:  # Ignore les termes trop courts
                        params[f"term_{i}"] = f"%{term}%"
                        where_clauses.append(f"(LOWER(item_name) LIKE :term_{i} OR LOWER(u_description) LIKE :term_{i})")
                
                if not where_clauses:
                    where_clauses = ["LOWER(item_name) LIKE '%' || LOWER(:name) || '%'"]
                
                results = session.execute(
                    text(f"""
                    SELECT item_code, item_name, u_description, avg_price, on_hand,
                        items_group_code, manufacturer, sales_unit
                    FROM produits_sap 
                    WHERE valid = true 
                    AND on_hand > 0
                    AND ({' OR '.join(where_clauses)})
                    ORDER BY on_hand DESC, LENGTH(item_name) ASC
                    LIMIT 10
                    """),
                    params
                ).fetchall()
                formatted_results: List[Dict[str, Any]] = []
                for row in results or []:
                    formatted_results.append({
                        "ItemCode": row.item_code,
                        "ItemName": row.item_name,
                        "U_Description": row.u_description or "",
                        "AvgPrice": float(row.avg_price or 0),
                        "OnHand": int(row.on_hand or 0),
                        "QuantityOnStock": int(row.on_hand or 0),
                        "ItemsGroupCode": row.items_group_code or "",
                        "Manufacturer": row.manufacturer or "",
                        "SalesUnit": row.sales_unit or "UN",
                        "source": "local_db",
                        "similarity_score": float(row.sim_score or 0.0)
                    })
                return formatted_results
        except Exception as e:
            logger.error(f"❌ Erreur recherche fuzzy locale: {str(e)}")
        return []
    
    async def _search_local_fallback(self, product_name: str) -> List[Dict[str, Any]]:
        """Recherche locale sans pg_trgm - fallback LIKE"""
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            db_url = os.getenv("DATABASE_URL")
            if not db_url:
                return []
            
            engine = create_engine(db_url, pool_pre_ping=True)
            SessionLocal = sessionmaker(bind=engine)
            
            with SessionLocal() as session:
                results = session.execute(
                    text("""
                    SELECT item_code, item_name, u_description, avg_price, on_hand,
                        items_group_code, manufacturer, sales_unit,
                        CASE 
                            WHEN LOWER(item_name) LIKE LOWER(:name_exact) THEN 0.9
                            WHEN LOWER(item_name) LIKE LOWER(:name_start) THEN 0.8  
                            WHEN LOWER(item_name) LIKE LOWER(:name_contain) THEN 0.6
                            WHEN LOWER(u_description) LIKE LOWER(:name_contain) THEN 0.4
                            ELSE 0.2
                        END as sim_score
                    FROM produits_sap 
                    WHERE valid = true 
                    AND on_hand > 0
                    AND (
                        LOWER(item_name) LIKE LOWER(:name_contain) OR
                        LOWER(u_description) LIKE LOWER(:name_contain)
                    )
                    ORDER BY sim_score DESC, on_hand DESC
                    LIMIT 5
                    """),
                    {
                        "name_exact": product_name,
                        "name_start": f"{product_name}%",
                        "name_contain": f"%{product_name}%"
                    }
                ).fetchall()
                
                formatted_results = []
                for row in results or []:
                    formatted_results.append({
                        "ItemCode": row.item_code,
                        "ItemName": row.item_name,
                        "U_Description": row.u_description or "",
                        "AvgPrice": float(row.avg_price or 0),
                        "OnHand": int(row.on_hand or 0),
                        "QuantityOnStock": int(row.on_hand or 0),
                        "ItemsGroupCode": row.items_group_code or "",
                        "Manufacturer": row.manufacturer or "",
                        "SalesUnit": row.sales_unit or "UN",
                        "source": "local_db",
                        "similarity_score": float(row.sim_score or 0.0)
                    })
                return formatted_results
        except Exception as e:
            logger.error(f"❌ Erreur recherche fallback locale: {str(e)}")
        return []
    def _extract_product_keywords(self, product_name: str) -> List[str]:
        """Extrait les mots-clés intelligents d'un nom de produit"""
        import unicodedata

        def _normalize(s: str) -> str:
            s_no_accents = ''.join(ch for ch in unicodedata.normalize('NFD', s) if not unicodedata.combining(ch))
            return s_no_accents.lower()

        product_lower = product_name.lower()
        product_norm = _normalize(product_name)

        search_terms: List[str] = []
        seen = set()

        def _add(term: str) -> None:
            t = term.strip()
            if not t:
                return
            key = _normalize(t)
            if key not in seen:
                seen.add(key)
                search_terms.append(t)

        translations = {
            "imprimante": ["laser printer", "inkjet printer"],
            "ordinateur": ["workstation", "laptop"],
            "écran": ["monitor", "display"],
            "clavier": ["keyboard", "mechanical keyboard"],
            "souris": ["wireless mouse", "optical mouse"],
            "scanner": ["document scanner", "scan"],
            "laser": ["laser printer", "LaserJet"],
            "couleur": ["color", "colour"],
            "noir": ["monochrome", "mono"],
            "ppm": ["pages per minute", "page/min"],
        }

        for french_term, english_terms in translations.items():
            fr_norm = _normalize(french_term)
            if fr_norm in product_norm:
                for t in english_terms[:2]:
                    _add(t)

        _add(product_name)

        numbers = re.findall(r"\d+", product_lower)
        for num in numbers:
            try:
                val = int(num)
            except ValueError:
                continue
            if 5 < val < 1000:
                _add(f"{num}ppm")
                _add(f"{num} ppm")
                _add(f"{num} pages")

        return search_terms[:6]

    def _get_english_search_terms(self, product_name: str) -> List[str]:
        """Génère des termes de recherche anglais pour SAP"""
        product_lower = product_name.lower()
        translations = {
            "imprimante": ["printer", "Printer", "PRINTER"],
            "ordinateur": ["computer", "Computer", "PC"],
            "écran": ["monitor", "Monitor", "screen"],
            "clavier": ["keyboard", "Keyboard"],
            "souris": ["mouse", "Mouse"],
            "scanner": ["scanner", "Scanner"]
        }
        search_terms: List[str] = []
        for french_term, english_terms in translations.items():
            if french_term in product_lower:
                search_terms.extend(english_terms)
                break
        search_terms.append(product_name)
        return search_terms[:3]

    def _extract_category_from_name(self, product_name: str) -> str:
        """Extrait la catégorie d'un nom de produit"""
        product_lower = product_name.lower()
        if any(term in product_lower for term in ["imprimante", "printer"]):
            return "imprimante"
        elif any(term in product_lower for term in ["ordinateur", "pc", "computer"]):
            return "ordinateur"
        elif any(term in product_lower for term in ["écran", "monitor", "screen"]):
            return "écran"
        else:
            return "général"

            
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
    def _get_intelligent_search_terms(self, product_name: str) -> List[str]:
        """
        Génère des termes de recherche intelligents pour SAP
        """
        product_lower = product_name.lower()
        search_terms = []
        
        # Mapping français -> anglais pour SAP
        translations = {
            "imprimante": ["printer", "imprimante", "Printer", "PRINTER"],
            "ordinateur": ["computer", "PC", "desktop", "ordinateur"],
            "écran": ["monitor", "screen", "display", "écran"],
            "clavier": ["keyboard", "clavier"],
            "souris": ["mouse", "souris"],
            "scanner": ["scanner", "scan"],
            "laser": ["laser", "Laser"],
            "couleur": ["color", "colour", "couleur"]
        }
        
        # Chercher des correspondances
        for french_term, english_terms in translations.items():
            if french_term in product_lower:
                search_terms.extend(english_terms)
        
        # Ajouter le terme original
        search_terms.append(product_name)
        
        # Retourner les termes uniques, anglais en premier
        return list(dict.fromkeys(search_terms))[:4]
    

    def _create_generic_product(self, product_name: str) -> Dict[str, Any]:
        """
        🔧 CRÉATION PRODUIT GÉNÉRIQUE avec prix estimé
        """
        import time
        
        # Prix estimés selon le type
        estimated_price = 100.0  # Par défaut
        
        if "imprimante" in product_name.lower():
            if "20 ppm" in product_name.lower() or "ppm" in product_name.lower():
                    # Extraction intelligente de la vitesse
                    import re
                    ppm_match = re.search(r'(\d+)\s*ppm', product_name.lower())
                    if ppm_match:
                        ppm_value = int(ppm_match.group(1))
                        estimated_price = 150.0 + (ppm_value * 5)  # Prix basé sur vitesse
                    else:
                        estimated_price = 300.0  # Imprimante standard
            else:
                estimated_price = 150.0  # Imprimante générique
        elif "ordinateur" in product_name.lower():
            estimated_price = 800.0
        elif "écran" in product_name.lower():
            estimated_price = 300.0
        
        generic_code = f"GEN{int(time.time()) % 10000:04d}"
        # Normaliser le format pour compatibilité avec la validation
        normalized_price = estimated_price
        
        return {
            "ItemCode": generic_code,
            "ItemName": product_name.title(),
            "OnHand": 999,  # Stock fictif
            "AvgPrice": estimated_price,
            "Price": estimated_price,  # Format standardisé pour validation
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

            try:
                await websocket_manager.send_user_interaction_required(self.task_id, {
                    "type": "product_selection",
                    "message": "Certains produits nécessitent votre attention",
                    "data": validation_data
                })
            except Exception as ws_error:
                logger.warning(f"⚠️ Erreur envoi WebSocket (non bloquant): {ws_error}")
            
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
    
    async def _handle_client_selection(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """🔧 Gère la sélection de client par l'utilisateur avec continuation workflow"""
        try:
            action = user_input.get("action")

            if action == "select_existing":
                # Initialisation des variables nécessaires
                selected_client_data = user_input.get("selected_data")
                client_name = context.get("original_client_name", "")

                # Récupérer le code SAP depuis selected_data
                if selected_client_data and isinstance(selected_client_data, dict) and selected_client_data.get("sap_code"):
                    self.context["client_sap_code"] = selected_client_data["sap_code"]
                    logger.info(f"✅ Code SAP récupéré depuis client sélectionné: {selected_client_data['sap_code']}")

                # Récupérer aussi depuis selected_client si selected_data manque
                if not selected_client_data:
                    alt = user_input.get("selected_client")
                    if alt and isinstance(alt, dict):
                        selected_client_data = alt

                # Préserver/compléter les données Salesforce si présentes
                if selected_client_data and isinstance(selected_client_data, dict) and selected_client_data.get("sf_id"):
                    sf_id = selected_client_data.get("sf_id")
                    if sf_id and not selected_client_data.get("Id"):
                        try:
                            sf_query = (
                                "SELECT Id, Name, AccountNumber, Phone, BillingStreet, "
                                "BillingCity, BillingPostalCode, BillingCountry "
                                f"FROM Account WHERE Id = '{escape_soql(sf_id)}'"
                            )
                            sf_result = await self.mcp_connector.call_mcp(
                                "salesforce_mcp", "salesforce_query", {"query": sf_query}
                            )
                            if sf_result.get("totalSize", 0) > 0:
                                sf_data = sf_result["records"][0]
                                if isinstance(sf_data, dict):
                                    selected_client_data.update(sf_data)
                                    logger.info(f"✅ Données Salesforce récupérées pour {sf_data.get('Name')}")
                        except Exception as e:
                            logger.warning(f"⚠️ Erreur récupération données SF: {str(e)}")

                if selected_client_data and isinstance(selected_client_data, dict):
                    # Mettre à jour avec le nom réel depuis les données
                    client_name = (
                        selected_client_data.get("Name")
                        or selected_client_data.get("name")
                        or selected_client_data.get("CardName")
                        or client_name
                    )
                    try:
                        await self.cache_manager.cache_client(client_name, selected_client_data)
                    except Exception as e:
                        logger.warning(f"⚠️ Cache client échoué: {e}")
                else:
                    logger.warning("⚠️ selected_data manquant - utilisation nom par défaut")

                # Mise à jour du contexte (unique source de vérité)
                self.context["client_info"] = {"data": selected_client_data, "found": bool(selected_client_data)}
                self.context["client_validated"] = True  # (dédupliqué)

                # Sauvegarder le contexte dans la tâche
                self._save_context_to_task()

                # Persistance complémentaire
                self.context["validated_client"] = selected_client_data
                self.context["selected_client"] = selected_client_data

                # Sauvegarder dans la tâche si disponible
                if getattr(self, "current_task", None):
                    if not hasattr(self.current_task, "context") or not isinstance(self.current_task.context, dict):
                        self.current_task.context = {}
                    self.current_task.context["client_info"] = {"data": selected_client_data, "found": bool(selected_client_data)}
                    logger.info("✅ Client info sauvegardé dans la tâche")

                # Affichage : protéger si selected_client_data est None
                if isinstance(selected_client_data, dict):
                    client_display_name = (
                        selected_client_data.get("Name")
                        or selected_client_data.get("CardName")
                        or client_name
                        or "Client sans nom"
                    )
                else:
                    client_display_name = client_name or "Client sans nom"
                # Récupérer original_extracted_info depuis le contexte ou interaction_data
                original_extracted_info = context.get("workflow_context", {}).get("extracted_info", {})
                if not original_extracted_info:
                    original_extracted_info = context.get("original_context", {}).get("extracted_info", {})
                if not original_extracted_info and hasattr(self, 'context'):
                    original_extracted_info = self.context.get("extracted_info", {})
                    
                # Fallback si toujours pas trouvé
                if not original_extracted_info:
                    original_extracted_info = {}
                    logger.warning("⚠️ original_extracted_info vide - utilisation fallback")
                self.context["selected_client_display"] = client_display_name
                logger.info(f"✅ Client sélectionné: {client_display_name}")

                # Poursuite du workflow
                workflow_ctx = context.get("workflow_context", {}) or {}
                extracted_info = (workflow_ctx.get("extracted_info") or {}) if isinstance(workflow_ctx, dict) else {}

                # Récupérer les produits depuis le contexte ou depuis la tâche
                original_products = (extracted_info.get("products") or []) if isinstance(extracted_info, dict) else []
                # CORRECTION: Récupérer les produits depuis extracted_info du contexte
                if not original_products and hasattr(self, 'context') and self.context.get('extracted_info'):
                    original_products = self.context.get('extracted_info', {}).get('products', [])
                    logger.info(f"🔄 Produits récupérés depuis contexte: {len(original_products)} produit(s)")
                # Si pas de produits dans le contexte, essayer de les récupérer depuis la tâche
                if not original_products and getattr(self, "current_task", None):
                    validation_data = getattr(self.current_task, "validation_data", None)
                    if isinstance(validation_data, dict):
                        client_validation = validation_data.get("client_selection", {}) or {}
                        original_context = client_validation.get("original_context", {}) or {}
                        original_products = (original_context.get("extracted_info", {}) or {}).get("products", []) or []
                        logger.info(f"🔍 Produits récupérés depuis validation_data de la tâche: {len(original_products)} produit(s)")

                # CORRECTION: Vérifier doublons APRÈS sélection client mais AVANT produits
                logger.info("🔍 === DÉBUT VÉRIFICATION DOUBLONS APRÈS SÉLECTION CLIENT ===")
                # 🔧 Honorer skip_duplicate_check (forçage 'créer malgré les doublons')
                if getattr(self, "skip_duplicate_check", False) or self.context.get("skip_duplicate_check"):
                    logger.info("⏭️ Vérification doublons ignorée (skip_duplicate_check actif)")
                    duplicate_check = {}
                else:
                    duplicate_check = await self._check_duplicate_quotes(
                        {"data": selected_client_data, "found": True, "name": client_display_name},
                        original_products
                    )
                self.context["duplicate_check"] = duplicate_check

                # Si doublons trouvés ET nécessite une décision utilisateur
                if duplicate_check.get("requires_user_decision"):
                    logger.warning(f"⚠️ DOUBLONS DÉTECTÉS - Interaction utilisateur requise")
                    
                    duplicate_interaction_data = {
                        "type": "duplicate_resolution",
                        "interaction_type": "duplicate_resolution",
                        "client_name": client_display_name,
                        "alert_message": duplicate_check.get("alert_message"),
                        "recent_quotes": duplicate_check.get("recent_quotes", []),
                        "draft_quotes": duplicate_check.get("draft_quotes", []),
                        "similar_quotes": duplicate_check.get("similar_quotes", []),
                        "extracted_info": original_extracted_info,
                        "options": [
                            {"value": "proceed", "label": "Créer un nouveau devis malgré les doublons"},
                            {"value": "consolidate", "label": "Consolider avec un devis existant"},
                            {"value": "review", "label": "Examiner les devis existants d'abord"},
                            {"value": "cancel", "label": "Annuler la demande"}
                        ],
                        "input_type": "choice"
                    }
                    
                    # Marquer la tâche en attente d'interaction
                    if self.current_task:
                        from services.progress_tracker import TaskStatus
                        self.current_task.status = TaskStatus.PENDING
                        self.current_task.require_user_validation(
                            "duplicate_resolution",
                            "duplicate_resolution", 
                            duplicate_interaction_data
                        )
                    
                    # Envoyer via WebSocket
                    try:
                        from services.websocket_manager import websocket_manager
                        await websocket_manager.send_user_interaction_required(
                            self.task_id,
                            duplicate_interaction_data
                        )
                        logger.info("✅ Alerte de doublon envoyée via WebSocket")
                        
                        return {
                            "success": True,
                            "status": "user_interaction_required", 
                            "type": "duplicate_resolution",
                            "message": duplicate_check.get("alert_message"),
                            "task_id": self.task_id,
                            "interaction_data": duplicate_interaction_data
                        }
                    except Exception as ws_error:
                        logger.warning(f"⚠️ Erreur envoi WebSocket alerte doublon: {ws_error}")

                # Si pas de doublons ou utilisateur veut continuer
                if original_products:
                    
                    self._track_step_start("lookup_products", f"📦 Recherche de {len(original_products)} produit(s)")
                    await self._process_products_retrieval(original_products)

                    # Récupérer extracted_info depuis le contexte de la tâche
                    extracted_info = self.context.get("extracted_info", {})
                    original_extracted_info = extracted_info  # Définir la variable avant utilisation
                    
                    # Si extracted_info disponible, continuer le workflow
                    if isinstance(extracted_info, dict) and extracted_info:
                        return await self._continue_workflow_after_client_selection(
                            selected_client_data, {"extracted_info": extracted_info}
                        )
                    elif isinstance(original_extracted_info, dict) and original_extracted_info:
                        return await self._continue_workflow_after_client_selection(
                            selected_client_data, {"extracted_info": original_extracted_info}
                        )
                    elif isinstance(extracted_info, dict) and extracted_info:
                        return await self._process_quote_workflow(extracted_info)

                    else:
                        # Fallback minimal si aucun extracted_info complet
                        return await self._continue_workflow_after_client_selection(
                            selected_client_data, {"extracted_info": {"products": original_products}}
                        )

                return self._build_error_response("Workflow incomplet", "Produits manquants pour continuer")

            elif action == "create_new":
                client_name = user_input.get("client_name", context.get("original_client_name", ""))
                # CORRECTION: Appeler directement _handle_new_client_creation avec le contexte workflow
                workflow_context = context.get("workflow_context", {})
                return await self._handle_new_client_creation(client_name, workflow_context)

            elif action == "cancel":
                return {"status": "cancelled", "message": "Demande de devis annulée par l'utilisateur"}

            else:
                return self._build_error_response("Action non reconnue", f"Action: {action}")

        except Exception as e:
            logger.exception(f"Erreur _handle_client_selection: {e}")
            return self._build_error_response("Erreur sélection client", str(e))

    async def _handle_new_client_creation(self, client_name: str, workflow_context: Dict) -> Dict:
        """
        🔧 CRÉATION CLIENT PUIS CONTINUATION WORKFLOW
        """
        # CORRECTION: Validation et création du client avec workflow continuation
        try:
            self._track_step_start("client_creation", f"Création du client: {client_name}")
            
            validation_result = await self.client_validator.validate_complete({"company_name": client_name}, "FR")
            
            if validation_result.get("can_create"):
                # Créer dans Salesforce puis SAP
                self._track_step_progress("client_creation", 30, "Création Salesforce...")
                sf_client = await self._create_salesforce_client(validation_result)
                
                self._track_step_progress("client_creation", 60, "Création SAP...")
                sap_client = await self._create_sap_client_from_validation(validation_result, sf_client)
                
                # Mettre à jour le contexte
                self.context.update({
                    "client_info": {"data": sf_client, "found": True},
                    "client_validated": True,
                    "client_sap_code": sf_client.get("sap_code", "")
                })
                
                self._track_step_complete("client_creation", f"Client créé: {sf_client.get('Name', client_name)}")
                
                # CORRECTION: Continuer le workflow avec les produits
                original_products = workflow_context.get("extracted_info", {}).get("products", [])
                if original_products:
                    self._track_step_start("product_validation", "Validation des produits...")
                    return await self._get_products_info(original_products)
                else:
                    # Pas de produits dans le contexte - demander à l'utilisateur
                    return self._build_product_request_response(sf_client.get("Name", client_name))
            
            else:
                self._track_step_fail("client_creation", "Impossible de créer le client", validation_result.get("error", ""))
                return self._build_error_response("Impossible de créer le client", validation_result.get("error", ""))
        
        except Exception as e:
            logger.exception(f"Erreur création client {client_name}: {e}")
            self._track_step_fail("client_creation", "Erreur création client", str(e))
            return self._build_error_response("Erreur création client", str(e))
        
    async def _initiate_client_creation(self, client_name: str) -> Dict[str, Any]:
        """
        CORRECTION: Méthode manquante pour initier la création client
        """
        try:
            logger.info(f"Initiation création client: {client_name}")
            
            # Récupérer le contexte workflow complet depuis la tâche
            if self.task_id:
                task = progress_tracker.get_task(self.task_id)
                if task and hasattr(task, 'context'):
                    workflow_context = task.context
                else:
                    workflow_context = {"extracted_info": {"products": []}}
            else:
                workflow_context = {"extracted_info": {"products": []}}
            
            return await self._handle_new_client_creation(client_name, workflow_context)
            
        except Exception as e:
            logger.exception(f"Erreur initiation création client {client_name}: {e}")
            return self._build_error_response("Erreur initiation création client", str(e))
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
            # Passer à la recherche et validation des produits
            self._track_step_start("lookup_products", f"📦 Recherche de {len(original_products)} produit(s)")
            products_result = await self._process_products_retrieval(original_products)
            
            # Vérifier si sélection produits requise
            if products_result.get("status") == "product_selection_required":
                logger.info("⚠️ Sélection produits requise après sélection client")
                # Envoyer l'interaction WebSocket
                await self._send_product_selection_interaction(products_result.get("products", []))
                return products_result
                
            # Si produits validés, continuer vers génération devis
            return await self._continue_quote_generation(products_result)
        else:
            # Si pas de produits, demander à l'utilisateur
            return self._build_product_selection_interface(client_data.get("Name", ""))
    def _generate_client_efficiency_tip(self, searched_name: str, found_client: Dict) -> str:
        """Génère des conseils d'efficacité pour l'utilisateur"""
        tips = []
        # Conseil spécifique si plusieurs clients avec noms similaires
        if "group" in searched_name.lower() or "groupe" in searched_name.lower():
            tips.append(f"💡 Astuce : Utilisez 'Group' ou 'Groupe' pour distinguer les filiales (ex: '{searched_name.replace('Group', '').strip()}' vs '{searched_name}')")
        elif len(searched_name.split()) == 1:
            # Client simple, vérifier s'il existe une version Group
            tips.append(f"💡 Astuce : Si vous cherchez une filiale, essayez '{searched_name} Group' ou '{searched_name} Groupe'")
        # Conseil sur la ville
        client_city = (found_client.get("BillingCity") or 
                      found_client.get("City") or 
                      found_client.get("Address", "").split(",")[-1].strip())
        if client_city and len(client_city) > 2:
            tips.append(f"💡 Pour être plus efficace, précisez la ville : '{searched_name} {client_city}'")
        
        # Conseil sur le code client
        client_code = found_client.get("AccountNumber") or found_client.get("CardCode")
        if client_code:
            tips.append(f"💡 Vous pouvez aussi utiliser le code client : '{client_code}'")
        
        # Conseil général
        if not tips:
            tips.append("💡 Pour gagner du temps, précisez la ville ou le secteur d'activité du client")
        
        return " • ".join(tips[:2])  # Maximum 2 conseils

    async def _get_products_info_with_auto_selection(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Récupération des produits avec auto-sélection intelligente"""
        try:
            if not products:
                return {
                    "status": "success",
                    "products": [],
                    "message": "Aucun produit à traiter"
                }

            self._track_step_progress("get_products_info", 10, f"🔍 Recherche de {len(products)} produit(s)...")

            validated_products = []
            products_found = []
            products_needing_selection = []
            products_needing_interaction = []
            auto_selected_count = 0

            for i, product in enumerate(products):
                product_name = product.get("name", "")
                product_code = product.get("code", "")
                quantity = product.get("quantity", 1)
                progress = int(20 + (i / len(products)) * 60)
                # Progression
                self._track_step_progress("get_products_info", progress,
                                        f"📦 Recherche '{product_name}' ({i+1}/{len(products)})")

                # Recherche du produit avec méthode existante
                single_product_list = [{
                    "name": product_name,
                    "code": product_code,
                    "quantity": quantity
                }]
                
                # Utiliser _process_products_retrieval qui existe
                # Initialiser le résultat du produit
                product_result = {"found": False, "suggestions": [], "error": None}
                search_result = await self._process_products_retrieval(single_product_list)
                found_products = search_result.get("products", [])
                
                if found_products and len(found_products) == 1:
                    # Un seul produit trouvé - Auto-sélection
                    validated_products.append(found_products[0])
                    auto_selected_count += 1
                    # Restaure la traçabilité sans alourdir
                    code = (found_products[0].get("code") if isinstance(found_products[0], dict) else None) or product_code
                    logger.info(f"✅ Produit auto-sélectionné: {code}")

                elif found_products and len(found_products) > 1:
                    # Plusieurs produits trouvés - Demande sélection
                    options = found_products[:5]
                    products_needing_selection.append({
                        "original_name": product_name,
                        "original_code": product_code,               # réintroduit (utile pour la suite)
                        "quantity": quantity,
                        "options": options,
                        "search_method": "intelligent_local",        # réintroduit (diagnostic/UX)
                        "selection_reason": (
                            f"Terme '{product_name}' trop générique - {len(found_products)} produits correspondent"
                        ),
                        "multiple_matches": True                     # réintroduit (signal explicite)
                    })
                    logger.info(f"⚠️ {len(found_products)} options pour '{product_name}' - Sélection requise")

                else:
                    # Produit non trouvé
                    product_result = {
                        "found": False,
                        "suggestions": [],
                        "error": "Produit non trouvé"
                    }
                    products_needing_interaction.append({
                        "original": product,
                        "suggestions": [],
                        "efficiency_tip": self._generate_product_efficiency_tip(product_code, product_name)
                    })
                if product_result.get("found"):
                    # Produit trouvé directement
                    validated_products.append({
                        "found": True,
                        "data": product_result["data"],
                        "quantity": quantity,
                        "auto_selected": True
                    })
                    logger.info(f"✅ Produit auto-sélectionné: {product_code}")
                                                            
            # Traitement des résultats
            if not products_needing_interaction:
                # Tous les produits auto-sélectionnés
                efficiency_tip = f"✨ {auto_selected_count} produit(s) automatiquement identifié(s) ! Pour plus d'efficacité, utilisez les codes de référence précis."

                try:
                    await websocket_manager.send_task_update(self.task_id, {
                        "type": "auto_selection",
                        "step": "products_auto_selected",
                        "message": f"✅ {auto_selected_count} produit(s) automatiquement sélectionné(s)",
                        "efficiency_tip": efficiency_tip,
                        "show_tip": True
                    })
                except Exception as ws_error:
                    logger.warning(f"⚠️ Erreur envoi WebSocket (non bloquant): {ws_error}")
                
                self.context["products_info"] = [p["data"] for p in validated_products]
                self._track_step_complete("get_products_info", f"{len(validated_products)} produit(s) validé(s)")
                
                # Continuer vers la génération du devis
                # Vérifier si des produits nécessitent sélection
                if products_needing_selection:
                    logger.info(f"⚠️ {len(products_needing_selection)} produit(s) nécessite(nt) sélection")
                    await self._send_product_selection_interaction(products_needing_selection)
                    return {
                        "status": "product_selection_required",
                        "products": products_needing_selection,
                        "task_id": self.task_id,
                        "message": f"{len(products_needing_selection)} produit(s) nécessite(nt) votre sélection"
                    }
                
                # Si tous les produits sont validés, continuer
                # Transformer les produits validés en format attendu par _continue_quote_generation
                products_for_generation = {"products": [p.get("data", p) for p in validated_products]}
                return await self._continue_quote_generation(products_for_generation)
                
            else:
                # Certains produits nécessitent une interaction
                logger.info(f"⚠️ {len(products_needing_interaction)} produit(s) nécessite(nt) sélection utilisateur")
                await self._send_product_selection_interaction(products_needing_interaction)
                return {
                    "status": "user_interaction_required",
                    "interaction_type": "product_selection", 
                    "products": products_needing_interaction,
                    "task_id": self.task_id,
                    "message": f"{len(products_needing_interaction)} produit(s) nécessite(nt) votre sélection"
                }
        except asyncio.CancelledError:
            logger.warning("⚠️ Recherche produits interrompue")
            return {"error": "Recherche interrompue", "cancelled": True}        
        except Exception as e:
            logger.exception(f"Erreur _get_products_info_with_auto_selection: {e}")
            return self._build_error_response("Erreur validation produits", str(e))

    def _generate_product_efficiency_tip(self, product_code: str, product_name: str) -> str:
        """Génère des conseils d'efficacité pour les produits"""
        tips = []
        
        # Conseil sur les codes de référence
        if not product_code or len(product_code) < 3:
            tips.append("💡 Utilisez le code de référence exact pour une recherche plus rapide")
        
        # Conseil sur les caractéristiques
        generic_terms = ["imprimante", "ordinateur", "écran", "scanner"]
        if any(term in product_name.lower() for term in generic_terms):
            tips.append("💡 Précisez le modèle, la marque ou les caractéristiques (ex: 'HP LaserJet', 'A4 couleur')")
        
        # Conseil général
        if not tips:
            tips.append("💡 Plus vous précisez le produit, plus la recherche sera efficace")
        
        return tips[0] if tips else ""

    async def _handle_mixed_product_validation(self, validated_products: List, products_needing_interaction: List) -> Dict:
        """Gère le cas mixte : certains produits auto-sélectionnés, d'autres nécessitent interaction"""
        
        first_unresolved = products_needing_interaction[0]
        product_suggestions = first_unresolved["suggestions"]
        efficiency_tip = first_unresolved["efficiency_tip"]
        
        # Préparer les options pour l'utilisateur
        options = []
        for i, suggestion in enumerate(product_suggestions[:5], 1):
            options.append({
                "id": suggestion.get("ItemCode", f"option_{i}"),
                "label": f"{suggestion.get('ItemName', 'N/A')} (Ref: {suggestion.get('ItemCode', 'N/A')})",
                "value": suggestion.get("ItemCode"),
                "data": suggestion
            })
        
        # Préparer la validation pour l'interaction utilisateur
        validation_data = {
            "type": "product_selection",
            "interaction_type": "product_selection", 
            "product": first_unresolved["original"],
            "options": options,
            "validated_products": validated_products,
            "remaining_products": products_needing_interaction[1:],
            "efficiency_tip": efficiency_tip,
            "message": f"Sélectionnez le produit pour '{first_unresolved['original'].get('name', '')}'",
            "show_tip": True
        }
        
        # Marquer la tâche en attente d'interaction
        if self.current_task:
            self.current_task.status = TaskStatus.PENDING
            self.current_task.require_user_validation("product_selection", "product_selection", validation_data)
        
        # Envoyer via WebSocket
        try:
            await websocket_manager.send_user_interaction_required(self.task_id, validation_data)
        except Exception as ws_error:
            logger.warning(f"⚠️ Erreur envoi WebSocket (non bloquant): {ws_error}")
        
        return {
            "success": True,
            "status": "user_interaction_required",
            "type": "product_selection",
            "message": "Sélection de produit requise",
            "task_id": self.task_id,
            "interaction_data": validation_data
        }
    # 🆕 MÉTHODES AUXILIAIRES POUR LA VALIDATION SÉQUENTIELLE
    async def _send_product_selection_interaction(self, products_needing_selection: List[Dict]) -> None:
        """Envoie l'interaction de sélection de produits via WebSocket"""
        try:
            
            interaction_data = {
                "type": "product_selection",
                "interaction_type": "product_selection",
                "products_needing_selection": products_needing_selection,
                "message": f"{len(products_needing_selection)} produits nécessitent votre sélection",
                "options": []
            }
            
            for product_info in products_needing_selection:
                interaction_data["options"].append({
                    "name": product_info.get("original_name"),
                    "quantity": product_info.get("quantity"),
                    "choices": [{
                        **option,
                        "Price": option.get("Price") or option.get("AvgPrice") or self._estimate_product_price(option.get("ItemName", "")),
                        "display_price": f"{option.get('Price') or option.get('AvgPrice') or self._estimate_product_price(option.get('ItemName', ''))}€"
                    } for option in product_info.get("options", [])]
                })
            
            # Stocker les données d'interaction dans la tâche pour récupération ultérieure
            task = progress_tracker.get_task(self.task_id)
            if task:
                task.interaction_data = interaction_data
                logger.info(f"📦 Données d'interaction stockées avec quantités")

            await websocket_manager.send_user_interaction_required(self.task_id, interaction_data)
            logger.info(f"✅ Interaction produit envoyée pour {len(products_needing_selection)} produits")
            
        except Exception as e:
            logger.error(f"❌ Erreur envoi interaction produit: {e}")
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

    async def _parallel_client_product_search(self, client_name: str, products: List[Dict]) -> Dict[str, Any]:
        """Recherche parallèle client et produits pour optimiser les performances"""
        try:
            logger.info(f"🚀 Recherche parallèle - Client: {client_name}, Produits: {len(products)}")

            # Notification début recherche parallèle
            await self._notify_websocket("parallel_search_started", {
                "client_query": client_name,
                "product_count": len(products),
                "message": "Recherche parallèle client et produits..."
            })

            # Créer les tâches parallèles
            client_task = asyncio.create_task(
                self._search_client_parallel(client_name)
            )
            products_task = asyncio.create_task(
                self._search_products_parallel(products)
            )

            # Exécution parallèle avec gestion d'exceptions
            client_result, products_result = await asyncio.gather(
                client_task, products_task, return_exceptions=True
            )

            # Gestion des erreurs de tâches
            if isinstance(client_result, Exception):
                logger.error(f"❌ Erreur recherche client parallèle: {client_result}")
                client_result = {"found": False, "error": str(client_result)}

            if isinstance(products_result, Exception):
                logger.error(f"❌ Erreur recherche produits parallèle: {products_result}")
                products_result = {"status": "error", "products": [], "error": str(products_result)}

            # Traitement des résultats
            return await self._process_parallel_results(client_result, products_result)

        except Exception as e:
            logger.exception(f"❌ Erreur recherche parallèle: {e}")
            # Fallback vers méthode séquentielle
            return {"status": "fallback_to_sequential", "error": str(e)}

    async def _search_client_parallel(self, client_name: str) -> Dict[str, Any]:
        """Recherche client optimisée pour parallélisation"""
        try:
            # Utiliser la logique existante sans les track_step qui sont séquentiels
            return await self._process_client_validation(client_name)
        except Exception as e:
            logger.error(f"❌ Erreur recherche client: {e}")
            return {"found": False, "error": str(e)}

    async def _search_products_parallel(self, products: List[Dict]) -> Dict[str, Any]:
        """Recherche produits optimisée pour parallélisation"""
        try:
            # Utiliser la logique existante sans les track_step
            return await self._process_products_retrieval(products)
        except Exception as e:
            logger.error(f"❌ Erreur recherche produits: {e}")
            return {"status": "error", "products": [], "error": str(e)}

    async def _process_parallel_results(self, client_result: Dict, products_result: Dict) -> Dict[str, Any]:
        """Traite les résultats de la recherche parallèle"""
        try:
            # Vérifier si interactions utilisateur requises
            interactions_needed = []

            # Client nécessite interaction
            if client_result.get("status") == "user_interaction_required":
                interactions_needed.append({
                    "type": "client_selection",
                    "data": client_result
                })

            # Produits nécessitent interaction
            if products_result.get("status") == "product_selection_required":
                interactions_needed.append({
                    "type": "product_selection",
                    "data": products_result
                })

            # Si interactions requises, prioriser client puis produits
            if interactions_needed:
                # Retourner la première interaction (client prioritaire)
                first_interaction = interactions_needed[0]

                # Stocker les autres interactions pour plus tard
                if len(interactions_needed) > 1:
                    self.context["pending_interactions"] = interactions_needed[1:]

                return first_interaction["data"]

            # Si tout est validé, continuer vers génération
            if (client_result.get("found") and
                products_result.get("status") == "success"):

                # Mettre à jour le contexte
                self.context["client_info"] = client_result
                self.context["products_info"] = products_result.get("products", [])

                logger.info("✅ Recherche parallèle réussie - Passage à la génération")
                return await self._continue_quote_generation({
                    "client": client_result,
                    "products": products_result.get("products", [])
                })

            # Cas d'erreur mixte
            errors = []
            if not client_result.get("found"):
                errors.append(f"Client non trouvé: {client_result.get('error', 'N/A')}")
            if products_result.get("status") != "success":
                errors.append(f"Produits non trouvés: {products_result.get('error', 'N/A')}")

            return {
                "status": "error",
                "message": "Erreurs lors de la recherche parallèle",
                "errors": errors
            }

        except Exception as e:
            logger.exception(f"❌ Erreur traitement résultats parallèles: {e}")
            return {
                "status": "error",
                "message": "Erreur traitement résultats parallèles",
                "error": str(e)
            }

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

    async def _process_quote_workflow(self, extracted_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 REFONTE : Workflow de devis avec gestion d'interruption client et statuts critiques
        """
        try:
            # 0) Entrées extraites du prompt
            client_name = extracted_info.get("client", "")
            products = extracted_info.get("products", [])
            # IMPORTANT: Sauvegarder extracted_info dans le contexte pour que _process_client_validation puisse y accéder
            self.context["extracted_info"] = extracted_info
            logger.info(f"✅ Contexte initialisé avec extracted_info - client: {client_name}, produits: {len(products)}")
            # NOUVEAU : Vérifier si recherche parallèle a déjà eu lieu
            if not hasattr(self, '_parallel_search_done'):
                parallel_search_result = await self._parallel_client_product_search(client_name, products)
                self._parallel_search_done = True
                # Si interactions requises, s'arrêter ici
                if parallel_search_result.get("status") in ["user_interaction_required", "product_selection_required"]:
                    return parallel_search_result
                # Si erreur, fallback vers séquentiel
                if parallel_search_result.get("status") == "fallback_to_sequential":
                    logger.warning("⚠️ Fallback vers recherche séquentielle")
                else:
                    # Recherche parallèle réussie, continuer directement à la génération
                    if parallel_search_result.get("status") not in ["error"]:
                        return parallel_search_result
            # Fallback séquentiel si parallèle a échoué
            # Étape 1 : recherche/validation du client
            self._track_step_start("search_client", f"👤 Recherche du client : {client_name}")
            client_result = await self._process_client_validation(client_name)
            # 🔒 Garde-fous
            if client_result is None:
                logger.error("❌ _process_client_validation a retourné None")
                return {
                    "success": False,
                    "status": "error",
                    "message": "Erreur lors de la validation du client",
                    "error": "client_validation_failed"
                }
            # ⏸️ Cas d'interaction utilisateur requise (sélection client)
            if client_result.get("status") in ["user_interaction_required", "client_selection_required"]:
                # Récupérer des options client de manière robuste
                interaction_data = client_result.get("interaction_data") or client_result
                client_options = (
                    interaction_data.get("client_options")
                    or interaction_data.get("options")
                    or interaction_data.get("clients")
                    or []
                )
                # Construire la validation_data ENRICHIE avec le contexte initial (client + produits)
                validation_data = {
                    "options": client_options,
                    "clients": client_options,
                    "client_options": client_options,
                    "total_options": len(client_options),
                    "original_client_name": client_name,
                    "allow_create_new": True,
                    "interaction_type": "client_selection",
                    "original_context": {
                        "extracted_info": {
                            "client": client_name,
                            "products": products
                        }
                    }
                }
                # Marquer la tâche et enregistrer l'attente d'interaction
                if self.current_task:
                    # 🔑 Un SEUL appel, avec le contexte complet
                    self.current_task.require_user_validation("client_selection", "client_selection", validation_data)
                # Logs de debug utiles
                if not client_options:
                    logger.error("❌ ERREUR: Pas de client_options dans validation_data")
                    logger.error(f"❌ Structure envoyée: {json.dumps(validation_data, indent=2, default=str)}")
                else:
                    logger.info(f"✅ {len(client_options)} clients prêts pour sélection")
                # Retour standardisé pour le front
                return {
                    "success": True,
                    "status": "user_interaction_required",
                    "type": "client_selection",
                    "message": "Sélection du client requise",
                    "task_id": self.task_id,
                    "interaction_data": validation_data
                }
            # 🔧 Statuts bloquants
            if client_result.get("status") in ["error", "cancelled"]:
                logger.warning(f"❌ Workflow interrompu - Statut client : {client_result.get('status')}")
                return client_result
            self._track_step_complete("search_client", f"✅ Client : {client_result.get('status')}")
            # CORRECTION CRITIQUE: Vérification doublons IMMÉDIATEMENT après validation du client
            self._track_step_start("check_duplicates", "🔍 Vérification des doublons...")
            
            # Utiliser le client du contexte si disponible (pour après sélection)
            client_info_for_duplicates = client_result
            if self.context.get("client_validated") and self.context.get("client_info"):
                logger.info("🔄 Utilisation du client du contexte (post-sélection)")
                client_info_for_duplicates = self.context["client_info"]
            
            # 🔧 Honorer skip_duplicate_check (forçage 'créer malgré les doublons')
            if getattr(self, "skip_duplicate_check", False) or self.context.get("skip_duplicate_check"):
                logger.info("⏭️ Vérification doublons ignorée (skip_duplicate_check actif)")
                duplicate_check = {}
            else:
                duplicate_check = await self._check_duplicate_quotes(
                    client_info=client_info_for_duplicates,
                    products=products
                )

            self.context["duplicate_check"] = duplicate_check
            
            # Si doublons trouvés ET nécessite une décision utilisateur
            if duplicate_check.get("requires_user_decision"):
                client_name_for_alert = (
                    client_info_for_duplicates.get("data", {}).get("Name") or 
                    client_info_for_duplicates.get("name") or 
                    client_name
                )
                
                self._track_step_progress("check_duplicates", 90, duplicate_check.get("alert_message", "Doublons détectés"))
                
                duplicate_interaction_data = {
                    "type": "duplicate_resolution",
                    "interaction_type": "duplicate_resolution",
                    "client_name": client_name_for_alert,
                    "alert_message": duplicate_check.get("alert_message"),
                    "recent_quotes": duplicate_check.get("recent_quotes", []),
                    "draft_quotes": duplicate_check.get("draft_quotes", []),
                    "similar_quotes": duplicate_check.get("similar_quotes", []),
                    "extracted_info": extracted_info,
                    "options": [
                        {"value": "proceed", "label": "Créer un nouveau devis malgré les doublons"},
                        {"value": "consolidate", "label": "Consolider avec un devis existant"},
                        {"value": "review", "label": "Examiner les devis existants d'abord"},
                        {"value": "cancel", "label": "Annuler la demande"}
                    ],
                    "input_type": "choice"
                }
                
                # Marquer la tâche en attente d'interaction
                if self.current_task:
                    self.current_task.status = TaskStatus.PENDING
                    self.current_task.require_user_validation(
                        "duplicate_resolution",
                        "duplicate_resolution",
                        duplicate_interaction_data
                    )
                
                # Envoyer via WebSocket
                try:
                    await websocket_manager.send_user_interaction_required(
                        self.task_id,
                        duplicate_interaction_data
                    )
                    logger.info("✅ Alerte de doublon envoyée via WebSocket")
                except Exception as ws_error:
                    logger.warning(f"⚠️ Erreur envoi WebSocket alerte doublon: {ws_error}")
                
                return {
                    "success": True,
                    "status": "user_interaction_required",
                    "type": "duplicate_resolution",
                    "message": duplicate_check.get("alert_message"),
                    "task_id": self.task_id,
                    "interaction_data": duplicate_interaction_data
                }
            
            # Si doublons détectés mais sans interaction requise, continuer avec warning
            if duplicate_check.get("duplicates_found"):
                logger.warning(f"⚠️ {len(duplicate_check.get('warnings', []))} doublons détectés - Continuation du workflow")
            else:
                logger.info("✅ Aucun doublon détecté")
            
            self._track_step_complete("check_duplicates", "✅ Vérification doublons terminée")            
            # Étape 2 : récupération des produits
            self._track_step_start("lookup_products", f"📦 Recherche de {len(products)} produit(s)")
            products_result = await self._process_products_retrieval(products) or {}
            if not isinstance(products_result, dict):
                logger.error("❌ _process_products_retrieval a retourné un type invalide")
                products_result = {"status": "error", "products": []}
            # VÉRIFICATION CRITIQUE : Arrêter le workflow si sélection de produits requise
            if products_result.get("status") == "product_selection_required":
                # Envoyer l'interaction WebSocket avant de s'arrêter
                try:
                    await self._send_product_selection_interaction(products_result.get("products", []))
                except Exception as ws_error:
                    logger.warning(f"⚠️ Erreur envoi WebSocket interaction produits: {ws_error}")
                logger.warning("⚠️ Sélection de produits requise - Arrêt du workflow")
                self._track_step_fail("lookup_products", "Produits non trouvés", "Sélection manuelle requise")
                return {
                    "success": False,
                    "status": "user_interaction_required",
                    "interaction_type": "product_selection",
                    "message": products_result.get("message", "Sélection de produits requise"),
                    "products_info": products_result.get("products", []),
                    "task_id": self.task_id
                }

            # Vérification des produits valides AVANT création du devis
            raw_products = products_result.get("products", []) if isinstance(products_result.get("products", []), list) else []
            valid_products = [p for p in raw_products if not p.get("error") and not p.get("requires_manual_search")]
            if not valid_products:
                error_msg = "Aucun produit valide trouvé dans le catalogue SAP"
                if raw_products:
                    errors = [p.get("error", "Produit non trouvé") for p in raw_products if p.get("error")]
                    if errors:
                        error_msg = f"Erreurs produits: {'; '.join(set(errors))}"
                logger.error(f"❌ {error_msg}")
                self._track_step_fail("lookup_products", "Produits invalides", error_msg)
                return {"success": False, "error": error_msg, "status": "product_error"}
            found = len(valid_products)  # Utiliser les produits réellement valides
            self._track_step_complete("lookup_products", f"✅ {found} produit(s) trouvé(s)")
            # Étape 3 : préparation et prévisualisation du devis
            self._track_step_start("prepare_quote", "📋 Préparation du devis")
            quote_preview = await self._prepare_quote_preview(client_result, products_result)
            self._track_step_complete("prepare_quote", "✅ Devis préparé")
            
            # Demander validation utilisateur avant création
            if not quote_preview.get("error"):
                # B6 : enveloppe conventionnelle {data, found, status} (cf. sites :961 / :5480)
                # au lieu d'envoyer le brut client_result {status, data, message}.
                client_info_payload = {
                    "data": client_result.get("data"),
                    "found": bool(client_result.get("data")),
                    "status": client_result.get("status"),
                }
                validation_data = {
                    "type": "quote_validation",
                    "interaction_type": "quote_validation",
                    "quote_preview": quote_preview,
                    "client_info": client_info_payload,
                    "products": valid_products,  # ✅ uniquement valides
                    "message": "Veuillez valider le devis avant création",
                    "total_amount": quote_preview.get("total_amount", 0),
                    "currency": quote_preview.get("currency", "EUR")
                }
                if self.current_task:
                    self.current_task.status = TaskStatus.PENDING
                    self.current_task.require_user_validation("quote_validation", "quote_validation", validation_data)
                try:
                    await websocket_manager.send_user_interaction_required(self.task_id, validation_data)
                except Exception as ws_error:
                    logger.warning(f"⚠️ Erreur envoi WebSocket (non bloquant): {ws_error}")
                return {
                    "success": True,
                    "status": "user_interaction_required",
                    "type": "quote_validation",
                    "message": "Validation du devis requise",
                    "task_id": self.task_id,
                    "interaction_data": validation_data
                }

            self._track_step_start("create_quote", "🧾 Création du devis")
            quote_result = await self._create_quote_document(client_result, products_result)
            if not isinstance(quote_result, dict):
                logger.error("❌ _create_quote_document a retourné un résultat invalide")
                quote_result = {"status": "error", "quote_data": {}}
            # Extraction sécurisée de quote_data
            quote_data = quote_result.get("quote_data") or {}
            returned_products = quote_data.get("products") or valid_products  # Utiliser produits valides uniquement
            if not returned_products:
                logger.warning("❌ Aucun produit valide pour le devis")
                return {"success": False, "error": "Aucun produit valide trouvé"}
            # Étape 4 : synchronisation dans le système externe (SAP)
            self._track_step_start("sync_external_systems", "💾 Synchronisation SAP")
            sync_results = {}
            for system in ("sap",):
                key = f"sync_to_{system}"
                self._track_step_start(key, f"{'💾' if system=='sap' else '☁️'} Enregistrement dans {system.upper()}")
                # Ajouter simulation temporelle même en mode draft
                if getattr(self, "draft_mode", False):
                    logger.info(f"🎯 MODE DRAFT - Simulation synchronisation {system.upper()}")
                    await asyncio.sleep(0.5)  # Simulation réaliste
                    result = {"status": "success", "simulated": True, "message": f"Simulation {system} réussie"}
                else:
                    result = await self._sync_quote_to_systems(quote_result, target=system)
                # Vérifier le résultat avant de marquer comme terminé
                if result.get("status") == "success":
                    self._track_step_complete(key, f"✅ {system.upper()} mis à jour")
                else:
                    error_msg = result.get("message", f"Erreur {system}")
                    self._track_step_fail(key, f"❌ Erreur {system.upper()}", error_msg)
                sync_results[system] = result
            # Total
            total_amount = sum(p.get("total_price", 0) for p in returned_products)
            # Résultat final
            return {
                "success": True,
                "status": quote_result.get("status", "success"),
                "type": "quote_generated",
                "message": "✅ Devis généré avec succès !",
                "task_id": self.task_id,
                "workflow_steps": getattr(self, "workflow_steps", []),
                "quote_id": quote_data.get("quote_id", ""),
                "client": quote_data.get("client", client_result.get("client_data", {})),
                "products": returned_products,
                "total_amount": total_amount,
                "currency": quote_data.get("currency", "EUR"),
                "quote_data": quote_data,
                "client_result": client_result,
                "products_result": products_result,
                "sync_results": sync_results
            }
        except HTTPException:
            # Réélever les erreurs HTTP
            raise
        except Exception as e:
            logger.exception(f"Erreur _process_quote_workflow: {e}")
            return {
                "success": False,
                "status": "error",
                "message": "Erreur interne pendant le workflow de devis",
                "error": str(e)
            }

    async def _prepare_quote_preview(self, client_result: Dict[str, Any], products_result: Dict[str, Any]) -> Dict[str, Any]:
        """Prépare l'aperçu du devis pour validation utilisateur"""
        try:
            from datetime import datetime, timedelta
            
            client_data = client_result.get("data", {})
            products = products_result.get("products", [])
            
            # Calculer totaux
            subtotal = sum(p.get("total_price", 0) for p in products if p.get("found"))
            tax_rate = 0.196  # TVA 19.6%
            tax_amount = subtotal * tax_rate
            total_amount = subtotal + tax_amount
            
            # Formatage des produits pour aperçu
            formatted_products = []
            for product in products:
                if product.get("found") and product.get("data"):
                    product_data = product["data"]
                    formatted_products.append({
                        "code": product_data.get("ItemCode", ""),
                        "name": product_data.get("ItemName", ""),
                        "quantity": product.get("quantity", 1),
                        "unit_price": product.get("unit_price", 0),
                        "total_price": product.get("total_price", 0),
                        "stock": product_data.get("OnHand", 0)
                    })

            preview = {
                "client_name": client_data.get("CardName") or client_data.get("Name", ""),
                "client_code": client_data.get("CardCode") or client_data.get("AccountNumber", ""),
                "products": formatted_products,
                "subtotal": subtotal,
                "tax_rate": tax_rate,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "currency": "EUR",
                "doc_date": datetime.now().strftime("%Y-%m-%d"),
                "due_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            }
            
            logger.info(f"📋 Aperçu devis préparé - Total: {total_amount}€")
            return preview
            
        except Exception as e:
            logger.error(f"❌ Erreur préparation aperçu devis: {str(e)}")
            return {"error": str(e)}


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
        return escape_soql(value)
    

    async def _propose_existing_clients_selection(self, client_name: str, search_results: Dict[str, Any]) -> Dict[str, Any]:
        """Propose la sélection du client avec interface utilisateur - AMÉLIORÉ"""
        try:
            option_id = 1
            client_options: List[Dict[str, Any]] = []

            # Sources
            deduplicated_clients = search_results.get("deduplicated_clients", []) or []
            all_sf_clients = search_results.get("salesforce", {}).get("clients", []) or []
            all_sap_clients = search_results.get("sap", {}).get("clients", []) or []

            # 1) Priorité aux clients dédupliqués si présents
            if deduplicated_clients:
                logger.info("✅ Utilisation des clients dédupliqués")
                for client in deduplicated_clients:
                    if not client:
                        continue
                    source = (client.get("source") or "Unknown").strip()
                    source_raw = source.lower().replace(" & ", "_").replace(" ", "_")
                    client_options.append({
                        "id": option_id,
                        "name": client.get("Name") or client.get("CardName", "Client sans nom"),
                        "source": source,
                        "source_raw": source_raw,
                        "display_detail": f"Client {source}",
                        "sf_id": client.get("Id", ""),
                        "sap_code": client.get("CardCode", ""),
                        "details": self._format_client_details(client, source)
                    })
                    option_id += 1
                logger.info(f"✅ {len(client_options)} options préparées (dédupliquées)")
                # Si des clients dédupliqués existent, ne pas traiter séparément SF et SAP
                return await self._finalize_client_selection(client_name, client_options)
            else:
                logger.info("⚠️ Pas de déduplication disponible - traitement individuel")

            logger.info(f"🔧 Traitement de {len(all_sf_clients)} clients SF + {len(all_sap_clients)} clients SAP")

            # 2) Auto-sélection si un seul client au total
            total_clients = len(all_sf_clients) + len(all_sap_clients)
            # Vérifier si c'est vraiment un client unique ou si la déduplication a masqué des différences
            if len(all_sf_clients) + len(all_sap_clients) > 1:
                logger.warning(f"⚠️ Déduplication suspecte : {len(all_sf_clients)} SF + {len(all_sap_clients)} SAP réduits à 1 client")
                # Forcer l'affichage des options pour les cas ambigus
                if any("group" in (client.get("Name") or client.get("CardName", "")).lower() 
                       for client in all_sf_clients + all_sap_clients):
                    logger.info("🔍 Clients avec 'Group' détectés - Affichage forcé des options")
                    # Continuer vers la sélection manuelle au lieu de l'auto-sélection
                else:
                    single_client = all_sf_clients[0] if all_sf_clients else all_sap_clients[0]
            else:
                single_client = all_sf_clients[0] if all_sf_clients else all_sap_clients[0]
                client_display_name = single_client.get("Name") or single_client.get("CardName", "Client sans nom")
                logger.info(f"✅ Auto-sélection client unique: {client_display_name}")

                efficiency_tip = self._generate_client_efficiency_tip(client_name, single_client)

                # Maj contexte
                if hasattr(self, "context") and isinstance(self.context, dict):
                    self.context.update({
                        "client_info": {"data": single_client, "found": True},
                        "client_validated": True,
                        "selected_client_display": client_display_name
                    })
                    # NOUVEAU: Sauvegarder le contexte dans la tâche
                    self._save_context_to_task()

                # Produits pour continuation
                products_list: List[Dict[str, Any]] = []
                try:
                    if hasattr(self, "context") and isinstance(self.context, dict):
                        extracted_info = self.context.get("extracted_info") or {}
                        products_list = extracted_info.get("products", []) or []
                except Exception as e:
                    logger.error(f"❌ Erreur lors de l'extraction des produits: {e}")
                    products_list = []

                # Continuer si produits connus
                try:
                    await websocket_manager.send_task_update(self.task_id, {
                        "type": "auto_selection",
                        "step": "client_auto_selected",
                        "message": f"✅ Client '{client_display_name}' automatiquement sélectionné",
                        "efficiency_tip": efficiency_tip,
                        "show_tip": True
                    })
                except Exception as ws_error:
                    logger.warning(f"⚠️ Impossible d'envoyer via WebSocket: {ws_error}")

                if products_list:
                    self._track_step_complete("search_client", f"✅ Client auto-sélectionné: {client_display_name}")
                    self._track_step_start("lookup_products", f"📦 Recherche de {len(products_list)} produit(s)")
                    return await self._continue_workflow_after_client_selection(
                        single_client,
                        {"extracted_info": {"products": products_list}}
                    )
                else:
                    return self._build_product_request_response(client_display_name)

            # 3) Construire options SF
            for sf_client in all_sf_clients:
                if not sf_client:
                    continue
                client_options.append({
                    "id": option_id,
                    "name": sf_client.get("Name", f"Client SF {option_id}"),
                    "source": "Salesforce",
                    "source_raw": "salesforce",
                    "display_detail": "Client Salesforce",
                    "sf_id": sf_client.get("Id", ""),
                    "sap_code": "",
                    "details": {
                        "sf_id": sf_client.get("Id", ""),
                        "sap_code": "",
                        "phone": sf_client.get("Phone"),
                        "address": f"{sf_client.get('BillingStreet', '')}, {sf_client.get('BillingCity', '')}".strip(", "),
                        "city": sf_client.get("BillingCity"),
                        "postal_code": sf_client.get("BillingPostalCode"),
                        "country": sf_client.get("BillingCountry"),
                        "siret": sf_client.get("Sic"),
                        "industry": sf_client.get("Industry", "N/A")
                    }
                })
                option_id += 1

            # 4) Construire options SAP
            for sap_client in all_sap_clients:
                if not sap_client:
                    continue
                client_options.append({
                    "id": option_id,
                    "name": sap_client.get("CardName", f"Client SAP {option_id}"),
                    "source": "SAP",
                    "source_raw": "sap",
                    "display_detail": "Client SAP",
                    "sf_id": "",
                    "sap_code": sap_client.get("CardCode", ""),
                    "details": {
                        "sf_id": "",
                        "sap_code": sap_client.get("CardCode", ""),
                        "phone": sap_client.get("Phone1"),
                        "address": sap_client.get("BillToStreet", "N/A"),
                        "city": sap_client.get("City"),
                        "postal_code": sap_client.get("ZipCode") if "ZipCode" in sap_client else None,
                        "country": sap_client.get("Country") if "Country" in sap_client else None,
                        "siret": sap_client.get("FederalTaxID"),
                        "industry": "N/A"
                    }
                })
                option_id += 1

            # 5) Dé-duplication finale par (sf_id, sap_code, name, source_raw)
            seen: set = set()
            deduped_options: List[Dict[str, Any]] = []
            for opt in client_options:
                key = (opt.get("sf_id", ""), opt.get("sap_code", ""), opt.get("name", ""), opt.get("source_raw", ""))
                if key in seen:
                    continue
                seen.add(key)
                deduped_options.append(opt)
            client_options = deduped_options

            logger.info(f"🔧 Préparation de {len(client_options)} options pour sélection")

            # 6) Debug contexte (sécurisé)
            try:
                import json  # local import pour éviter dépendance globale
                logger.info(f"🔍 DEBUG: self.context = {json.dumps(self.context, indent=2, default=str)}")
            except Exception as _:
                logger.info("🔍 DEBUG: contexte non sérialisable")

            # 7) Produits du contexte
            products_list: List[Dict[str, Any]] = []
            try:
                if hasattr(self, "context") and isinstance(self.context, dict):
                    extracted_info = self.context.get("extracted_info", {}) or {}
                    products_list = extracted_info.get("products", []) or []
                    logger.info(f"🔍 DEBUG: Produits extraits = {products_list}")
                else:
                    logger.warning("⚠️ Contexte non initialisé ou vide")
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'extraction des produits: {e}")
                products_list = []

            # 8) Validation utilisateur (garde si current_task absent)
            validation_data = {
                "options": client_options,
                "clients": client_options,
                "client_options": client_options,
                "total_options": len(client_options),
                "original_client_name": client_name,
                "allow_create_new": True,
                "interaction_type": "client_selection",
                "original_context": {
                    "extracted_info": {
                        "client": client_name,
                        "products": products_list
                    }
                }
            }
            try:
                if getattr(self, "current_task", None):
                    self.current_task.require_user_validation("client_selection", "client_selection", validation_data)
                else:
                    logger.warning("⚠️ current_task absent: impossible de pousser la validation dans le tracker")
            except Exception as e:
                logger.error(f"❌ Erreur lors du require_user_validation: {e}")

            # 9) Emission WebSocket
            interaction_message = {
                "type": "client_selection",
                "interaction_type": "client_selection",
                "options": client_options,
                "clients": client_options,
                "client_options": client_options,
                "total_options": len(client_options),
                "original_client_name": client_name,
                "allow_create_new": True,
                "message": f"Sélection client requise - {len(client_options)} options disponibles"
            }
            try:
                await websocket_manager.send_user_interaction_required(self.task_id, interaction_message)
                logger.info(f"✅ Message WebSocket envoyé pour task {self.task_id} avec {len(client_options)} options")
            except Exception as ws_error:
                logger.warning(f"⚠️ Impossible d'envoyer via WebSocket: {ws_error}")

            # 10) Retour API
            return {
                "status": "user_interaction_required",
                "requires_user_selection": True,
                "validation_pending": True,
                "task_id": self.task_id,
                "message": f"Sélection client requise - {len(client_options)} options disponibles",
                "interaction_type": "client_selection",
                "interaction_data": interaction_message,
                "client_options": client_options,
                "total_options": len(client_options),
                "original_client_name": client_name,
                "allow_create_new": True
            }

        except Exception as e:
            logger.error(f"❌ Erreur proposition sélection clients: {e}")
            import traceback
            logger.error(f"❌ Traceback complet: {traceback.format_exc()}")
            return {"status": "error", "found": False, "error": str(e)}

    async def _finalize_client_selection(self, client_name: str, client_options: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Finalise la sélection client avec les options dédupliquées uniquement"""
        
        try:
            # Auto-sélection si un seul client
            if len(client_options) == 1:
                single_client = client_options[0]
                client_display_name = single_client.get("name", "Client sans nom")
                logger.info(f"✅ Auto-sélection client unique: {client_display_name}")
                
                # Mettre à jour le contexte
                self.context.update({
                    "client_info": {"data": single_client, "found": True},
                    "client_validated": True,
                    "selected_client_display": client_display_name
                })
                
                return {
                    "status": "auto_selected",
                    "client_data": single_client,
                    "message": f"Client unique sélectionné: {client_display_name}"
                }
            
            # Plusieurs clients - demander sélection
            validation_data = {
                "options": client_options,
                "clients": client_options,
                "client_options": client_options,
                "total_options": len(client_options),
                "original_client_name": client_name,
                "allow_create_new": True,
                "interaction_type": "client_selection"
            }
            
            if self.current_task:
                self.current_task.require_user_validation("client_selection", "client_selection", validation_data)
            
            # Préparer le message d'interaction
            interaction_message = {
                "type": "client_selection",
                "interaction_type": "client_selection",
                **validation_data,
                "message": f"Sélection client requise - {len(client_options)} options disponibles"
            }
            
            # Envoyer via WebSocket
            try:
                await websocket_manager.send_user_interaction_required(self.task_id, interaction_message)
            except Exception as ws_error:
                logger.warning(f"⚠️ Erreur envoi WebSocket (non bloquant): {ws_error}")
            
            return {
                "status": "user_interaction_required",
                "interaction_data": interaction_message,
                "message": f"Sélection parmi {len(client_options)} options disponibles"
            }
            
        except Exception as e:
            logger.exception(f"Erreur finalisation sélection client: {str(e)}")
            return self._build_error_response("Erreur sélection client", str(e))


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
                
                sap_results = await self.mcp_connector.call_mcp(
                    "sap_mcp",
                    "sap_create_customer_complete",
                    {"customer_data": sap_client_data}
                )

                if not sap_results.get("success", False):
                    logger.error(f"❌ Échec création SAP: {sap_results.get('error')}")
                    return {
                        "created": False,
                        "error": f"Erreur SAP: {sap_results.get('error', 'Erreur inconnue')}"
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
                    "Description": f"Client cree automatiquement depuis SAP ({card_code})"
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
        Validation complète du client via recherche SAP (find_client_everywhere) et enrichissement.
        🔧 CORRIGÉ: Détection et arrêt pour interaction utilisateur
        """
        if not client_name or not client_name.strip():
            return {
                "status": "error",
                "data": None,
                "message": "Nom de client vide"
            }

        try:
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
            # === ÉTAPE 4: RECHERCHE DANS SAP ===
            self._track_step_progress("search_client", 60, "🔍 Recherche dans SAP")
            sap_results = await self.mcp_connector.call_mcp("sap_mcp", "sap_search", {
                "query": client_name,
                "entity_type": "BusinessPartners",
                "limit": 5
            })

            if sap_results.get("success") and sap_results.get("count", 0) > 0:
                for sap_client in sap_results.get("results", []):
                    if sap_client.get("CardName", "").upper() == client_name.upper():
                        logger.info(f"✅ Client trouvé dans SAP: {sap_client['CardName']}")
                        return {
                            "status": "found",
                            "data": sap_client,
                            "message": "Client trouvé dans SAP",
                            "source": "sap"
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
            create_result = await self.mcp_connector.call_sap_mcp(
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
        """Génère mots-clés de recherche pour SAP"""
        import re
        import unicodedata

        # Garde-fou
        if not product_name or not isinstance(product_name, str):
            return []

        def _normalize(s: str) -> str:
            # lower + suppression des accents pour matcher "écran" vs "ecran"
            s_nfkd = unicodedata.normalize("NFKD", s)
            s_no_accents = "".join(ch for ch in s_nfkd if not unicodedata.combining(ch))
            return s_no_accents.lower()

        product_lower = product_name.lower()
        product_norm = _normalize(product_name)

        search_terms: List[str] = []
        seen = set()  # déduplication en préservant l’ordre

        def _add(term: str):
            t = term.strip()
            if not t:
                return
            key = _normalize(t)
            if key not in seen:
                seen.add(key)
                search_terms.append(t)

        # Dictionnaire enrichi français/anglais avec filtrage intelligent
        translations = {
            "imprimante": ["printer", "Printer", "PRINTER", "laser printer", "inkjet printer"],
            "ordinateur": ["computer", "PC", "desktop", "workstation", "laptop"],
            "écran": ["monitor", "screen", "display", "LCD", "LED"],
            "clavier": ["keyboard", "Keys", "mechanical keyboard"],
            "souris": ["mouse", "optical mouse", "wireless mouse"],
            "scanner": ["scanner", "scan", "document scanner"],
            "laser": ["laser", "LaserJet", "laser printer"],
            "couleur": ["color", "colour", "couleur"],
            "noir": ["black", "monochrome", "mono"],
            "ppm": ["ppm", "pages per minute", "page/min"],
        }

        # Chercher correspondances exactes avec priorité sur les termes spécifiques
        for french_term, english_terms in translations.items():
            fr_norm = _normalize(french_term)
            if fr_norm in product_norm:
                # Ajouter les termes les plus spécifiques en premier (max 2)
                for t in english_terms[:2]:
                    _add(t)

        # Ajouter le terme original si pas encore ajouté
        _add(product_name)

        # Extraire caractéristiques numériques (PPM, etc.)
        numbers = re.findall(r"\d+", product_lower)
        for num in numbers:
            try:
                val = int(num)
            except ValueError:
                continue
            if 5 < val < 1000:  # Filtre raisonnable pour PPM/capacités
                _add(f"{num}ppm")
                _add(f"{num} ppm")
                _add(f"{num} pages")

        # Limiter à 6 termes maximum
        return search_terms[:6]

    
    def _get_english_search_terms(self, product_name: str) -> List[str]:
        """Génère des termes de recherche anglais pour SAP"""
        product_lower = product_name.lower()
        
        # Mapping français -> anglais pour SAP
        translations = {
            "imprimante": ["printer", "Printer", "PRINTER"],
            "ordinateur": ["computer", "Computer", "PC"],
            "écran": ["monitor", "Monitor", "screen"],
            "clavier": ["keyboard", "Keyboard"],
            "souris": ["mouse", "Mouse"],
            "scanner": ["scanner", "Scanner"]
        }
        
        search_terms = []
        for french_term, english_terms in translations.items():
            if french_term in product_lower:
                search_terms.extend(english_terms)
                break
        
        # Ajouter le terme original en dernier
        search_terms.append(product_name)
        
        return search_terms[:3]
    
    async def _process_products_retrieval(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Récupération des produits avec progression avancée
        """
        ACCESSORY_TERMS = ('cartouche', 'encre', 'toner', 'cable', 'câble')

        def _odata_escape(s: str) -> str:
            try:
                return str(s).replace("'", "''")
            except Exception:
                return str(s or "")

        try:
            if not products:
                return {
                    "status": "success",
                    "products": [],
                    "message": "Aucun produit à traiter"
                }

            self._track_step_progress("lookup_products", 10, f"🔍 Recherche de {len(products)} produit(s)...")

            found_products: List[Dict[str, Any]] = []
            products_needing_selection: List[Dict[str, Any]] = []
            total_products = len(products)

            for i, product in enumerate(products):
                product_name = str(product.get("name", "") or "")
                product_code = str(product.get("code", "") or "")
                try:
                    quantity = int(product.get("quantity", 1) or 1)
                except Exception:
                    quantity = 1
                if quantity < 1:
                    quantity = 1

                # Progression (sur i+1 pour une montée plus régulière)
                progress = int(20 + ((i + 1) / total_products) * 70)
                self._track_step_progress("lookup_products", progress, f"📦 Recherche '{product_name}' ({i+1}/{total_products})")

                # === RECHERCHE INTELLIGENTE ===
                try:
                    smart_search = await self._smart_product_search(product_name, product_code)
                    if not isinstance(smart_search, dict):
                        smart_search = {"found": False, "products": [], "method": "invalid_response"}
                    smart_search.setdefault("found", False)
                    smart_search.setdefault("products", [])
                    smart_search_method = smart_search.get("method")
                except Exception as e:
                    logger.error(f"❌ Erreur appel _smart_product_search: {str(e)}")
                    smart_search = {"found": False, "products": [], "method": "call_error", "error": str(e)}
                    smart_search_method = "call_error"

                if smart_search["found"] and smart_search["products"]:
                    products_found = smart_search.get("products") or []
                    if self._is_generic_search(product_name) and len(products_found) > 1:
                        logger.info(f"⚠️ Terme générique '{product_name}' avec {len(products_found)} options - Interaction requise")
                        products_needing_selection.append({
                            "original_name": product_name,
                            "original_code": product_code,
                            "quantity": quantity,
                            "options": products_found[:5],
                            "search_method": smart_search_method,
                            "selection_reason": f"Terme '{product_name}' trop générique - {len(products_found)} produits correspondent"
                        })
                        continue
                    # AJOUT: Arrêter le workflow immédiatement pour demander la sélection
                    if products_needing_selection:
                        logger.warning(f"⏸️ Arrêt workflow - {len(products_needing_selection)} produit(s) nécessitent sélection")
                        return {
                            "status": "product_selection_required",
                            "products": products_needing_selection,
                            "message": "Sélection de produits requise"
                        }
                    # Auto-sélection si 1 résultat, sinon on prend le 1er comme “best”
                    best_list = products_found[:1] if len(products_found) == 1 else products_found[:1]
                    if not best_list:
                        # garde défensive ultra rare
                        logger.debug("Aucun produit exploitable dans smart_search malgré found=True")
                    else:
                        best_match = best_list[0]
                        logger.info(f"✅ Produit auto-sélectionné: {best_match.get('ItemName')} - Code: {best_match.get('ItemCode')} - Quantité: {quantity}")
                        found_products.append({
                            **self._format_product_data(best_match, quantity),  # Passer la vraie quantité
                            "search_method": smart_search_method,
                            "found": True
                        })
                    continue

                # Recherche traditionnelle si recherche intelligente échoue
                product_found = False

                # Étape 1: Recherche exacte par code
                if product_code:
                    try:
                        exact_search = await self.mcp_connector.call_sap_mcp(
                            "sap_read",
                            {"endpoint": f"/Items('{_odata_escape(product_code)}')", "method": "GET"}
                        )
                        if isinstance(exact_search, dict) and "error" not in exact_search and exact_search.get("ItemCode"):
                            logger.info(f"✅ Produit trouvé par code exact: {product_code}")
                            found_products.append({
                                **self._format_product_data(exact_search, quantity),
                                "search_method": "exact_code",
                                "found": True
                            })
                            continue
                    except Exception as e:
                        logger.debug(f"Recherche par code exact échouée: {str(e)}")

                # Étape 2: Recherche par nom exact
                if product_name and not product_found:
                    try:
                        pn = _odata_escape(product_name)
                        name_search = await self.mcp_connector.call_sap_mcp(
                            "sap_read",
                            {"endpoint": f"/Items?$filter=ItemName eq '{pn}'&$top=1", "method": "GET"}
                        )
                        values = (name_search or {}).get("value") or []
                        if values:
                            logger.info(f"✅ Produit trouvé par nom exact: {product_name}")
                            found_products.append({
                                **self._format_product_data(values[0], quantity),
                                "search_method": "exact_name",
                                "found": True
                            })
                            continue
                    except Exception as e:
                        logger.debug(f"Recherche nom exact échouée: {str(e)}")

                # Étape 3: Recherches par mots-clés élargies
                if not product_found:
                    for keyword in self._extract_product_keywords(product_name):
                        if not keyword:
                            continue
                        kw = _odata_escape(keyword)
                        logger.info(f"🔎 Recherche avec mot-clé: '{keyword}'")

                        # Recherche filtrée (éviter accessoires)
                        try:
                            filter_query = (
                                f"contains(tolower(ItemName),tolower('{kw}')) "
                                f"and not contains(tolower(ItemName),'cartouche') "
                                f"and not contains(tolower(ItemName),'encre') "
                                f"and not contains(tolower(ItemName),'toner') "
                                f"and not contains(tolower(ItemName),'cable')"
                            )
                            result = await self.mcp_connector.call_sap_mcp(
                                "sap_read",
                                {"endpoint": f"/Items?$filter={filter_query}&$top=5", "method": "GET"}
                            )
                            values = (result or {}).get("value") or []
                            if not values:
                                # Fallback simple
                                result = await self.mcp_connector.call_sap_mcp(
                                    "sap_read",
                                    {"endpoint": f"/Items?$filter=contains(tolower(ItemName),tolower('{kw}'))&$top=5", "method": "GET"}
                                )
                                values = (result or {}).get("value") or []

                            if values:
                                best_match = None
                                for match in values:
                                    item_name_lower = (match.get('ItemName') or '').lower()
                                    if not any(acc in item_name_lower for acc in ACCESSORY_TERMS):
                                        best_match = match
                                        break
                                if not best_match:
                                    best_match = values[0]

                                logger.info(f"✅ Produit trouvé par mot-clé '{keyword}': {best_match.get('ItemName')}")
                                found_products.append({
                                    **self._format_product_data(best_match, quantity),
                                    "search_method": f"keyword_{keyword}",
                                    "found": True
                                })
                                product_found = True
                                break
                        except Exception as e:
                            logger.debug(f"Recherche '{keyword}' échouée: {str(e)}")
                            # on tente le tour suivant

                # Si aucun produit trouvé, utiliser le système de suggestions
                if not product_found:
                    logger.warning(f"❌ Produit non trouvé: {product_name or product_code}")
                    logger.info(f"🔍 Recherche de suggestions pour: {product_name or product_code}")
                    try:
                        all_products_result = await self.mcp_connector.call_sap_mcp(
                            "sap_read",
                            {"endpoint": "/Items?$select=ItemCode,ItemName,OnHand,Price&$top=500", "method": "GET"}
                        )
                        if isinstance(all_products_result, dict) and "error" not in all_products_result and "value" in all_products_result:
                            available_products = all_products_result["value"]
                            from services.suggestion_engine import SuggestionEngine
                            suggestion_engine = SuggestionEngine()
                            suggestion_result = await suggestion_engine.suggest_product(product_name or product_code, available_products)

                            if getattr(suggestion_result, "has_suggestions", False):
                                found_products.append({
                                    "code": product_code or f"UNKNOWN_{i}",
                                    "name": product_name or "Produit à identifier",
                                    "quantity": quantity,
                                    "unit_price": 0.0,
                                    "total_price": 0.0,
                                    "currency": "EUR",
                                    "sap_data": None,
                                    "found": False,
                                    "requires_selection": True,
                                    "suggestions": suggestion_result.to_dict(),
                                    "original_request": product_name or product_code
                                })
                                logger.info(f"✅ Suggestions trouvées pour: {product_name or product_code}")
                            else:
                                found_products.append({
                                    "code": product_code or f"UNKNOWN_{i}",
                                    "name": product_name or "Produit inconnu",
                                    "quantity": quantity,
                                    "error": f"Aucun produit similaire trouvé dans le catalogue pour '{product_name or product_code}'",
                                    "requires_manual_search": True,
                                    "original_request": product_name or product_code
                                })
                                logger.error(f"❌ Aucune suggestion trouvée pour: {product_name or product_code}")
                        else:
                            found_products.append({
                                "code": product_code or f"ERROR_{i}",
                                "name": product_name or "Produit inaccessible",
                                "quantity": quantity,
                                "error": "Impossible d'accéder au catalogue SAP pour trouver des alternatives",
                                "requires_manual_search": True,
                                "original_request": product_name or product_code
                            })
                    except Exception as e:
                        logger.error(f"Erreur lors de la recherche de suggestions: {str(e)}")
                        found_products.append({
                            "code": product_code or f"ERROR_{i}",
                            "name": product_name or "Erreur produit",
                            "quantity": quantity,
                            "error": f"Erreur technique lors de la recherche: {str(e)}",
                            "requires_manual_search": True,
                            "original_request": product_name or product_code
                        })

            # Finaliser la progression
            self._track_step_progress("lookup_products", 100, "✅ Recherche terminée")

            # Statistiques et validation
            found_count = sum(1 for p in found_products if p.get("found"))
            selection_count = len(products_needing_selection)
            suggestions_count = sum(1 for p in found_products if p.get("requires_selection"))
            errors_count = sum(1 for p in found_products if p.get("error"))

            logger.info(f"📊 Produits: {found_count}/{len(products)} trouvés, {selection_count + suggestions_count} nécessitent sélection, {errors_count} erreurs")

            if products_needing_selection or suggestions_count > 0 or errors_count > 0:
                logger.warning("⚠️ Sélection de produits requise - Interruption du workflow")
                all_products_needing_action = products_needing_selection + [p for p in found_products if p.get("requires_selection") or p.get("error")]
                return {
                    "status": "product_selection_required",
                    "message": f"{len(all_products_needing_action)} produit(s) nécessitent votre attention",
                    "products": all_products_needing_action,
                    "workflow_context": {
                        "client_info": self.context.get("client_info", {}),
                        "task_id": self.task_id,
                        "step": "product_selection"
                    },
                    "requires_user_action": True
                }

            total_amount = sum(p.get("total_price", 0) for p in found_products if p.get("found"))
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

    def _format_product_data(self, sap_product: Dict[str, Any], quantity: int) -> Dict[str, Any]:
        """Formate les données produit SAP en format standard - CORRECTION: Préserver quantité exacte"""
        unit_price = float(sap_product.get("Price") or sap_product.get("AvgPrice", 0))
        if unit_price == 0:
            unit_price = self._estimate_product_price(sap_product.get("ItemName", ""))

        return {
            "code": sap_product.get("ItemCode", ""),
            "name": sap_product.get("ItemName", ""),
            "quantity": quantity,  # CRITIQUE: Utiliser la quantité passée en paramètre
            "unit_price": unit_price,
            "total_price": unit_price * quantity,  # Calculer avec la vraie quantité
            "currency": "EUR",
            "stock": int(sap_product.get("OnHand", 0)),
            "description": sap_product.get("U_Description", ""),
            "sap_data": sap_product,
            "Price": unit_price
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

    
    async def _sync_quote_to_systems(self, quote_result: Dict, target: str = None) -> Dict[str, Any]:
        """
        Synchronisation du devis vers SAP - VERSION PRODUCTION COMPLÈTE

        Args:
            quote_result: Résultat contenant les données de devis consolidées
            target: Système cible ('sap') ou None

        Returns:
            Dict avec statut de synchronisation détaillé
        """
        try:
            # === VALIDATIONS INITIALES ===
            quote_data = quote_result.get("quote_data", {})
            
            # Validation du paramètre target
            if target and target not in ("sap",):
                logger.error(f"❌ Target invalide: {target}")
                return {
                    "status": "error",
                    "message": f"Target '{target}' non supporté. Utilisez 'sap'"
                }
            
            # Validation des données de devis
            if not quote_data:
                logger.error("❌ Aucune donnée de devis à synchroniser")
                return {
                    "status": "error",
                    "message": "Pas de données de devis à synchroniser"
                }
            
            quote_id = quote_data.get("quote_id")
            if not quote_id:
                logger.error("❌ Quote ID manquant")
                return {
                    "status": "error", 
                    "message": "Quote ID manquant dans les données"
                }
            
            # === FLAG PRODUCTION CENTRALISÉ ===
            NOVA_MODE = os.getenv("NOVA_MODE", "draft")
            is_production_mode = NOVA_MODE == "production"
            
            if is_production_mode:
                logger.info(f"🚀 MODE PRODUCTION - Synchronisation réelle du devis {quote_id}")
            else:
                logger.info(f"🎯 MODE DRAFT - Simulation synchronisation du devis {quote_id}")
            
            # === EXTRACTION ET VALIDATION DES DONNÉES ===
            client_data = quote_data.get("client", {})
            products_data = quote_data.get("products", [])
            
            # Validation données client
            if not client_data:
                logger.error("❌ Données client manquantes")
                return {
                    "status": "error",
                    "message": "Données client manquantes pour la synchronisation"
                }
            # CardCode minimal pour SAP si SAP demandé
            if (not target or target == "sap") and not (client_data.get("CardCode") or client_data.get("sap_code")):
                logger.error("❌ Code client SAP manquant (CardCode/sap_code)")
                return {
                    "status": "error",
                    "message": "Code client SAP manquant (CardCode/sap_code)"
                }
                
            # Validation données produits
            if not products_data:
                logger.error("❌ Aucun produit à synchroniser")
                return {
                    "status": "error", 
                    "message": "Aucun produit à synchroniser"
                }

            # Normalisation utilitaires internes (sans toucher à l’API externe)
            def _to_number(v, default=0.0):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return float(default)

            def _to_qty(v, default=1):
                try:
                    q = int(float(v))
                    return q if q > 0 else default
                except (TypeError, ValueError):
                    return default
            
            now = datetime.now()
            close_date_str = (now + timedelta(days=30)).strftime("%Y-%m-%d")
            doc_date_str = now.strftime("%Y-%m-%d")

            # Validation des prix produits + total calculé
            total_amount_validation = 0.0
            for product in products_data:
                price = _to_number(product.get("UnitPrice", product.get("price", 0)), 0.0)
                quantity = _to_qty(product.get("Quantity", product.get("quantity", 1)), 1)
                if price <= 0:
                    logger.warning(f"⚠️ Produit {product.get('ItemCode') or product.get('code') or 'UNKNOWN'} sans prix valide: {price}")
                total_amount_validation += price * quantity
            
            if total_amount_validation <= 0:
                logger.error(f"❌ Montant total invalide: {total_amount_validation}")
                return {
                    "status": "error",
                    "message": f"Montant total invalide: {total_amount_validation}€"
                }
            
            # === INITIALISATION DES RÉSULTATS ===
            sync_results = {
                "sap_sync": {
                    "attempted": False,
                    "success": False,
                    "message": "Non tenté",
                    "quote_sap_id": None,
                    "doc_entry": None
                }
            }
            
            # === SYNCHRONISATION SAP ===
            if not target or target == "sap":
                sync_results["sap_sync"]["attempted"] = True
                logger.info(f"📡 Début synchronisation SAP pour {quote_id}")
                
                # Préparation structure SAP quotation_data
                sap_quotation_data = {
                    "CardCode": client_data.get("CardCode") or client_data.get("sap_code"),
                    "CardName": client_data.get("CardName") or client_data.get("name"),
                    "DocDate": doc_date_str,
                    "DocDueDate": close_date_str,
                    "Comments": f"Devis généré automatiquement NOVA - {quote_id}",
                    "DocumentLines": []
                }
                
                # Construction des lignes de devis SAP
                for product in products_data:
                    item_code = product.get("ItemCode") or product.get("code")
                    unit_price = _to_number(product.get("UnitPrice", product.get("price", 0)), 0.0)
                    quantity = _to_qty(product.get("Quantity", product.get("quantity", 1)), 1)
                    
                    if not item_code:
                        logger.warning(f"⚠️ Produit sans ItemCode ignoré: {product}")
                        continue
                        
                    line_data = {
                        "ItemCode": item_code,
                        "Quantity": quantity,
                        "UnitPrice": unit_price,
                        "LineTotal": unit_price * quantity,
                        "WarehouseCode": product.get("WarehouseCode", "01"),  # Entrepôt par défaut
                        "VatGroup": product.get("VatGroup", "FR_VAT_20")      # TVA par défaut France
                    }
                    sap_quotation_data["DocumentLines"].append(line_data)
                
                # Validation finale des lignes SAP
                if not sap_quotation_data["DocumentLines"]:
                    sync_results["sap_sync"]["message"] = "Aucune ligne valide pour SAP"
                    logger.error("❌ Aucune ligne valide pour le devis SAP")
                else:
                    # === APPEL SAP RÉEL OU SIMULATION ===
                    if is_production_mode:
                        logger.info(f"📡 Appel SAP RÉEL sap_create_quotation_complete")
                        sap_results = await self.mcp_connector.sap_create_quotation_complete(sap_quotation_data)
                        
                        if sap_results.get("success"):
                            sync_results["sap_sync"]["success"] = True
                            sync_results["sap_sync"]["message"] = "Devis SAP créé avec succès"
                            sync_results["sap_sync"]["quote_sap_id"] = sap_results.get("DocNum")
                            sync_results["sap_sync"]["doc_entry"] = sap_results.get("DocEntry")
                            logger.info(f"✅ Devis SAP créé: DocNum={sap_results.get('DocNum')}")
                        else:
                            sync_results["sap_sync"]["message"] = sap_results.get("error", "Erreur SAP inconnue")
                            logger.error(f"❌ Erreur création devis SAP: {sync_results['sap_sync']['message']}")
                    else:
                        # MODE DRAFT - Simulation réaliste
                        await asyncio.sleep(0.8)  # Simulation latence SAP
                        sync_results["sap_sync"]["success"] = True
                        sync_results["sap_sync"]["message"] = "Simulation SAP réussie (mode draft)"
                        sync_results["sap_sync"]["quote_sap_id"] = f"DRAFT_SAP_{quote_id}"
                        sync_results["sap_sync"]["doc_entry"] = f"ENTRY_DRAFT_{quote_id}"
                        logger.info(f"🎯 Simulation SAP terminée pour {quote_id}")
            
            # === DÉTERMINATION DU STATUT GLOBAL (SAP uniquement) ===
            sap_success = sync_results["sap_sync"]["success"]
            sap_attempted = sync_results["sap_sync"]["attempted"]

            if sap_success:
                status = "success"
                message = f"Synchronisation SAP réussie pour {quote_id}"
            else:
                status = "error"
                message = f"Échec synchronisation SAP pour {quote_id}: {sync_results['sap_sync']['message']}"

            # === LOG DE SYNTHÈSE ===
            mode_display = "PRODUCTION" if is_production_mode else "DRAFT"
            logger.info(f"✅ Synchronisation {mode_display} terminée - Statut: {status}")

            if sap_attempted:
                sap_status = "✅" if sap_success else "❌"
                logger.info(f"{sap_status} SAP: {sync_results['sap_sync']['message']}")
            
            # === CONSTRUCTION DE LA RÉPONSE FINALE ===
            response = {
                "status": status,
                "sync_results": sync_results,
                "message": message,
                "quote_id": quote_id,
                "mode": "production" if is_production_mode else "draft",
                "target_filter": target,
                "timestamp": datetime.now().isoformat(),
                "total_amount": total_amount_validation
            }
            
            if sap_success:
                response["sap_quote_number"] = sync_results["sap_sync"]["quote_sap_id"]
                response["sap_doc_entry"] = sync_results["sap_sync"]["doc_entry"]

            return response
            
        except Exception as e:
            logger.exception(f"❌ Exception critique dans _sync_quote_to_systems: {str(e)}")
            # sécurise l'accès à quote_id même si l'exception survient très tôt
            _qd = locals().get("quote_data", {}) or {}
            return {
                "status": "error",
                "message": f"Erreur système lors de la synchronisation: {str(e)}",
                "quote_id": _qd.get("quote_id", "UNKNOWN"),
                "timestamp": datetime.now().isoformat(),
                "exception_type": type(e).__name__
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
    async def _notify_websocket(self, event_type: str, data: dict):
        """Notification WebSocket"""
        if self.task_id:
            await self.websocket_manager.send_task_update(self.task_id, {
                "event": event_type,
                "data": data
            })

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
            result = await self.mcp_connector.call_sap_mcp(
                "sap_create_customer_complete",
                {"customer_data": sap_client_data}
            )

            if not result.get("success", False):
                logger.error(f"❌ Échec création SAP: {result.get('error')}")
                return {
                    "created": False,
                    "error": f"Erreur SAP: {result.get('error', 'Erreur inconnue')}"
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
        """Recherche produit SAP avec fallback intelligent"""
        try:
            logger.info(f"🔍 Recherche SAP: code='{product_code}', nom='{product_name}'")
            
            # 1. Recherche par code exact si disponible
            if product_code and product_code != "":
                try:
                    code_result = await self.mcp_connector.call_mcp(
                        "sap_mcp",
                        "sap_read",
                        {"endpoint": f"/Items('{product_code}')"}
                    )
                    
                    if not code_result.get("error") and code_result.get("ItemCode"):
                        logger.info(f"✅ Produit trouvé par code: {product_code}")
                        return {
                            "found": True,
                            "data": code_result,
                            "search_method": "code"
                        }
                except Exception as e:
                    logger.warning(f"⚠️ Erreur recherche par code {product_code}: {e}")
            
            # 2. Recherche par nom avec mots-clés intelligents
            # Protection contre boucle infinie
                search_timeout = asyncio.create_task(asyncio.sleep(30))  # 30 secondes max
                keyword_attempts = 0
                max_keyword_attempts = 3
            if product_name:
                keywords = self._extract_product_keywords(product_name)
                
                for keyword in keywords[:2]:  # Tester 2 mots-clés max
                    # Vérifier limite d'essais et timeout
                    if keyword_attempts >= max_keyword_attempts:
                        logger.warning(f"⏰ Limite d'essais atteinte pour '{product_name}'")
                        break
                    
                    keyword_attempts += 1
                    try:
                        logger.info(f"🔍 Recherche avec mot-clé: '{keyword}'")
                        
                        search_result = await self.mcp_connector.call_mcp(
                            "sap_mcp",
                            "sap_search",
                            {
                                "query": keyword,
                                "entity_type": "Items",
                                "limit": 5
                            }
                        )
                        
                        if search_result and search_result.get("success") and search_result.get("results"):
                            best_match = search_result["results"][0]
                            logger.info(f"✅ Produit trouvé via '{keyword}': {best_match.get('ItemName')} ({best_match.get('ItemCode')})")
                            
                            return {
                                "found": True,
                                "data": {
                                    "ItemCode": best_match.get("ItemCode"),
                                    "ItemName": best_match.get("ItemName"),
                                    "OnHand": best_match.get("OnHand", 0),
                                    "AvgPrice": best_match.get("AvgPrice", 0),
                                    "U_Description": best_match.get("U_Description", "")
                                },
                                "search_method": f"keyword_{keyword}",
                                "matched_keyword": keyword
                            }
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur recherche mot-clé '{keyword}': {e}")
                        continue
            
            # 3. Recherche avec termes anglais
            if product_name:
                english_terms = self._get_english_search_terms(product_name)
                
                for term in english_terms[:2]:
                    try:
                        logger.info(f"🔍 Recherche terme anglais: '{term}'")
                        
                        alt_result = await self.mcp_connector.call_mcp(
                            "sap_mcp",
                            "sap_search",
                            {
                                "query": term,
                                "entity_type": "Items", 
                                "limit": 3
                            }
                        )
                        
                        if alt_result and alt_result.get("success") and alt_result.get("results"):
                            best_match = alt_result["results"][0]
                            logger.info(f"✅ Produit trouvé via terme '{term}': {best_match.get('ItemName')}")
                            
                            return {
                                "found": True,
                                "data": {
                                    "ItemCode": best_match.get("ItemCode"),
                                    "ItemName": best_match.get("ItemName"),
                                    "OnHand": best_match.get("OnHand", 0),
                                    "AvgPrice": best_match.get("AvgPrice", 0),
                                    "U_Description": best_match.get("U_Description", "")
                                },
                                "search_method": f"english_{term}",
                                "matched_term": term
                            }
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur recherche terme '{term}': {e}")
                        continue
            
            # 4. Recherche générale sur tous les items
            try:
                logger.info("🔍 Recherche générale dans Items...")
                all_items = await self.mcp_connector.call_mcp(
                    "sap_mcp",
                    "sap_read",
                    {"endpoint": "/Items?$top=50&$orderby=ItemCode"}
                )
                
                if all_items and not all_items.get("error") and all_items.get("value"):
                    items = all_items["value"]
                    logger.info(f"📦 {len(items)} produits disponibles dans SAP")
                    
                    # Chercher correspondance dans les noms
                    for item in items:
                        item_name = item.get("ItemName", "").lower()
                        if any(keyword.lower() in item_name for keyword in self._extract_product_keywords(product_name)):
                            logger.info(f"✅ Correspondance trouvée: {item.get('ItemName')}")
                            return {
                                "found": True,
                                "data": item,
                                "search_method": "general_scan"
                            }
            except Exception as e:
                logger.warning(f"⚠️ Erreur recherche générale: {e}")
            
            # Aucune correspondance trouvée
            logger.warning(f"❌ Aucun produit SAP trouvé pour: code='{product_code}', nom='{product_name}'")
            return {
                "found": False,
                "error": f"Produit non trouvé: {product_name or product_code}"
            }
            
        except Exception as e:
            logger.exception(f"❌ Exception recherche produit: {str(e)}")
            return {
                "found": False,
                "error": f"Erreur système: {str(e)}"
            }
    
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
            sap_results = await self._search_sap_product(product.get("code", ""), product_name)
            
            if sap_results.get("found"):
                await self._notify_websocket("product_found", {
                    "product_index": i,
                    "product_data": sap_results["data"],
                    "message": f"Produit '{product_name}' trouvé"
                })
                results.append({"index": i, "found": True, "data": sap_results["data"]})
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
__all__ = ['DevisWorkflow']