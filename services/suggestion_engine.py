"""
🧠 SuggestionEngine - Moteur d'Intelligence NOVA
===============================================

Moteur central qui transforme NOVA en véritable assistant intelligent,
capable de proposer des solutions proactives à chaque problème.

Principe : "NOVA ne dit jamais juste 'Non trouvé' - il propose TOUJOURS une solution"
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from fuzzywuzzy import fuzz, process
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SuggestionType(Enum):
    """Types de suggestions disponibles"""
    CLIENT_MATCH = "client_match"
    PRODUCT_MATCH = "product_match"
    ACTION_SUGGESTION = "action_suggestion"
    CORRECTION = "correction"
    ALTERNATIVE = "alternative"
    ENHANCEMENT = "enhancement"

class ConfidenceLevel(Enum):
    """Niveaux de confiance pour les suggestions"""
    HIGH = "high"      # > 90% - Action automatique recommandée
    MEDIUM = "medium"  # 70-90% - Proposition avec explication
    LOW = "low"        # 50-70% - Suggestion avec alternatives
    VERY_LOW = "very_low"  # < 50% - Recherche élargie

@dataclass
class Suggestion:
    """Structure d'une suggestion intelligente"""
    type: SuggestionType
    confidence: ConfidenceLevel
    original_input: str
    suggested_value: str
    score: float
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour API"""
        return {
            "type": self.type.value,
            "confidence": self.confidence.value,
            "original_input": self.original_input,
            "suggested_value": self.suggested_value,
            "score": self.score,
            "explanation": self.explanation,
            "metadata": self.metadata,
            "alternatives": self.alternatives,
            "actions": self.actions
        }

@dataclass
class SuggestionResult:
    """Résultat complet d'une analyse de suggestions"""
    has_suggestions: bool
    primary_suggestion: Optional[Suggestion] = None
    all_suggestions: List[Suggestion] = field(default_factory=list)
    requires_user_action: bool = False
    conversation_prompt: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour API"""
        return {
            "has_suggestions": self.has_suggestions,
            "primary_suggestion": self.primary_suggestion.to_dict() if self.primary_suggestion else None,
            "all_suggestions": [s.to_dict() for s in self.all_suggestions],
            "requires_user_action": self.requires_user_action,
            "conversation_prompt": self.conversation_prompt
        }

class FuzzyMatcher:
    """Moteur de correspondance floue multi-algorithmes"""
    
    @staticmethod
    def calculate_similarity(query: str, candidate: str) -> float:
        """Calcule la similarité entre deux chaînes avec plusieurs algorithmes"""
        if not query or not candidate:
            return 0.0
        
        # Normalisation
        query_norm = query.lower().strip()
        candidate_norm = candidate.lower().strip()
        
        # Correspondance exacte
        if query_norm == candidate_norm:
            return 100.0
        
        # Algorithmes de similarité
        ratio = fuzz.ratio(query_norm, candidate_norm)
        partial_ratio = fuzz.partial_ratio(query_norm, candidate_norm)
        token_sort = fuzz.token_sort_ratio(query_norm, candidate_norm)
        token_set = fuzz.token_set_ratio(query_norm, candidate_norm)
        
        # Pondération des scores
        final_score = (
            ratio * 0.3 +
            partial_ratio * 0.2 +
            token_sort * 0.25 +
            token_set * 0.25
        )
        
        return round(final_score, 2)
    
    @staticmethod
    def find_best_matches(query: str, candidates: List[Dict[str, Any]], 
                         key_field: str = "name", limit: int = 5) -> List[Dict[str, Any]]:
        """Trouve les meilleures correspondances avec scores"""
        if not query or not candidates:
            return []
        
        matches = []
        for candidate in candidates:
            candidate_value = candidate.get(key_field, "")
            if candidate_value:
                score = FuzzyMatcher.calculate_similarity(query, candidate_value)
                if score > 30:  # Seuil minimum de pertinence
                    matches.append({
                        **candidate,
                        "similarity_score": score,
                        "matched_field": key_field
                    })
        
        # Trier par score décroissant
        matches.sort(key=lambda x: x["similarity_score"], reverse=True)
        return matches[:limit]

class SuggestionEngine:
    """
    🧠 Moteur d'Intelligence Central de NOVA
    
    Transforme chaque problème en solution proactive
    """
    
    def __init__(self):
        self.matcher = FuzzyMatcher()
        self.conversation_patterns = self._load_conversation_patterns()
        
    def _load_conversation_patterns(self) -> Dict[str, str]:
        """Templates de conversation pour différents scénarios"""
        return {
            "client_not_found_high_confidence": (
                "Client '{original}' non trouvé, mais je pense que vous voulez dire '{suggestion}' "
                "(similarité {score}%). Voulez-vous :\n"
                "1. ✅ Utiliser '{suggestion}'\n"
                "2. 🆕 Créer un nouveau client '{original}'\n"
                "3. 🔍 Voir d'autres clients similaires"
            ),
            "client_not_found_medium_confidence": (
                "Client '{original}' non trouvé. Voici les clients les plus proches :\n"
                "{alternatives}\n"
                "Voulez-vous utiliser l'un d'eux ou créer un nouveau client ?"
            ),
            "product_not_found_with_alternatives": (
                "Produit '{original}' non trouvé. Produits similaires disponibles :\n"
                "{alternatives}\n"
                "Lequel souhaitez-vous utiliser ?"
            ),
            "multiple_corrections_needed": (
                "J'ai détecté plusieurs éléments à corriger dans votre demande :\n"
                "{corrections}\n"
                "Dois-je appliquer ces corrections et générer le devis ?"
            )
        }
    
    async def suggest_client(self, user_input: str, available_clients: List[Dict[str, Any]]) -> SuggestionResult:
        """
        Analyse et propose des clients basés sur la saisie utilisateur
        
        Args:
            user_input: Nom du client saisi par l'utilisateur
            available_clients: Liste des clients disponibles (Salesforce + SAP)
            
        Returns:
            SuggestionResult avec les meilleures suggestions
        """
        logger.info(f"🔍 Recherche de suggestions pour client: '{user_input}'")
        
        if not user_input or not available_clients:
            return SuggestionResult(has_suggestions=False)
        
        # Recherche des correspondances
        matches = self.matcher.find_best_matches(
            user_input, 
            available_clients, 
            key_field="Name",
            limit=5
        )
        
        if not matches:
            return self._create_no_client_suggestion(user_input)
        
        # Analyser le meilleur match
        best_match = matches[0]
        confidence = self._calculate_confidence(best_match["similarity_score"])
        
        # Créer la suggestion principale
        primary_suggestion = Suggestion(
            type=SuggestionType.CLIENT_MATCH,
            confidence=confidence,
            original_input=user_input,
            suggested_value=best_match["Name"],
            score=best_match["similarity_score"],
            explanation=self._generate_client_explanation(best_match),
            metadata={
                "salesforce_id": best_match.get("Id"),
                "account_number": best_match.get("AccountNumber"),
                "last_activity": best_match.get("LastActivityDate"),
                "annual_revenue": best_match.get("AnnualRevenue")
            },
            alternatives=[self._format_client_alternative(m) for m in matches[1:3]],
            actions=self._generate_client_actions(confidence, user_input, best_match)
        )
        
        # Générer le prompt de conversation
        conversation_prompt = self._generate_client_conversation(
            confidence, user_input, best_match, matches
        )
        
        return SuggestionResult(
            has_suggestions=True,
            primary_suggestion=primary_suggestion,
            all_suggestions=[primary_suggestion],
            requires_user_action=(confidence != ConfidenceLevel.HIGH),
            conversation_prompt=conversation_prompt
        )
    
    async def suggest_product(self, user_input: str, available_products: List[Dict[str, Any]]) -> SuggestionResult:
        """
        Analyse et propose des produits basés sur la saisie utilisateur
        
        Args:
            user_input: Référence/nom du produit saisi par l'utilisateur
            available_products: Liste des produits disponibles (SAP)
            
        Returns:
            SuggestionResult avec les meilleures suggestions
        """
        logger.info(f"🔍 Recherche de suggestions pour produit: '{user_input}'")
        
        if not user_input or not available_products:
            return SuggestionResult(has_suggestions=False)
        
        # Recherche sur plusieurs champs
        matches = []
        
        # Recherche par code produit
        code_matches = self.matcher.find_best_matches(
            user_input, available_products, key_field="ItemCode", limit=3
        )
        matches.extend(code_matches)
        
        # Recherche par nom produit
        name_matches = self.matcher.find_best_matches(
            user_input, available_products, key_field="ItemName", limit=3
        )
        matches.extend(name_matches)
        
        # Déduplication et tri
        unique_matches = {}
        for match in matches:
            item_code = match.get("ItemCode")
            if item_code and (item_code not in unique_matches or 
                             match["similarity_score"] > unique_matches[item_code]["similarity_score"]):
                unique_matches[item_code] = match
        
        sorted_matches = sorted(unique_matches.values(), 
                              key=lambda x: x["similarity_score"], reverse=True)[:5]
        
        if not sorted_matches:
            return self._create_no_product_suggestion(user_input)
        
        # Analyser le meilleur match
        best_match = sorted_matches[0]
        confidence = self._calculate_confidence(best_match["similarity_score"])
        
        # Créer la suggestion principale
        primary_suggestion = Suggestion(
            type=SuggestionType.PRODUCT_MATCH,
            confidence=confidence,
            original_input=user_input,
            suggested_value=f"{best_match['ItemCode']} - {best_match.get('ItemName', 'Sans nom')}",
            score=best_match["similarity_score"],
            explanation=self._generate_product_explanation(best_match),
            metadata={
                "item_code": best_match.get("ItemCode"),
                "item_name": best_match.get("ItemName"),
                "unit_price": best_match.get("UnitPrice"),
                "in_stock": best_match.get("InStock"),
                "stock_quantity": best_match.get("StockQuantity")
            },
            alternatives=[self._format_product_alternative(m) for m in sorted_matches[1:3]],
            actions=self._generate_product_actions(confidence, user_input, best_match)
        )
        
        # Générer le prompt de conversation
        conversation_prompt = self._generate_product_conversation(
            confidence, user_input, best_match, sorted_matches
        )
        
        return SuggestionResult(
            has_suggestions=True,
            primary_suggestion=primary_suggestion,
            all_suggestions=[primary_suggestion],
            requires_user_action=(confidence != ConfidenceLevel.HIGH),
            conversation_prompt=conversation_prompt
        )
    
    async def suggest_complete_quote(self, extracted_info: Dict[str, Any], 
                                   client_suggestions: SuggestionResult,
                                   product_suggestions: List[SuggestionResult]) -> SuggestionResult:
        """
        Génère des suggestions globales pour un devis complet
        
        Args:
            extracted_info: Informations extraites de la demande
            client_suggestions: Suggestions pour le client
            product_suggestions: Liste des suggestions pour chaque produit
            
        Returns:
            SuggestionResult avec recommandations globales
        """
        logger.info("🎯 Génération de suggestions globales pour le devis")
        
        corrections = []
        requires_action = False
        
        # Analyser les corrections client
        if client_suggestions.has_suggestions and client_suggestions.requires_user_action:
            corrections.append(f"📋 Client: {client_suggestions.conversation_prompt}")
            requires_action = True
        
        # Analyser les corrections produits
        for i, product_suggestion in enumerate(product_suggestions):
            if product_suggestion.has_suggestions and product_suggestion.requires_user_action:
                product_info = extracted_info.get("products", [])[i] if i < len(extracted_info.get("products", [])) else {}
                corrections.append(f"📦 Produit {i+1}: {product_suggestion.conversation_prompt}")
                requires_action = True
        
        if not corrections:
            # Pas de corrections nécessaires
            return SuggestionResult(
                has_suggestions=True,
                conversation_prompt="✅ Toutes les informations sont validées. Génération du devis en cours..."
            )
        
        # Générer le prompt global
        if len(corrections) == 1:
            conversation_prompt = corrections[0]
        else:
            conversation_prompt = self.conversation_patterns["multiple_corrections_needed"].format(
                corrections="\n".join(f"{i+1}. {c}" for i, c in enumerate(corrections))
            )
        
        global_suggestion = Suggestion(
            type=SuggestionType.ENHANCEMENT,
            confidence=ConfidenceLevel.MEDIUM,
            original_input=str(extracted_info),
            suggested_value="Corrections multiples proposées",
            score=85.0,
            explanation="Plusieurs éléments peuvent être optimisés pour améliorer votre devis",
            actions=["apply_all_corrections", "review_individually", "proceed_anyway"]
        )
        
        return SuggestionResult(
            has_suggestions=True,
            primary_suggestion=global_suggestion,
            all_suggestions=[global_suggestion],
            requires_user_action=requires_action,
            conversation_prompt=conversation_prompt
        )
    
    # === MÉTHODES PRIVÉES ===
    
    def _calculate_confidence(self, similarity_score: float) -> ConfidenceLevel:
        """Calcule le niveau de confiance basé sur le score de similarité"""
        if similarity_score >= 90:
            return ConfidenceLevel.HIGH
        elif similarity_score >= 70:
            return ConfidenceLevel.MEDIUM
        elif similarity_score >= 50:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def _create_no_client_suggestion(self, user_input: str) -> SuggestionResult:
        """Crée une suggestion pour un client non trouvé"""
        suggestion = Suggestion(
            type=SuggestionType.ACTION_SUGGESTION,
            confidence=ConfidenceLevel.MEDIUM,
            original_input=user_input,
            suggested_value=f"Créer le client '{user_input}'",
            score=0.0,
            explanation=f"Le client '{user_input}' n'existe pas dans la base de données",
            actions=["create_new_client", "search_broader", "manual_entry"]
        )
        
        conversation_prompt = (
            f"Client '{user_input}' non trouvé. Voulez-vous :\n"
            f"1. 🆕 Créer un nouveau client '{user_input}'\n"
            f"2. 🔍 Rechercher avec d'autres critères\n"
            f"3. ✏️ Saisir manuellement les informations client"
        )
        
        return SuggestionResult(
            has_suggestions=True,
            primary_suggestion=suggestion,
            requires_user_action=True,
            conversation_prompt=conversation_prompt
        )
    
    def _create_no_product_suggestion(self, user_input: str) -> SuggestionResult:
        """Crée une suggestion pour un produit non trouvé"""
        suggestion = Suggestion(
            type=SuggestionType.ACTION_SUGGESTION,
            confidence=ConfidenceLevel.MEDIUM,
            original_input=user_input,
            suggested_value=f"Rechercher alternatives pour '{user_input}'",
            score=0.0,
            explanation=f"Le produit '{user_input}' n'existe pas dans le catalogue",
            actions=["search_alternatives", "check_catalog", "contact_support"]
        )
        
        conversation_prompt = (
            f"Produit '{user_input}' non trouvé dans le catalogue. Voulez-vous :\n"
            f"1. 🔍 Rechercher des produits similaires\n"
            f"2. 📋 Consulter le catalogue complet\n"
            f"3. 📞 Contacter le support technique"
        )
        
        return SuggestionResult(
            has_suggestions=True,
            primary_suggestion=suggestion,
            requires_user_action=True,
            conversation_prompt=conversation_prompt
        )
    
    def _generate_client_explanation(self, match: Dict[str, Any]) -> str:
        """Génère une explication pour une suggestion client"""
        explanations = [f"Similarité de {match['similarity_score']}%"]
        
        if match.get("AnnualRevenue"):
            explanations.append(f"CA annuel: {match['AnnualRevenue']:,.0f}€")
        
        if match.get("LastActivityDate"):
            explanations.append(f"Dernière activité: {match['LastActivityDate']}")
        
        return " | ".join(explanations)
    
    def _generate_product_explanation(self, match: Dict[str, Any]) -> str:
        """Génère une explication pour une suggestion produit"""
        explanations = [f"Similarité de {match['similarity_score']}%"]
        
        if match.get("UnitPrice"):
            explanations.append(f"Prix: {match['UnitPrice']:.2f}€ HT")
        
        if match.get("InStock"):
            stock_qty = match.get("StockQuantity", 0)
            explanations.append(f"Stock: {stock_qty} unités disponibles")
        else:
            explanations.append("Stock: Non disponible")
        
        return " | ".join(explanations)
    
    def _format_client_alternative(self, match: Dict[str, Any]) -> Dict[str, Any]:
        """Formate une alternative client"""
        return {
            "name": match["Name"],
            "score": match["similarity_score"],
            "id": match.get("Id"),
            "account_number": match.get("AccountNumber"),
            "revenue": match.get("AnnualRevenue")
        }
    
    def _format_product_alternative(self, match: Dict[str, Any]) -> Dict[str, Any]:
        """Formate une alternative produit"""
        return {
            "code": match.get("ItemCode"),
            "name": match.get("ItemName"),
            "score": match["similarity_score"],
            "price": match.get("UnitPrice"),
            "stock": match.get("StockQuantity"),
            "available": match.get("InStock", False)
        }
    
    def _generate_client_actions(self, confidence: ConfidenceLevel, 
                               original: str, match: Dict[str, Any]) -> List[str]:
        """Génère les actions possibles pour un client"""
        actions = []
        
        if confidence == ConfidenceLevel.HIGH:
            actions.extend(["auto_use_suggestion", "confirm_and_proceed"])
        else:
            actions.extend(["use_suggestion", "create_new_client", "search_more"])
        
        if match.get("Id"):
            actions.append("view_client_details")
        
        return actions
    
    def _generate_product_actions(self, confidence: ConfidenceLevel,
                                original: str, match: Dict[str, Any]) -> List[str]:
        """Génère les actions possibles pour un produit"""
        actions = []
        
        if confidence == ConfidenceLevel.HIGH and match.get("InStock"):
            actions.extend(["auto_use_suggestion", "confirm_and_proceed"])
        else:
            actions.extend(["use_suggestion", "search_alternatives"])
        
        if not match.get("InStock"):
            actions.append("find_alternatives")
        
        actions.append("view_product_details")
        return actions
    
    def _generate_client_conversation(self, confidence: ConfidenceLevel,
                                    original: str, best_match: Dict[str, Any],
                                    all_matches: List[Dict[str, Any]]) -> str:
        """Génère le prompt de conversation pour un client"""
        if confidence == ConfidenceLevel.HIGH:
            return self.conversation_patterns["client_not_found_high_confidence"].format(
                original=original,
                suggestion=best_match["Name"],
                score=best_match["similarity_score"]
            )
        else:
            alternatives = "\n".join([
                f"{i+1}. {match['Name']} (similarité: {match['similarity_score']}%)"
                for i, match in enumerate(all_matches[:3])
            ])
            return self.conversation_patterns["client_not_found_medium_confidence"].format(
                original=original,
                alternatives=alternatives
            )
    
    def _generate_product_conversation(self, confidence: ConfidenceLevel,
                                     original: str, best_match: Dict[str, Any],
                                     all_matches: List[Dict[str, Any]]) -> str:
        """Génère le prompt de conversation pour un produit"""
        alternatives = []
        for i, match in enumerate(all_matches[:3]):
            stock_info = ""
            if match.get("InStock"):
                stock_qty = match.get("StockQuantity", 0)
                stock_info = f" (stock: {stock_qty})"
            else:
                stock_info = " (rupture)"
            
            price_info = ""
            if match.get("UnitPrice"):
                price_info = f" - {match['UnitPrice']:.2f}€"
            
            alternatives.append(
                f"{i+1}. {match.get('ItemCode')} - {match.get('ItemName', 'Sans nom')}"
                f"{price_info}{stock_info} (similarité: {match['similarity_score']}%)"
            )
        
        return self.conversation_patterns["product_not_found_with_alternatives"].format(
            original=original,
            alternatives="\n".join(alternatives)
        )


# === CLASSE UTILITAIRE POUR LES TESTS ===

class MockDataProvider:
    """Fournit des données de test pour le SuggestionEngine"""
    
    @staticmethod
    def get_mock_clients() -> List[Dict[str, Any]]:
        """Retourne des clients de test"""
        return [
            {
                "Id": "001XX000004C3V2",
                "Name": "Edge Communications",
                "AccountNumber": "CD451796",
                "AnnualRevenue": 50000,
                "LastActivityDate": "2024-12-01"
            },
            {
                "Id": "001XX000004C3V3",
                "Name": "Orange Communications",
                "AccountNumber": "CD451797",
                "AnnualRevenue": 150000,
                "LastActivityDate": "2024-11-28"
            },
            {
                "Id": "001XX000004C3V4",
                "Name": "Airbus Industries",
                "AccountNumber": "CD451798",
                "AnnualRevenue": 2000000,
                "LastActivityDate": "2024-12-02"
            }
        ]
    
    @staticmethod
    def get_mock_products() -> List[Dict[str, Any]]:
        """Retourne des produits de test"""
        return [
            {
                "ItemCode": "A00001",
                "ItemName": "Produit Premium",
                "UnitPrice": 55.00,
                "InStock": True,
                "StockQuantity": 75
            },
            {
                "ItemCode": "A00002",
                "ItemName": "Produit Standard",
                "UnitPrice": 40.00,
                "InStock": True,
                "StockQuantity": 150
            },
            {
                "ItemCode": "A10025",
                "ItemName": "Produit Spécialisé",
                "UnitPrice": 120.00,
                "InStock": False,
                "StockQuantity": 0
            }
        ]


if __name__ == "__main__":
    # Tests de base
    async def test_suggestion_engine():
        """Test de base du SuggestionEngine"""
        engine = SuggestionEngine()
        
        # Test suggestions client
        clients = MockDataProvider.get_mock_clients()
        result = await engine.suggest_client("Edge Comunications", clients)
        
        print("=== TEST CLIENT SUGGESTIONS ===")
        print(f"Has suggestions: {result.has_suggestions}")
        if result.primary_suggestion:
            print(f"Suggestion: {result.primary_suggestion.suggested_value}")
            print(f"Score: {result.primary_suggestion.score}")
            print(f"Confidence: {result.primary_suggestion.confidence.value}")
        print(f"Conversation: {result.conversation_prompt}")
        
        # Test suggestions produit
        products = MockDataProvider.get_mock_products()
        result = await engine.suggest_product("A00025", products)
        
        print("\n=== TEST PRODUCT SUGGESTIONS ===")
        print(f"Has suggestions: {result.has_suggestions}")
        if result.primary_suggestion:
            print(f"Suggestion: {result.primary_suggestion.suggested_value}")
            print(f"Score: {result.primary_suggestion.score}")
            print(f"Confidence: {result.primary_suggestion.confidence.value}")
        print(f"Conversation: {result.conversation_prompt}")
    
    # Exécuter les tests
    asyncio.run(test_suggestion_engine())