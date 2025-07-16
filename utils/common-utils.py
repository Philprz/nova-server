# utils/common_utils.py - NOUVEAU FICHIER
from typing import Dict, Any, Optional
from datetime import datetime
import logging

class ResponseBuilder:
    """Constructeur de réponses standardisées"""
    
    @staticmethod
    def build_error_response(error_title: str, error_message: str, 
                           context: Optional[Dict] = None) -> Dict[str, Any]:
        """UNE SEULE fonction pour toutes les erreurs"""
        return {
            "success": False,
            "error": error_message,
            "error_title": error_title,
            "timestamp": datetime.now().isoformat(),
            "context": context or {}
        }
    
    @staticmethod
    def build_success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
        """Réponse de succès standardisée"""
        return {
            "success": True,
            "data": data,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

class ValidationUtils:
    """Utilitaires de validation réutilisables"""
    
    @staticmethod
    def validate_phone_format(phone: str) -> bool:
        """Validation téléphone - factorisation"""
        # Logique existante de client_validator.py
        pass
    
    @staticmethod
    def validate_postal_code(postal_code: str, country: str) -> bool:
        """Validation code postal par pays - factorisation"""
        patterns = {
            "FR": r'^\d{5}$',
            "US": r'^\d{5}(-\d{4})?$',
            "UK": r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$'
        }
        return bool(re.match(patterns.get(country, r'.*'), postal_code))
