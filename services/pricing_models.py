"""
Modèles de données pour le moteur de pricing intelligent RONDOT-SAS
Conforme à l'organigramme des 4 CAS déterministes
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


class PricingCaseType(str, Enum):
    """Type de CAS de pricing selon organigramme RONDOT-SAS"""
    SAP_FUNCTION = "SAP_FUNCTION"  # Prix calculé par fonction SAP (prioritaire)
    CAS_1_HC = "CAS_1_HC"      # Historique Client - Prix stable
    CAS_2_HCM = "CAS_2_HCM"    # Historique Client - Prix Modifié
    CAS_3_HA = "CAS_3_HA"      # Historique Autres clients
    CAS_4_NP = "CAS_4_NP"      # Nouveau Produit
    CAS_MANUAL = "CAS_MANUAL"  # Prix manuel (validation commerciale)


class SupplierPriceVariation(BaseModel):
    """Détection variation prix fournisseur"""
    previous_price: float = Field(..., description="Prix fournisseur précédent")
    current_price: float = Field(..., description="Prix fournisseur actuel")
    variation_percent: float = Field(default=0.0, description="Variation en pourcentage")
    is_stable: bool = Field(default=True, description="Stable si variation < 5%")
    last_price_date: Optional[date] = Field(None, description="Date dernier prix connu")

    @field_validator('variation_percent', mode='before')
    @classmethod
    def calculate_variation(cls, v, info):
        """Calcul automatique de la variation"""
        data = info.data
        if 'previous_price' in data and 'current_price' in data:
            prev = data['previous_price']
            curr = data['current_price']
            if prev > 0:
                return round(((curr - prev) / prev) * 100, 2)
        return 0.0

    @field_validator('is_stable', mode='before')
    @classmethod
    def check_stability(cls, v, info):
        """Vérification stabilité (seuil 5%)"""
        data = info.data
        if 'variation_percent' in data:
            return abs(data['variation_percent']) < 5.0
        return True


class SalesHistoryEntry(BaseModel):
    """Entrée historique vente client"""
    doc_entry: int = Field(..., description="DocEntry de la facture SAP")
    doc_num: int = Field(..., description="DocNum de la facture")
    doc_date: date = Field(..., description="Date de la facture")
    card_code: str = Field(..., description="Code client SAP")
    item_code: str = Field(..., description="Code article")
    quantity: float = Field(..., description="Quantité vendue")
    unit_price: float = Field(..., description="Prix unitaire vendu")
    line_total: float = Field(..., description="Montant total ligne")
    discount_percent: float = Field(default=0.0, description="Remise appliquée")

    class Config:
        json_schema_extra = {
            "example": {
                "doc_entry": 12345,
                "doc_num": 1000123,
                "doc_date": "2025-01-15",
                "card_code": "C00001",
                "item_code": "REF-001",
                "quantity": 10,
                "unit_price": 150.00,
                "line_total": 1500.00,
                "discount_percent": 0.0
            }
        }


class PricingContext(BaseModel):
    """Contexte d'entrée pour calcul pricing"""
    item_code: str = Field(..., description="Code article")
    card_code: str = Field(..., description="Code client")
    quantity: float = Field(default=1.0, description="Quantité demandée")
    supplier_price: Optional[float] = Field(None, description="Prix fournisseur actuel")

    # Métadonnées enrichies (depuis supplier_tariffs_db)
    delivery_days: Optional[int] = None
    transport_cost: Optional[float] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None

    # Options de calcul
    force_recalculate: bool = Field(default=False, description="Forcer recalcul même si stable")
    apply_margin: float = Field(default=45.0, description="Marge à appliquer (défaut 45%)")

    class Config:
        json_schema_extra = {
            "example": {
                "item_code": "REF-001",
                "card_code": "C00001",
                "quantity": 10,
                "supplier_price": 100.0,
                "apply_margin": 45.0
            }
        }


class PricingDecision(BaseModel):
    """Décision de pricing avec traçabilité complète"""

    # Identification
    decision_id: str = Field(..., description="ID unique de décision (UUID)")
    item_code: str
    card_code: str
    quantity: float

    # CAS appliqué
    case_type: PricingCaseType = Field(..., description="CAS RONDOT-SAS appliqué")
    case_description: str = Field(..., description="Description du CAS")

    # Prix calculé
    calculated_price: float = Field(..., description="Prix unitaire calculé")
    line_total: float = Field(default=0.0, description="Montant total ligne")
    currency: str = Field(default="EUR")

    # Justification et traçabilité
    justification: str = Field(..., description="Justification détaillée de la décision")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Niveau de confiance (0-1)")

    # Données sources
    supplier_price: Optional[float] = Field(None, description="Prix fournisseur utilisé")
    margin_applied: Optional[float] = Field(None, description="Marge appliquée (%)")

    # Historique de référence
    last_sale_date: Optional[date] = Field(None, description="Date dernière vente")
    last_sale_price: Optional[float] = Field(None, description="Prix dernière vente")
    last_sale_doc_num: Optional[int] = Field(None, description="Numéro devis/facture référence")

    # Variation prix fournisseur (pour CAS 2)
    price_variation: Optional[SupplierPriceVariation] = None

    # Prix moyen autres clients (pour CAS 3)
    average_price_others: Optional[float] = None
    reference_sales_count: Optional[int] = Field(None, description="Nombre ventes référence")

    # Alertes et validation
    requires_validation: bool = Field(default=False, description="Validation commerciale requise")
    validation_reason: Optional[str] = Field(None, description="Raison validation requise")
    alerts: List[str] = Field(default_factory=list, description="Alertes associées")

    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="pricing_engine", description="Créateur décision")

    @field_validator('line_total', mode='before')
    @classmethod
    def calculate_line_total(cls, v, info):
        """Calcul automatique montant ligne"""
        data = info.data
        if 'calculated_price' in data and 'quantity' in data:
            return round(data['calculated_price'] * data['quantity'], 2)
        return v if v else 0.0

    class Config:
        json_schema_extra = {
            "example": {
                "decision_id": "550e8400-e29b-41d4-a716-446655440000",
                "item_code": "REF-001",
                "card_code": "C00001",
                "quantity": 10,
                "case_type": "CAS_1_HC",
                "case_description": "Historique client + Prix fournisseur stable",
                "calculated_price": 150.00,
                "line_total": 1500.00,
                "justification": "Reprise prix dernière vente (150.00 EUR) car variation < 5%",
                "confidence_score": 1.0,
                "supplier_price": 100.00,
                "margin_applied": 50.0,
                "last_sale_date": "2025-01-15",
                "last_sale_price": 150.00,
                "requires_validation": False
            }
        }


class PricingResult(BaseModel):
    """Résultat complet du moteur de pricing"""
    success: bool = Field(..., description="Succès du calcul")
    decision: Optional[PricingDecision] = None
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    # Performance
    processing_time_ms: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "decision": {"...": "voir PricingDecision"},
                "warnings": [],
                "processing_time_ms": 45.2
            }
        }


class WeightedSaleData(BaseModel):
    """Vente pondérée pour calcul prix moyen (CAS 3)"""
    card_code: str
    card_name: Optional[str] = None
    unit_price: float
    quantity: float
    sale_date: date
    weight: float = Field(default=1.0, description="Poids dans la moyenne (basé sur récence/quantité)")

    @field_validator('weight', mode='before')
    @classmethod
    def calculate_weight(cls, v, info):
        """Calcul poids basé sur récence"""
        data = info.data
        if 'sale_date' in data:
            days_old = (date.today() - data['sale_date']).days
            # Décroissance linéaire : 100% à J, 50% à 180j, 0% à 360j
            recency_weight = max(0, 1 - (days_old / 360))
            quantity_weight = min(1.0, data.get('quantity', 1) / 10)  # Normalisation quantité
            return round((recency_weight + quantity_weight) / 2, 3)
        return 1.0
