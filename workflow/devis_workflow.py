# workflow/devis_workflow_refactored.py - VERSION REFACTORISÉE AVEC ARCHITECTURE MODULAIRE

import re
import sys
import io
import os
import json
import logging
import asyncio
from fastapi import APIRouter, HTTPException
from services.progress_tracker import TaskStatus
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


class WorkflowState:
    """Gestionnaire d'état centralisé pour le workflow"""

    def __init__(self, task_id: str = None):
        self.task_id = task_id
        self.context = {}
        self.extracted_info = {}
        self.client_info = {}
        self.products_info = []
        self.validation_results = {}
        self.current_step = None
        self.errors = []

    def update_context(self, key: str, value: Any):
        """Met à jour le contexte de manière sécurisée"""
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur du contexte"""
        return self.context.get(key, default)

    def save_to_task(self, task_manager):
        """Sauvegarde l'état dans la tâche"""
        if self.task_id and task_manager:
            task = task_manager.get_task(self.task_id)
            if task:
                if not hasattr(task, 'context'):
                    task.context = {}
                task.context.update(self.context)
                logger.info(f"💾 État sauvegardé pour tâche {self.task_id}")


class ClientManager:
    """Gestionnaire spécialisé pour les opérations client"""

    def __init__(self, mcp_connector: MCPConnector, client_validator=None):
        self.mcp_connector = mcp_connector
        self.client_validator = client_validator

    async def validate_client(self, client_name: str) -> Dict[str, Any]:
        """Valide et recherche un client"""
        if not client_name or not client_name.strip():
            return {"found": False, "error": "Nom de client manquant"}

        try:
            # Recherche dans les systèmes
            client_info = await find_client_everywhere(client_name)

            if client_info.get("found"):
                return self._normalize_client_info(client_info)

            # Recherche de suggestions si non trouvé
            suggestions = await self._find_client_suggestions(client_name)
            if suggestions:
                return {
                    "found": False,
                    "suggestions": suggestions,
                    "message": f"Suggestions disponibles pour '{client_name}'"
                }

            return {"found": False, "error": f"Client '{client_name}' non trouvé"}

        except Exception as e:
            logger.exception(f"Erreur validation client {client_name}: {e}")
            return {"found": False, "error": str(e)}

    async def _find_client_suggestions(self, client_name: str) -> List[Dict]:
        """Trouve des suggestions de clients similaires"""
        try:
            # Recherche floue dans Salesforce
            query = f"""
            SELECT Id, Name, AccountNumber, Phone, BillingCity 
            FROM Account 
            WHERE Name LIKE '%{client_name[:10]}%' 
            LIMIT 5
            """
            result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": query})

            if result.get("success") and result.get("data"):
                suggestions = []
                for record in result["data"]:
                    similarity = self._calculate_similarity(client_name, record.get("Name", ""))
                    if similarity > 0.6:  # Seuil de similarité
                        suggestions.append({
                            "id": record.get("Id"),
                            "name": record.get("Name"),
                            "account_number": record.get("AccountNumber"),
                            "similarity": similarity
                        })
                return sorted(suggestions, key=lambda x: x["similarity"], reverse=True)

        except Exception as e:
            logger.warning(f"Erreur recherche suggestions: {e}")

        return []

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calcule la similarité entre deux noms"""
        try:
            return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
        except:
            return 0.0

    def _normalize_client_info(self, client_info: Any) -> Dict[str, Any]:
        """Normalise les informations client"""
        if not client_info:
            return {"data": {}, "found": False}

        if not isinstance(client_info, dict):
            return {"data": {}, "found": False}

        if "data" not in client_info:
            client_info["data"] = {}
        elif client_info["data"] is None:
            client_info["data"] = {}
        elif not isinstance(client_info["data"], dict):
            client_info["data"] = {}

        return client_info

    async def create_client(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un nouveau client dans les systèmes"""
        try:
            # Créer d'abord dans Salesforce
            sf_result = await self._create_salesforce_client(client_data)
            if not sf_result.get("success"):
                return sf_result

            # Puis dans SAP
            sap_result = await self._create_sap_client(client_data, sf_result)

            return {
                "success": True,
                "salesforce": sf_result,
                "sap": sap_result,
                "client_data": sf_result.get("data", {})
            }

        except Exception as e:
            logger.exception(f"Erreur création client: {e}")
            return {"success": False, "error": str(e)}

    async def _create_salesforce_client(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un client dans Salesforce"""
        try:
            sf_data = {
                "Name": client_data.get("company_name", ""),
                "Type": "Customer",
                "Description": "Client créé automatiquement via NOVA"
            }

            result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_create_record", {
                "sobject": "Account",
                "data": sf_data
            })

            if result.get("success"):
                return {"success": True, "id": result["id"], "data": sf_data}
            else:
                return {"success": False, "error": result.get("error")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _create_sap_client(self, client_data: Dict[str, Any], sf_result: Dict[str, Any]) -> Dict[str, Any]:
        """Crée un client dans SAP"""
        try:
            # Générer un CardCode unique
            import time
            clean_name = re.sub(r'[^a-zA-Z0-9]', '', client_data.get("company_name", ""))[:8]
            timestamp = str(int(time.time()))[-4:]
            card_code = f"C{clean_name}{timestamp}".upper()[:15]

            sap_data = {
                "CardCode": card_code,
                "CardName": client_data.get("company_name", ""),
                "CardType": "cCustomer",
                "GroupCode": 100,
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO",
                "Notes": "Client créé automatiquement via NOVA",
                "FederalTaxID": sf_result.get("id", "")[:32]
            }

            result = await self.mcp_connector.call_mcp("sap_mcp", "sap_create_customer_complete", {
                "customer_data": sap_data
            })

            if result.get("success"):
                return {"success": True, "card_code": card_code, "data": sap_data}
            else:
                return {"success": False, "error": result.get("error")}

        except Exception as e:
            return {"success": False, "error": str(e)}


class ProductManager:
    """Gestionnaire spécialisé pour les opérations produits"""

    def __init__(self, mcp_connector: MCPConnector, suggestion_engine: SuggestionEngine):
        self.mcp_connector = mcp_connector
        self.suggestion_engine = suggestion_engine

    async def validate_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Valide une liste de produits avec suggestions"""
        validated_products = []

        for product in products:
            product_code = product.get("code", product.get("name", "")).strip()
            quantity = float(product.get("quantity", 1))

            if not product_code:
                validated_products.append({
                    "found": False,
                    "error": "Code produit manquant",
                    "quantity": quantity
                })
                continue

            # Recherche directe
            product_data = await self._find_product_direct(product_code)
            if product_data:
                validated_products.append({
                    "found": True,
                    "data": product_data,
                    "quantity": quantity
                })
                continue

            # Recherche avec suggestions
            suggestions = await self._find_product_suggestions(product_code)
            if suggestions:
                validated_products.append({
                    "found": False,
                    "original_code": product_code,
                    "quantity": quantity,
                    "suggestions": suggestions
                })
            else:
                validated_products.append({
                    "found": False,
                    "original_code": product_code,
                    "quantity": quantity,
                    "error": f"Produit '{product_code}' non trouvé"
                })

        return validated_products

    async def _find_product_direct(self, product_code: str) -> Optional[Dict[str, Any]]:
        """Recherche directe d'un produit"""
        try:
            result = await self.mcp_connector.call_mcp("sap_mcp", "sap_get_product_details", {
                "item_code": product_code
            })

            if result.get("success") and result.get("ItemCode"):
                return result

        except Exception as e:
            logger.warning(f"Erreur recherche produit {product_code}: {e}")

        return None

    async def _find_product_suggestions(self, product_code: str) -> List[Dict[str, Any]]:
        """Trouve des suggestions de produits similaires"""
        try:
            # Récupérer tous les produits pour la recherche floue
            all_products_result = await self.mcp_connector.call_mcp("sap_mcp", "get_all_items", {"limit": 1000})
            available_products = all_products_result.get("data", []) if all_products_result.get("success") else []

            # Générer les suggestions
            product_suggestion = await self.suggestion_engine.suggest_product(product_code, available_products)

            if product_suggestion.has_suggestions:
                return [
                    {
                        "code": suggestion.suggested_value,
                        "name": suggestion.metadata.get("ItemName", ""),
                        "confidence": suggestion.confidence.value,
                        "score": suggestion.score
                    }
                    for suggestion in product_suggestion.all_suggestions
                ]

        except Exception as e:
            logger.warning(f"Erreur recherche suggestions produit: {e}")

        return []


class QuoteManager:
    """Gestionnaire spécialisé pour les opérations de devis"""

    def __init__(self, mcp_connector: MCPConnector, price_engine: PriceEngineService):
        self.mcp_connector = mcp_connector
        self.price_engine = price_engine

    async def create_quote(self, client_data: Dict[str, Any], products_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Crée un devis complet dans SAP et Salesforce"""
        try:
            # Calculer les prix
            pricing_result = await self.price_engine.calculate_quote_pricing({
                "client_data": client_data,
                "products": products_data,
                "special_conditions": {}
            })

            updated_products = pricing_result.get("updated_products", products_data)
            total_amount = pricing_result.get("total_amount", 0)

            # Créer dans SAP
            sap_result = await self._create_sap_quote(client_data, updated_products, total_amount)
            if not sap_result.get("success"):
                return sap_result

            # Créer dans Salesforce
            sf_result = await self._create_salesforce_opportunity(client_data, updated_products, sap_result)

            return {
                "success": True,
                "quote_id": sap_result.get("quote_number"),
                "sap_result": sap_result,
                "salesforce_result": sf_result,
                "total_amount": total_amount,
                "products": updated_products
            }

        except Exception as e:
            logger.exception(f"Erreur création devis: {e}")
            return {"success": False, "error": str(e)}

    async def _create_sap_quote(self, client_data: Dict[str, Any], products_data: List[Dict[str, Any]], total_amount: float) -> Dict[str, Any]:
        """Crée un devis dans SAP"""
        try:
            # Préparer les lignes de devis
            document_lines = []
            for i, product in enumerate(products_data):
                if product.get("found", True) and not product.get("error"):
                    document_lines.append({
                        "LineNum": i,
                        "ItemCode": product.get("code", product.get("ItemCode", "")),
                        "ItemDescription": product.get("name", product.get("ItemName", "")),
                        "Quantity": float(product.get("quantity", 1)),
                        "Price": float(product.get("unit_price", product.get("Price", 0)))
                    })

            # Données du devis SAP
            quote_data = {
                "CardCode": self._get_client_sap_code(client_data),
                "DocDate": datetime.now().strftime("%Y-%m-%d"),
                "DocDueDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "Comments": "Devis créé automatiquement via NOVA",
                "DocumentLines": document_lines
            }

            result = await self.mcp_connector.call_mcp("sap_mcp", "sap_create_quotation", quote_data)

            if result.get("success"):
                return {
                    "success": True,
                    "quote_number": result.get("DocNum"),
                    "doc_entry": result.get("DocEntry"),
                    "data": result
                }
            else:
                return {"success": False, "error": result.get("error")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _create_salesforce_opportunity(self, client_data: Dict[str, Any], products_data: List[Dict[str, Any]], sap_result: Dict[str, Any]) -> Dict[str, Any]:
        """Crée une opportunité dans Salesforce"""
        try:
            # Calculer le montant total
            total_amount = sum(
                float(p.get("quantity", 1)) * float(p.get("unit_price", p.get("Price", 0)))
                for p in products_data
                if p.get("found", True) and not p.get("error")
            )

            opportunity_data = {
                "Name": f"Devis {sap_result.get('quote_number', 'AUTO')} - {client_data.get('Name', 'Client')}",
                "AccountId": client_data.get("Id"),
                "StageName": "Prospecting",
                "CloseDate": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "Amount": total_amount,
                "Description": f"Devis SAP #{sap_result.get('quote_number')} créé automatiquement via NOVA"
            }

            result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_create_record", {
                "sobject": "Opportunity",
                "data": opportunity_data
            })

            if result.get("success"):
                return {"success": True, "opportunity_id": result["id"]}
            else:
                return {"success": False, "error": result.get("error")}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_client_sap_code(self, client_data: Dict[str, Any]) -> str:
        """Récupère le code SAP du client"""
        # Logique pour récupérer le CardCode SAP
        return client_data.get("CardCode", client_data.get("AccountNumber", "DEFAULT"))

    async def check_duplicate_quotes(self, client_info: Dict[str, Any], products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Vérifie les doublons de devis"""
        try:
            client_id = client_info.get("data", {}).get("Id")
            if not client_id:
                return {"has_duplicates": False}

            # Rechercher les devis récents
            recent_quotes = await self._find_recent_quotes(client_id)
            similar_quotes = await self._find_similar_quotes(client_id, products)

            total_duplicates = len(recent_quotes) + len(similar_quotes)

            if total_duplicates > 0:
                return {
                    "has_duplicates": True,
                    "requires_user_decision": True,
                    "recent_quotes": recent_quotes,
                    "similar_quotes": similar_quotes,
                    "alert_message": f"{total_duplicates} devis existant(s) détecté(s)"
                }
            else:
                return {"has_duplicates": False}

        except Exception as e:
            logger.warning(f"Erreur vérification doublons: {e}")
            return {"has_duplicates": False, "error": str(e)}

    async def _find_recent_quotes(self, client_id: str) -> List[Dict[str, Any]]:
        """Trouve les devis récents pour un client"""
        try:
            # Recherche dans Salesforce
            query = f"""
            SELECT Id, Name, Amount, CreatedDate, StageName
            FROM Opportunity 
            WHERE AccountId = '{client_id}' 
            AND CreatedDate = LAST_N_DAYS:30
            ORDER BY CreatedDate DESC
            LIMIT 10
            """

            result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {"query": query})

            if result.get("success") and result.get("data"):
                return result["data"]

        except Exception as e:
            logger.warning(f"Erreur recherche devis récents: {e}")

        return []

    async def _find_similar_quotes(self, client_id: str, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trouve les devis similaires basés sur les produits"""
        # Implémentation simplifiée - à améliorer selon les besoins
        return []


class ValidationEngine:
    """Moteur de validation centralisé"""

    def __init__(self, mcp_connector: MCPConnector):
        self.mcp_connector = mcp_connector

    async def validate_quote_data(self, client_data: Dict[str, Any], products_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Valide les données complètes du devis"""
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        # Validation client
        client_validation = self._validate_client_data(client_data)
        if not client_validation["valid"]:
            validation_results["valid"] = False
            validation_results["errors"].extend(client_validation["errors"])
        validation_results["warnings"].extend(client_validation.get("warnings", []))

        # Validation produits
        products_validation = self._validate_products_data(products_data)
        if not products_validation["valid"]:
            validation_results["valid"] = False
            validation_results["errors"].extend(products_validation["errors"])
        validation_results["warnings"].extend(products_validation.get("warnings", []))

        return validation_results

    def _validate_client_data(self, client_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valide les données client"""
        errors = []
        warnings = []

        if not client_data.get("Name"):
            errors.append("Nom du client manquant")

        if not client_data.get("Id"):
            warnings.append("ID Salesforce manquant")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _validate_products_data(self, products_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Valide les données produits"""
        errors = []
        warnings = []

        if not products_data:
            errors.append("Aucun produit spécifié")
            return {"valid": False, "errors": errors, "warnings": warnings}

        for i, product in enumerate(products_data):
            if product.get("error"):
                errors.append(f"Produit {i+1}: {product['error']}")
            elif not product.get("found", True):
                warnings.append(f"Produit {i+1} non trouvé dans le catalogue")

            quantity = product.get("quantity", 0)
            if quantity <= 0:
                errors.append(f"Produit {i+1}: quantité invalide ({quantity})")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


class DevisWorkflowRefactored:
    """Workflow de devis refactorisé avec architecture modulaire"""

    def __init__(self, validation_enabled: bool = True, draft_mode: bool = False, force_production: bool = True, task_id: str = None):
        """
        Initialise le workflow avec les gestionnaires spécialisés

        Args:
            validation_enabled: Active la validation des données
            draft_mode: Mode brouillon (True) ou normal (False)
            force_production: Force le mode production même si connexions échouent
            task_id: ID de tâche existant pour récupérer une tâche en cours
        """
        # Configuration de base
        self.validation_enabled = validation_enabled
        self.draft_mode = draft_mode
        self.force_production = force_production
        self.task_id = task_id

        # Initialisation des composants principaux
        self.mcp_connector = MCPConnector()
        self.llm_extractor = LLMExtractor()

        # Gestionnaire d'état centralisé
        self.state = WorkflowState(task_id)

        # Gestionnaires spécialisés
        client_validator = ClientValidator() if validation_enabled and VALIDATOR_AVAILABLE else None
        self.client_manager = ClientManager(self.mcp_connector, client_validator)

        suggestion_engine = SuggestionEngine()
        self.product_manager = ProductManager(self.mcp_connector, suggestion_engine)

        price_engine = PriceEngineService()
        self.quote_manager = QuoteManager(self.mcp_connector, price_engine)

        # Moteur de validation
        self.validation_engine = ValidationEngine(self.mcp_connector)

        # Services additionnels
        self.websocket_manager = websocket_manager
        self.cache_manager = referential_cache

        # Gestion de la tâche
        self.current_task = None
        if task_id:
            self._initialize_existing_task(task_id)

        logger.info("✅ Workflow refactorisé initialisé avec architecture modulaire")

    def _initialize_existing_task(self, task_id: str):
        """Initialise une tâche existante"""
        try:
            self.current_task = progress_tracker.get_task(task_id)
            if self.current_task:
                logger.info(f"✅ Tâche récupérée: {task_id}")
                # Restaurer le contexte si disponible
                if hasattr(self.current_task, 'context') and self.current_task.context:
                    self.state.context.update(self.current_task.context)
                    logger.info(f"✅ Contexte restauré: {list(self.state.context.keys())}")
            else:
                logger.warning(f"⚠️ Tâche {task_id} introuvable")

        except Exception as e:
            logger.error(f"Erreur initialisation tâche {task_id}: {e}")
            self.current_task = None

    async def process_quote_request(self, user_prompt: str, draft_mode: bool = False) -> Dict[str, Any]:
        """
        Méthode principale pour traiter une demande de devis

        Args:
            user_prompt: Demande en langage naturel
            draft_mode: Mode brouillon si True

        Returns:
            Résultat du traitement avec statut et données
        """
        try:
            # Configuration du mode
            if draft_mode:
                self.draft_mode = draft_mode

            # Initialiser le tracking si nécessaire
            if not self.current_task:
                self.task_id = self._initialize_task_tracking(user_prompt)

            logger.info(f"=== DÉMARRAGE WORKFLOW REFACTORISÉ - Tâche {self.task_id} ===")

            # Phase 1: Extraction des informations
            self._track_step_complete("extract_entities", "✅ Demande analysée")
            extracted_info = await self.llm_extractor.extract_quote_info(user_prompt)

            if not extracted_info:
                return self._build_error_response("Extraction échouée", "Impossible d'analyser votre demande")

            self.state.extracted_info = extracted_info
            self.state.save_to_task(progress_tracker)
            self._track_step_complete("extract_info", "✅ Demande analysée")

            # Phase 2: Validation du client
            self._track_step_start("search_client", "👤 Validation du client")
            client_result = await self._process_client_validation(extracted_info.get("client"))

            if client_result.get("status") == "user_interaction_required":
                return client_result

            if not client_result.get("success"):
                return self._build_error_response("Validation client échouée", client_result.get("error"))

            self.state.client_info = client_result.get("client_info", {})
            self._track_step_complete("search_client", "✅ Client validé")

            # Phase 3: Validation des produits
            self._track_step_start("validate_products", "📦 Validation des produits")
            products_result = await self._process_products_validation(extracted_info.get("products", []))

            if products_result.get("status") == "user_interaction_required":
                return products_result

            if not products_result.get("success"):
                return self._build_error_response("Validation produits échouée", products_result.get("error"))

            self.state.products_info = products_result.get("products", [])
            self._track_step_complete("validate_products", "✅ Produits validés")

            # Phase 4: Vérification des doublons
            self._track_step_start("check_duplicates", "🔍 Vérification des doublons")
            duplicate_result = await self._check_duplicate_quotes()

            if duplicate_result.get("requires_user_decision"):
                return {
                    "status": "user_interaction_required",
                    "interaction_type": "duplicate_resolution",
                    "message": duplicate_result.get("alert_message"),
                    "duplicate_data": duplicate_result
                }

            self._track_step_complete("check_duplicates", "✅ Vérification terminée")

            # Phase 5: Validation finale
            self._track_step_start("final_validation", "✅ Validation finale")
            validation_result = await self.validation_engine.validate_quote_data(
                self.state.client_info.get("data", {}),
                self.state.products_info
            )

            if not validation_result.get("valid"):
                return self._build_error_response("Validation finale échouée", "; ".join(validation_result.get("errors", [])))

            self._track_step_complete("final_validation", "✅ Données validées")

            # Phase 6: Création du devis
            self._track_step_start("create_quote", "📄 Création du devis")
            quote_result = await self.quote_manager.create_quote(
                self.state.client_info.get("data", {}),
                self.state.products_info
            )

            if not quote_result.get("success"):
                return self._build_error_response("Création devis échouée", quote_result.get("error"))

            self._track_step_complete("create_quote", "✅ Devis créé avec succès")

            # Finalisation
            final_result = self._build_success_response(quote_result)

            # Terminer la tâche
            if self.current_task:
                progress_tracker.complete_task(self.task_id, final_result)

            return final_result

        except Exception as e:
            logger.exception(f"Erreur workflow principal: {e}")
            if self.current_task:
                progress_tracker.fail_task(self.task_id, str(e))
            return self._build_error_response("Erreur système", str(e))

    async def continue_after_user_input(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """
        Continue le workflow après une interaction utilisateur

        Args:
            user_input: Réponse de l'utilisateur
            context: Contexte de l'interaction

        Returns:
            Résultat de la continuation
        """
        try:
            # Restaurer le contexte si nécessaire
            if self.task_id:
                task = progress_tracker.get_task(self.task_id)
                if task and hasattr(task, 'context') and task.context:
                    self.state.context.update(task.context)

            interaction_type = context.get("interaction_type")

            if interaction_type == "client_selection":
                return await self._handle_client_selection(user_input, context)
            elif interaction_type == "client_creation":
                return await self._handle_client_creation(user_input, context)
            elif interaction_type == "product_selection":
                return await self._handle_product_selection(user_input, context)
            elif interaction_type == "duplicate_resolution":
                return await self._handle_duplicate_resolution(user_input, context)
            else:
                return self._build_error_response("Type d'interaction non reconnu", f"Type: {interaction_type}")

        except Exception as e:
            logger.exception(f"Erreur continuation workflow: {e}")
            return self._build_error_response("Erreur continuation", str(e))

    async def _process_client_validation(self, client_name: str) -> Dict[str, Any]:
        """Traite la validation du client"""
        if not client_name:
            return {"success": False, "error": "Nom du client manquant"}

        client_info = await self.client_manager.validate_client(client_name)

        if client_info.get("found"):
            return {"success": True, "client_info": client_info}
        elif client_info.get("suggestions"):
            return {
                "success": False,
                "status": "user_interaction_required",
                "interaction_type": "client_selection",
                "suggestions": client_info["suggestions"],
                "message": client_info.get("message")
            }
        else:
            # Client non trouvé, proposer la création
            return {
                "success": False,
                "status": "user_interaction_required",
                "interaction_type": "client_creation",
                "client_name": client_name,
                "message": f"Client '{client_name}' non trouvé. Souhaitez-vous le créer ?"
            }

    async def _process_products_validation(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Traite la validation des produits"""
        if not products:
            return {"success": False, "error": "Aucun produit spécifié"}

        validated_products = await self.product_manager.validate_products(products)

        # Vérifier s'il y a des produits nécessitant une sélection
        products_with_suggestions = [p for p in validated_products if not p.get("found") and p.get("suggestions")]

        if products_with_suggestions:
            return {
                "success": False,
                "status": "user_interaction_required",
                "interaction_type": "product_selection",
                "products": validated_products,
                "message": f"{len(products_with_suggestions)} produit(s) nécessitent votre attention"
            }

        # Vérifier qu'au moins un produit est valide
        valid_products = [p for p in validated_products if p.get("found")]
        if not valid_products:
            return {"success": False, "error": "Aucun produit valide trouvé"}

        return {"success": True, "products": validated_products}

    async def _check_duplicate_quotes(self) -> Dict[str, Any]:
        """Vérifie les doublons de devis"""
        return await self.quote_manager.check_duplicate_quotes(
            self.state.client_info,
            self.state.products_info
        )

    async def _handle_client_selection(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la sélection de client par l'utilisateur"""
        selected_client = user_input.get("selected_client")
        if not selected_client:
            return self._build_error_response("Sélection invalide", "Aucun client sélectionné")

        # Mettre à jour l'état avec le client sélectionné
        self.state.client_info = {"data": selected_client, "found": True}
        self.state.save_to_task(progress_tracker)

        # Continuer avec la validation des produits
        extracted_info = self.state.extracted_info
        return await self._process_products_validation(extracted_info.get("products", []))

    async def _handle_client_creation(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la création d'un nouveau client"""
        if user_input.get("action") != "create_client":
            return self._build_error_response("Action annulée", "Création du client annulée")

        client_name = context.get("client_name")
        if not client_name:
            return self._build_error_response("Données manquantes", "Nom du client manquant")

        # Créer le client
        creation_result = await self.client_manager.create_client({"company_name": client_name})

        if not creation_result.get("success"):
            return self._build_error_response("Création échouée", creation_result.get("error"))

        # Mettre à jour l'état
        self.state.client_info = {"data": creation_result.get("client_data", {}), "found": True, "created": True}
        self.state.save_to_task(progress_tracker)

        # Continuer avec la validation des produits
        extracted_info = self.state.extracted_info
        return await self._process_products_validation(extracted_info.get("products", []))

    async def _handle_product_selection(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la sélection de produit par l'utilisateur"""
        selected_product = user_input.get("selected_product")
        if not selected_product:
            return self._build_error_response("Sélection invalide", "Aucun produit sélectionné")

        # Mettre à jour les produits avec la sélection
        # Logique simplifiée - à adapter selon les besoins
        self.state.products_info = [selected_product]
        self.state.save_to_task(progress_tracker)

        # Continuer avec la création du devis
        quote_result = await self.quote_manager.create_quote(
            self.state.client_info.get("data", {}),
            self.state.products_info
        )

        if not quote_result.get("success"):
            return self._build_error_response("Création devis échouée", quote_result.get("error"))

        return self._build_success_response(quote_result)

    async def _handle_duplicate_resolution(self, user_input: Dict, context: Dict) -> Dict[str, Any]:
        """Gère la résolution des doublons"""
        action = user_input.get("action")

        if action == "proceed":
            # Continuer malgré les doublons
            quote_result = await self.quote_manager.create_quote(
                self.state.client_info.get("data", {}),
                self.state.products_info
            )

            if not quote_result.get("success"):
                return self._build_error_response("Création devis échouée", quote_result.get("error"))

            return self._build_success_response(quote_result)

        elif action == "cancel":
            return {"status": "cancelled", "message": "Demande de devis annulée"}

        else:
            return self._build_error_response("Action non reconnue", f"Action: {action}")

    def _initialize_task_tracking(self, user_prompt: str) -> str:
        """Initialise le tracking de tâche"""
        try:
            self.current_task = progress_tracker.create_task(
                user_prompt=user_prompt,
                draft_mode=self.draft_mode
            )
            task_id = self.current_task.task_id
            self.state.task_id = task_id
            logger.info(f"✅ Tâche créée: {task_id}")
            return task_id
        except Exception as e:
            logger.error(f"Erreur création tâche: {e}")
            return f"task_{int(datetime.now().timestamp())}"

    def _track_step_start(self, step_id: str, message: str = ""):
        """Démarre le tracking d'une étape"""
        if self.current_task:
            self.current_task.start_step(step_id, message)

    def _track_step_complete(self, step_id: str, message: str = ""):
        """Termine une étape avec succès"""
        if self.current_task:
            self.current_task.complete_step(step_id, message)

    def _track_step_fail(self, step_id: str, error: str, message: str = ""):
        """Termine une étape en erreur"""
        if self.current_task:
            self.current_task.fail_step(step_id, error, message)

    def _build_error_response(self, error_title: str, error_message: str) -> Dict[str, Any]:
        """Construit une réponse d'erreur standardisée"""
        return {
            "success": False,
            "status": "error",
            "error": error_message,
            "error_type": error_title.lower().replace(" ", "_"),
            "task_id": self.task_id,
            "timestamp": datetime.now().isoformat()
        }

    def _build_success_response(self, quote_result: Dict[str, Any]) -> Dict[str, Any]:
        """Construit une réponse de succès standardisée"""
        return {
            "success": True,
            "status": "success",
            "quote_id": quote_result.get("quote_id"),
            "sap_doc_num": quote_result.get("quote_id"),
            "salesforce_opportunity_id": quote_result.get("salesforce_result", {}).get("opportunity_id"),
            "total_amount": quote_result.get("total_amount", 0),
            "currency": "EUR",
            "products": quote_result.get("products", []),
            "client": self.state.client_info.get("data", {}),
            "task_id": self.task_id,
            "date": datetime.now().strftime('%Y-%m-%d'),
            "message": "Devis créé avec succès"
        }


# Classe de compatibilité pour maintenir l'interface existante
class DevisWorkflow(DevisWorkflowRefactored):
    """Classe de compatibilité qui hérite du workflow refactorisé"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.info("✅ Utilisation du workflow refactorisé via interface de compatibilité")

    # Méthodes de compatibilité pour maintenir l'API existante
    async def process_prompt(self, user_prompt: str, task_id: str = None, draft_mode: bool = False) -> Dict[str, Any]:
        """Méthode de compatibilité pour process_prompt"""
        if task_id:
            self.task_id = task_id
        return await self.process_quote_request(user_prompt, draft_mode)


# Classe améliorée pour les workflows parallèles
class EnhancedDevisWorkflow(DevisWorkflowRefactored):
    """Version améliorée avec capacités de traitement parallèle"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parallel_enabled = True
        logger.info("✅ Workflow amélioré avec traitement parallèle initialisé")

    async def process_quote_request_parallel(self, user_prompt: str, draft_mode: bool = False) -> Dict[str, Any]:
        """Version parallélisée du traitement de devis"""
        try:
            # Phase 1: Extraction (séquentielle)
            self._track_step_start("extract_info", "🔍 Analyse de votre demande")
            extracted_info = await self.llm_extractor.extract_quote_info(user_prompt)

            if not extracted_info:
                return self._build_error_response("Extraction échouée", "Impossible d'analyser votre demande")

            self.state.extracted_info = extracted_info
            self._track_step_complete("extract_info", "✅ Demande analysée")

            # Phase 2: Validation parallèle client + produits
            self._track_step_start("parallel_validation", "⚡ Validation parallèle")

            client_task = asyncio.create_task(
                self._process_client_validation(extracted_info.get("client"))
            )
            products_task = asyncio.create_task(
                self._process_products_validation(extracted_info.get("products", []))
            )

            # Attendre les deux validations
            client_result, products_result = await asyncio.gather(client_task, products_task, return_exceptions=True)

            # Gérer les exceptions
            if isinstance(client_result, Exception):
                return self._build_error_response("Erreur validation client", str(client_result))
            if isinstance(products_result, Exception):
                return self._build_error_response("Erreur validation produits", str(products_result))

            # Vérifier les résultats
            if client_result.get("status") == "user_interaction_required":
                return client_result
            if products_result.get("status") == "user_interaction_required":
                return products_result

            if not client_result.get("success") or not products_result.get("success"):
                return self._build_error_response(
                    "Validation échouée", 
                    f"Client: {client_result.get('error', 'OK')}, Produits: {products_result.get('error', 'OK')}"
                )

            self.state.client_info = client_result.get("client_info", {})
            self.state.products_info = products_result.get("products", [])
            self._track_step_complete("parallel_validation", "✅ Validations parallèles terminées")

            # Suite du workflow (séquentielle)
            return await self._continue_sequential_workflow()

        except Exception as e:
            logger.exception(f"Erreur workflow parallèle: {e}")
            return self._build_error_response("Erreur système", str(e))

    async def _continue_sequential_workflow(self) -> Dict[str, Any]:
        """Continue le workflow de manière séquentielle après la validation parallèle"""
        # Vérification des doublons
        self._track_step_start("check_duplicates", "🔍 Vérification des doublons")
        duplicate_result = await self._check_duplicate_quotes()

        if duplicate_result.get("requires_user_decision"):
            return {
                "status": "user_interaction_required",
                "interaction_type": "duplicate_resolution",
                "message": duplicate_result.get("alert_message"),
                "duplicate_data": duplicate_result
            }

        self._track_step_complete("check_duplicates", "✅ Vérification terminée")

        # Validation finale
        self._track_step_start("final_validation", "✅ Validation finale")
        validation_result = await self.validation_engine.validate_quote_data(
            self.state.client_info.get("data", {}),
            self.state.products_info
        )

        if not validation_result.get("valid"):
            return self._build_error_response("Validation finale échouée", "; ".join(validation_result.get("errors", [])))

        self._track_step_complete("final_validation", "✅ Données validées")

        # Création du devis
        self._track_step_start("create_quote", "📄 Création du devis")
        quote_result = await self.quote_manager.create_quote(
            self.state.client_info.get("data", {}),
            self.state.products_info
        )

        if not quote_result.get("success"):
            return self._build_error_response("Création devis échouée", quote_result.get("error"))

        self._track_step_complete("create_quote", "✅ Devis créé avec succès")

        # Finalisation
        final_result = self._build_success_response(quote_result)

        if self.current_task:
            progress_tracker.complete_task(self.task_id, final_result)

        return final_result
