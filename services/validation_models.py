"""
services/validation_models.py
Modèles Pydantic pour le workflow de validation commerciale
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ValidationStatus(str, Enum):
    """Statuts de validation possibles"""
    PENDING = "pending"  # En attente de validation
    APPROVED = "approved"  # Validé et approuvé
    REJECTED = "rejected"  # Rejeté
    MODIFIED = "modified"  # Modifié et validé
    EXPIRED = "expired"  # Expiré (délai dépassé)


class ValidationType(str, Enum):
    """Types de validation"""
    PRICING = "pricing"  # Validation pricing (CAS 2 & 4)
    DISCOUNT = "discount"  # Validation remise exceptionnelle
    MARGIN = "margin"  # Validation marge faible
    AMOUNT = "amount"  # Validation montant élevé
    CUSTOM = "custom"  # Validation personnalisée


class ValidationPriority(str, Enum):
    """Priorités de validation"""
    LOW = "low"  # Basse priorité
    MEDIUM = "medium"  # Priorité moyenne
    HIGH = "high"  # Haute priorité
    URGENT = "urgent"  # Urgent (> 10% variation)


class ValidationRequest(BaseModel):
    """Demande de validation commerciale"""
    validation_id: str = Field(description="ID unique de la validation")
    validation_type: ValidationType = Field(description="Type de validation")
    priority: ValidationPriority = Field(default=ValidationPriority.MEDIUM)

    # Contexte pricing
    decision_id: Optional[str] = Field(None, description="ID de la décision pricing associée")
    item_code: str = Field(description="Code article")
    item_name: Optional[str] = Field(None, description="Nom article")
    card_code: Optional[str] = Field(None, description="Code client")
    card_name: Optional[str] = Field(None, description="Nom client")
    quantity: float = Field(description="Quantité")

    # Prix et marges
    calculated_price: float = Field(description="Prix calculé automatiquement")
    supplier_price: Optional[float] = Field(None, description="Prix fournisseur")
    margin_applied: Optional[float] = Field(None, description="Marge appliquée (%)")

    # Contexte décisionnel
    case_type: Optional[str] = Field(None, description="Type de CAS pricing")
    justification: str = Field(description="Justification de la demande de validation")
    alerts: List[str] = Field(default_factory=list, description="Alertes générées")

    # Historique pour contexte
    last_sale_price: Optional[float] = Field(None, description="Prix dernière vente")
    last_sale_date: Optional[str] = Field(None, description="Date dernière vente")
    price_variation_percent: Optional[float] = Field(None, description="Variation prix (%)")

    # Métadonnées
    requested_by: str = Field(default="system", description="Demandé par (email/username)")
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="Date d'expiration")

    # Email source (si applicable)
    email_id: Optional[str] = Field(None, description="ID email source")
    email_subject: Optional[str] = Field(None, description="Sujet email")

    class Config:
        json_schema_extra = {
            "example": {
                "validation_id": "val_20260207_001",
                "validation_type": "pricing",
                "priority": "high",
                "item_code": "ITEM002",
                "item_name": "Composant électronique XYZ",
                "card_code": "C00001",
                "card_name": "ENTREPRISE CLIENT",
                "quantity": 5,
                "calculated_price": 174.00,
                "supplier_price": 120.00,
                "margin_applied": 45.0,
                "case_type": "CAS_2_HCM",
                "justification": "Variation prix fournisseur +14%",
                "alerts": ["⚠ ALERTE: Variation prix fournisseur +14.00%"],
                "last_sale_price": 150.00,
                "price_variation_percent": 16.0
            }
        }


class ValidationDecision(BaseModel):
    """Décision de validation prise par un commercial"""
    validation_id: str = Field(description="ID de la validation")
    status: ValidationStatus = Field(description="Statut de validation")

    # Décision
    approved_price: Optional[float] = Field(None, description="Prix approuvé (si différent du calculé)")
    approved_margin: Optional[float] = Field(None, description="Marge approuvée")

    # Justification
    validator_comment: Optional[str] = Field(None, description="Commentaire du validateur")
    rejection_reason: Optional[str] = Field(None, description="Raison du rejet")

    # Validateur
    validated_by: str = Field(description="Email/username du validateur")
    validated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "validation_id": "val_20260207_001",
                "status": "approved",
                "approved_price": 174.00,
                "validator_comment": "Prix accepté, variation justifiée par hausse matière première",
                "validated_by": "commercial@rondot-sas.fr"
            }
        }


class ValidationResult(BaseModel):
    """Résultat complet d'une validation"""
    request: ValidationRequest
    decision: Optional[ValidationDecision] = None
    status: ValidationStatus
    is_validated: bool = False

    # Métriques
    validation_time_seconds: Optional[int] = Field(None, description="Temps de validation (secondes)")

    class Config:
        json_schema_extra = {
            "example": {
                "request": {
                    "validation_id": "val_20260207_001",
                    "validation_type": "pricing",
                    "item_code": "ITEM002",
                    "calculated_price": 174.00
                },
                "decision": {
                    "validation_id": "val_20260207_001",
                    "status": "approved",
                    "validated_by": "commercial@rondot-sas.fr"
                },
                "status": "approved",
                "is_validated": True,
                "validation_time_seconds": 3600
            }
        }


class ValidationListFilter(BaseModel):
    """Filtres pour lister les validations"""
    status: Optional[ValidationStatus] = None
    validation_type: Optional[ValidationType] = None
    priority: Optional[ValidationPriority] = None
    item_code: Optional[str] = None
    card_code: Optional[str] = None
    validator: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = Field(default=50, le=200)
    offset: int = Field(default=0, ge=0)


class ValidationStatistics(BaseModel):
    """Statistiques de validation"""
    total_validations: int = 0
    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    modified_count: int = 0
    expired_count: int = 0

    # Temps moyens
    avg_validation_time_minutes: Optional[float] = None
    median_validation_time_minutes: Optional[float] = None

    # Répartition par type
    by_validation_type: Dict[str, int] = Field(default_factory=dict)
    by_priority: Dict[str, int] = Field(default_factory=dict)
    by_case_type: Dict[str, int] = Field(default_factory=dict)

    # Taux d'approbation
    approval_rate: Optional[float] = Field(None, description="Taux d'approbation (%)")
    rejection_rate: Optional[float] = Field(None, description="Taux de rejet (%)")

    # Période
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "total_validations": 150,
                "pending_count": 12,
                "approved_count": 120,
                "rejected_count": 15,
                "modified_count": 3,
                "avg_validation_time_minutes": 45.5,
                "by_validation_type": {"pricing": 130, "discount": 20},
                "approval_rate": 80.0,
                "rejection_rate": 10.0
            }
        }


class ValidationBulkAction(BaseModel):
    """Action en masse sur des validations"""
    validation_ids: List[str] = Field(description="IDs des validations")
    action: str = Field(description="Action à effectuer (approve, reject, expire)")
    comment: Optional[str] = Field(None, description="Commentaire")
    validated_by: str = Field(description="Email/username du validateur")

    # Pour approbation en masse
    use_calculated_price: bool = Field(default=True, description="Utiliser prix calculé")


class ValidationNotification(BaseModel):
    """Notification de validation"""
    validation_id: str
    notification_type: str = Field(description="Type: created, updated, approved, rejected, expired")
    recipient: str = Field(description="Email destinataire")
    subject: str
    message: str
    sent_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "validation_id": "val_20260207_001",
                "notification_type": "created",
                "recipient": "commercial@rondot-sas.fr",
                "subject": "⚠ Validation requise: ITEM002 pour CLIENT001",
                "message": "Une validation de pricing est requise pour l'article ITEM002..."
            }
        }


class ValidationWorkflowConfig(BaseModel):
    """Configuration du workflow de validation"""
    # Seuils de validation automatique
    auto_approve_threshold_percent: float = Field(default=3.0, description="Seuil auto-approbation (%)")
    auto_reject_threshold_percent: float = Field(default=50.0, description="Seuil auto-rejet (%)")

    # Délais
    default_expiration_hours: int = Field(default=48, description="Expiration par défaut (heures)")
    urgent_expiration_hours: int = Field(default=4, description="Expiration urgent (heures)")

    # Notifications
    notify_on_creation: bool = Field(default=True)
    notify_on_expiration: bool = Field(default=True)
    notification_email: str = Field(default="validation@rondot-sas.fr")

    # Priorités automatiques
    high_priority_threshold_percent: float = Field(default=10.0, description="> 10% = haute priorité")
    urgent_priority_threshold_percent: float = Field(default=20.0, description="> 20% = urgent")

    # Validateurs
    default_validators: List[str] = Field(default_factory=list, description="Emails validateurs par défaut")
    cas_2_validators: List[str] = Field(default_factory=list, description="Validateurs CAS 2")
    cas_4_validators: List[str] = Field(default_factory=list, description="Validateurs CAS 4")

    class Config:
        json_schema_extra = {
            "example": {
                "auto_approve_threshold_percent": 3.0,
                "default_expiration_hours": 48,
                "notification_email": "validation@rondot-sas.fr",
                "high_priority_threshold_percent": 10.0,
                "default_validators": [
                    "commercial1@rondot-sas.fr",
                    "commercial2@rondot-sas.fr"
                ]
            }
        }


class PriceUpdateRequest(BaseModel):
    """
    Requête de modification manuelle de prix
    Utilisé quand l'utilisateur ajuste le prix proposé par le moteur
    """
    decision_id: str = Field(description="ID de la décision pricing à modifier")
    new_price: float = Field(gt=0, description="Nouveau prix unitaire")
    modification_reason: Optional[str] = Field(None, description="Raison de la modification")
    modified_by: Optional[str] = Field(None, description="Email de l'utilisateur qui modifie")

    class Config:
        json_schema_extra = {
            "example": {
                "decision_id": "550e8400-e29b-41d4-a716-446655440000",
                "new_price": 165.50,
                "modification_reason": "Ajustement commercial sur demande client",
                "modified_by": "commercial@rondot-sas.fr"
            }
        }


class PriceUpdateResult(BaseModel):
    """Résultat d'une modification de prix"""
    success: bool
    decision_id: str
    old_price: float
    new_price: float
    margin_applied: float = Field(description="Nouvelle marge calculée (%)")
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "decision_id": "550e8400-e29b-41d4-a716-446655440000",
                "old_price": 150.00,
                "new_price": 165.50,
                "margin_applied": 48.5,
                "message": "Prix modifié avec succès"
            }
        }
