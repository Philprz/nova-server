# utils/common_utils.py
"""
Utilitaires communs pour éliminer les doublons de code
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class ResponseBuilder:
    """Constructeur de réponses standardisées - UNE SEULE VERSION"""
    
    @staticmethod
    def build_error_response(error_title: str, error_message: str, 
                           context: Optional[Dict] = None, 
                           task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Construction d'une réponse d'erreur standardisée
        REMPLACE toutes les versions dupliquées de _build_error_response
        """
        response = {
            "success": False,
            "error": error_message,
            "error_title": error_title,
            "timestamp": datetime.now().isoformat(),
            "status": "error"
        }
        
        if context:
            response["context"] = context
        
        if task_id:
            response["task_id"] = task_id
        
        return response
    
    @staticmethod
    def build_success_response(data: Any, message: str = "Success", 
                             task_id: Optional[str] = None) -> Dict[str, Any]:
        """Construction d'une réponse de succès standardisée"""
        response = {
            "success": True,
            "data": data,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "status": "success"
        }
        
        if task_id:
            response["task_id"] = task_id
        
        return response
    
    @staticmethod
    def build_warning_response(message: str, data: Any = None, 
                             warnings: List[str] = None,
                             task_id: Optional[str] = None) -> Dict[str, Any]:
        """Construction d'une réponse d'avertissement"""
        response = {
            "success": False,
            "status": "warning",
            "message": message,
            "warnings": warnings or [],
            "timestamp": datetime.now().isoformat()
        }
        
        if data:
            response["data"] = data
        
        if task_id:
            response["task_id"] = task_id
        
        return response
    
    @staticmethod
    def build_suggestions_response(suggestions: Dict[str, Any], 
                                 message: str = "Suggestions disponibles",
                                 task_id: Optional[str] = None) -> Dict[str, Any]:
        """Construction d'une réponse avec suggestions"""
        return {
            "success": False,
            "status": "suggestions_required",
            "message": message,
            "suggestions": suggestions,
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id
        }

class ValidationUtils:
    """Utilitaires de validation réutilisables - FACTORISATION"""
    
    @staticmethod
    def validate_phone_format(phone: str) -> bool:
        """
        Validation téléphone - FACTORISATION de client_validator.py
        """
        if not phone:
            return False
        
        # Nettoyer le numéro
        clean_phone = re.sub(r'[\s\-\.\(\)]', '', phone)
        
        # Patterns pour différents formats
        patterns = [
            r'^(\+33|0033)[1-9]\d{8}$',  # France
            r'^(\+1|001)?[2-9]\d{2}[2-9]\d{2}\d{4}$',  # USA/Canada
            r'^(\+44|0044|0)[1-9]\d{8,9}$',  # UK
            r'^\+[1-9]\d{1,14}$'  # Format international général
        ]
        
        return any(re.match(pattern, clean_phone) for pattern in patterns)
    
    @staticmethod
    def validate_postal_code(postal_code: str, country: str) -> bool:
        """
        Validation code postal par pays - FACTORISATION
        """
        if not postal_code:
            return False
        
        patterns = {
            "FR": r'^\d{5}$',
            "US": r'^\d{5}(-\d{4})?$',
            "UK": r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$',
            "CA": r'^[A-Z]\d[A-Z] \d[A-Z]\d$',
            "DE": r'^\d{5}$',
            "ES": r'^\d{5}$',
            "IT": r'^\d{5}$'
        }
        
        pattern = patterns.get(country.upper(), r'.*')  # Accepter tout par défaut
        return bool(re.match(pattern, postal_code.upper()))
    
    @staticmethod
    def validate_email_format(email: str) -> bool:
        """Validation email basique"""
        if not email:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_siret_format(siret: str) -> bool:
        """Validation format SIRET français"""
        if not siret:
            return False
        
        # Nettoyer
        clean_siret = re.sub(r'[\s\-\.]', '', siret)
        return bool(re.match(r'^\d{14}$', clean_siret))
    
    @staticmethod
    def normalize_company_name(name: str) -> str:
        """Normalisation nom d'entreprise"""
        if not name:
            return ""
        
        # Nettoyer et normaliser
        normalized = re.sub(r'\s+', ' ', name.strip())
        normalized = normalized.title()
        
        # Corrections communes
        corrections = {
            " Sarl": " SARL",
            " Sas": " SAS",
            " Sa": " SA",
            " Eurl": " EURL",
            " Sci": " SCI"
        }
        
        for old, new in corrections.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    @staticmethod
    def extract_numeric_value(value: str) -> float:
        """Extraction valeur numérique d'une chaîne"""
        if not value:
            return 0.0
        
        # Suppression des caractères non numériques sauf . et ,
        clean_value = re.sub(r'[^\d.,]', '', str(value))
        
        # Gestion des séparateurs décimaux
        if ',' in clean_value and '.' in clean_value:
            # Format français : 1.234,56
            clean_value = clean_value.replace('.', '').replace(',', '.')
        elif ',' in clean_value:
            # Soit milliers, soit décimales
            if clean_value.count(',') == 1 and len(clean_value.split(',')[1]) <= 2:
                # Décimales
                clean_value = clean_value.replace(',', '.')
            else:
                # Milliers
                clean_value = clean_value.replace(',', '')
        
        try:
            return float(clean_value)
        except ValueError:
            return 0.0

class ErrorHandler:
    """Gestionnaire d'erreurs centralisé"""
    
    def __init__(self):
        self.response_builder = ResponseBuilder()
    
    def handle_client_search_error(self, client_name: str, error: str) -> Dict[str, Any]:
        """Gestion d'erreur recherche client"""
        return self.response_builder.build_error_response(
            "Erreur recherche client",
            f"Impossible de rechercher le client '{client_name}': {error}",
            context={"client_name": client_name, "error_type": "client_search"}
        )
    
    def handle_client_creation_error(self, client_name: str, error: str) -> Dict[str, Any]:
        """Gestion d'erreur création client"""
        return self.response_builder.build_error_response(
            "Erreur création client",
            f"Impossible de créer le client '{client_name}': {error}",
            context={"client_name": client_name, "error_type": "client_creation"}
        )
    
    def handle_products_error(self, error: str) -> Dict[str, Any]:
        """Gestion d'erreur produits"""
        return self.response_builder.build_error_response(
            "Erreur produits",
            f"Erreur lors de la recherche des produits: {error}",
            context={"error_type": "products_search"}
        )
    
    def handle_extraction_error(self, error: str) -> Dict[str, Any]:
        """Gestion d'erreur extraction LLM"""
        return self.response_builder.build_error_response(
            "Erreur d'analyse",
            f"Impossible d'analyser votre demande: {error}",
            context={"error_type": "llm_extraction"}
        )
    
    def handle_generation_error(self, error: str) -> Dict[str, Any]:
        """Gestion d'erreur génération"""
        return self.response_builder.build_error_response(
            "Erreur de génération",
            f"Impossible de générer le devis: {error}",
            context={"error_type": "quote_generation"}
        )
    
    def handle_missing_info_error(self, client_name: str, product_codes: List[str]) -> Dict[str, Any]:
        """Gestion d'informations manquantes"""
        missing_items = []
        if not client_name:
            missing_items.append("nom du client")
        if not product_codes:
            missing_items.append("codes produits")
        
        return self.response_builder.build_error_response(
            "Informations manquantes",
            f"Informations manquantes: {', '.join(missing_items)}",
            context={
                "client_name": client_name,
                "product_codes": product_codes,
                "error_type": "missing_info"
            }
        )
    
    def handle_client_not_found(self, client_name: str) -> Dict[str, Any]:
        """Gestion client non trouvé"""
        return self.response_builder.build_error_response(
            "Client non trouvé",
            f"Le client '{client_name}' n'a pas été trouvé dans les bases de données",
            context={"client_name": client_name, "error_type": "client_not_found"}
        )
    
    def handle_client_error(self, error: str) -> Dict[str, Any]:
        """Gestion d'erreur client générale"""
        return self.response_builder.build_error_response(
            "Erreur client",
            f"Erreur lors du traitement du client: {error}",
            context={"error_type": "client_processing"}
        )
    
    def handle_draft_error(self, error: str) -> Dict[str, Any]:
        """Gestion d'erreur mode draft"""
        return self.response_builder.build_error_response(
            "Erreur mode draft",
            f"Erreur lors de la génération du draft: {error}",
            context={"error_type": "draft_generation"}
        )
    
    def handle_final_error(self, error: str) -> Dict[str, Any]:
        """Gestion d'erreur mode final"""
        return self.response_builder.build_error_response(
            "Erreur génération finale",
            f"Erreur lors de la génération finale: {error}",
            context={"error_type": "final_generation"}
        )

class CacheUtils:
    """Utilitaires de cache communs"""
    
    @staticmethod
    def generate_cache_key(prefix: str, **kwargs) -> str:
        """Génération de clé de cache standardisée"""
        params = "_".join(f"{k}_{v}" for k, v in sorted(kwargs.items()))
        return f"{prefix}:{params}".lower()
    
    @staticmethod
    def is_cache_expired(timestamp: datetime, ttl_seconds: int) -> bool:
        """Vérification expiration cache"""
        return (datetime.now() - timestamp).total_seconds() > ttl_seconds
    
    @staticmethod
    def clean_cache_key(key: str) -> str:
        """Nettoyage clé de cache"""
        # Suppression des caractères spéciaux
        return re.sub(r'[^a-zA-Z0-9:_-]', '', key)

class StringUtils:
    """Utilitaires de traitement de chaînes"""
    
    @staticmethod
    def truncate_string(text: str, max_length: int = 100) -> str:
        """Troncature de chaîne avec ellipse"""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Nettoyage nom de fichier"""
        # Suppression des caractères interdits
        clean_name = re.sub(r'[<>:"/\\|?*]', '', filename)
        return clean_name.strip()
    
    @staticmethod
    def format_currency(amount: float, currency: str = "EUR") -> str:
        """Formatage monétaire"""
        if currency == "EUR":
            return f"{amount:,.2f}€".replace(',', ' ')
        elif currency == "USD":
            return f"${amount:,.2f}"
        else:
            return f"{amount:,.2f} {currency}"
    
    @staticmethod
    def pluralize(count: int, singular: str, plural: str = None) -> str:
        """Pluralisation automatique"""
        if plural is None:
            plural = singular + "s"
        
        return f"{count} {singular if count == 1 else plural}"