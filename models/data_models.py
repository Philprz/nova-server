# models/data_models.py
"""
Modèles de données typés pour remplacer Dict[str, Any]
Améliore la robustesse et la maintenabilité du code
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum

class QuoteStatus(Enum):
    """Statuts possibles d'un devis"""
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ValidationStatus(Enum):
    """Statuts de validation"""
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    PENDING = "pending"

class SystemSource(Enum):
    """Sources de données système"""
    SALESFORCE = "salesforce"
    SAP = "sap"
    CACHE = "cache"
    MANUAL = "manual"

@dataclass
class ClientData:
    """Modèle standardisé pour les clients"""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "FR"
    siret: Optional[str] = None
    
    # IDs systèmes
    salesforce_id: Optional[str] = None
    sap_code: Optional[str] = None
    
    # Métadonnées
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    source: SystemSource = SystemSource.MANUAL
    
    def __post_init__(self):
        """Validation et normalisation après création"""
        if self.name:
            self.name = self.name.strip()
        if self.email:
            self.email = self.email.strip().lower()
        if self.phone:
            self.phone = self.phone.strip()
        if self.country:
            self.country = self.country.upper()
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "city": self.city,
            "postal_code": self.postal_code,
            "country": self.country,
            "siret": self.siret,
            "salesforce_id": self.salesforce_id,
            "sap_code": self.sap_code,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "source": self.source.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClientData':
        """Création depuis un dictionnaire"""
        return cls(
            name=data.get("name", ""),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            city=data.get("city"),
            postal_code=data.get("postal_code"),
            country=data.get("country", "FR"),
            siret=data.get("siret"),
            salesforce_id=data.get("salesforce_id"),
            sap_code=data.get("sap_code"),
            source=SystemSource(data.get("source", "manual"))
        )
    
    def is_complete(self) -> bool:
        """Vérification si les données sont complètes"""
        required_fields = [self.name, self.email or self.phone]
        return all(field for field in required_fields)

@dataclass
class ProductData:
    """Modèle standardisé pour les produits"""
    code: str
    name: str
    price: float
    quantity: int = 1
    stock: int = 0
    available: bool = True
    
    # Métadonnées
    category: Optional[str] = None
    description: Optional[str] = None
    unit: str = "pcs"
    currency: str = "EUR"
    
    # IDs systèmes
    salesforce_id: Optional[str] = None
    sap_id: Optional[str] = None
    
    # Calculs
    line_total: Optional[float] = None
    
    def __post_init__(self):
        """Calculs automatiques après création"""
        if self.line_total is None:
            self.line_total = self.price * self.quantity
        
        # Validation
        if self.price < 0:
            raise ValueError("Le prix ne peut pas être négatif")
        if self.quantity < 0:
            raise ValueError("La quantité ne peut pas être négative")
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "quantity": self.quantity,
            "stock": self.stock,
            "available": self.available,
            "category": self.category,
            "description": self.description,
            "unit": self.unit,
            "currency": self.currency,
            "salesforce_id": self.salesforce_id,
            "sap_id": self.sap_id,
            "line_total": self.line_total
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProductData':
        """Création depuis un dictionnaire"""
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            price=float(data.get("price", 0)),
            quantity=int(data.get("quantity", 1)),
            stock=int(data.get("stock", 0)),
            available=data.get("available", True),
            category=data.get("category"),
            description=data.get("description"),
            unit=data.get("unit", "pcs"),
            currency=data.get("currency", "EUR"),
            salesforce_id=data.get("salesforce_id"),
            sap_id=data.get("sap_id")
        )
    
    def is_stock_sufficient(self) -> bool:
        """Vérification si le stock est suffisant"""
        return self.stock >= self.quantity
    
    def calculate_total(self) -> float:
        """Calcul du total ligne"""
        return self.price * self.quantity

@dataclass
class QuoteData:
    """Modèle standardisé pour les devis"""
    client: ClientData
    products: List[ProductData]
    total_amount: float = 0.0
    
    # Métadonnées
    quote_number: Optional[str] = None
    status: QuoteStatus = QuoteStatus.DRAFT
    currency: str = "EUR"
    
    # IDs systèmes
    sap_doc_entry: Optional[int] = None
    salesforce_opportunity_id: Optional[str] = None
    
    # Dates
    created_at: datetime = field(default_factory=datetime.now)
    valid_until: Optional[datetime] = None
    
    def __post_init__(self):
        """Calculs automatiques après création"""
        if self.total_amount == 0.0:
            self.total_amount = sum(product.calculate_total() for product in self.products)
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "client": self.client.to_dict(),
            "products": [product.to_dict() for product in self.products],
            "total_amount": self.total_amount,
            "quote_number": self.quote_number,
            "status": self.status.value,
            "currency": self.currency,
            "sap_doc_entry": self.sap_doc_entry,
            "salesforce_opportunity_id": self.salesforce_opportunity_id,
            "created_at": self.created_at.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QuoteData':
        """Création depuis un dictionnaire"""
        return cls(
            client=ClientData.from_dict(data.get("client", {})),
            products=[ProductData.from_dict(p) for p in data.get("products", [])],
            total_amount=float(data.get("total_amount", 0)),
            quote_number=data.get("quote_number"),
            status=QuoteStatus(data.get("status", "draft")),
            currency=data.get("currency", "EUR"),
            sap_doc_entry=data.get("sap_doc_entry"),
            salesforce_opportunity_id=data.get("salesforce_opportunity_id")
        )
    
    def get_products_count(self) -> int:
        """Nombre total de produits"""
        return len(self.products)
    
    def get_total_quantity(self) -> int:
        """Quantité totale de tous les produits"""
        return sum(product.quantity for product in self.products)
    
    def has_stock_issues(self) -> bool:
        """Vérification si des problèmes de stock existent"""
        return any(not product.is_stock_sufficient() for product in self.products)
    
    def get_stock_issues(self) -> List[ProductData]:
        """Liste des produits avec problèmes de stock"""
        return [product for product in self.products if not product.is_stock_sufficient()]

@dataclass
class ValidationResult:
    """Résultat de validation"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    enriched_data: Dict[str, Any] = field(default_factory=dict)
    duplicate_check: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, error: str):
        """Ajout d'une erreur"""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        """Ajout d'un avertissement"""
        self.warnings.append(warning)
    
    def add_suggestion(self, suggestion: str):
        """Ajout d'une suggestion"""
        self.suggestions.append(suggestion)
    
    def has_issues(self) -> bool:
        """Vérification si des problèmes existent"""
        return bool(self.errors or self.warnings)
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "enriched_data": self.enriched_data,
            "duplicate_check": self.duplicate_check
        }

@dataclass
class StockInfo:
    """Informations de stock"""
    product_code: str
    available_quantity: int
    reserved_quantity: int = 0
    incoming_quantity: int = 0
    
    def get_free_quantity(self) -> int:
        """Quantité disponible libre"""
        return self.available_quantity - self.reserved_quantity
    
    def is_sufficient(self, requested_quantity: int) -> bool:
        """Vérification si la quantité est suffisante"""
        return self.get_free_quantity() >= requested_quantity

@dataclass
class SuggestionItem:
    """Item de suggestion"""
    value: str
    score: float
    explanation: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "value": self.value,
            "score": self.score,
            "explanation": self.explanation,
            "metadata": self.metadata
        }

@dataclass
class TaskProgress:
    """Progression d'une tâche"""
    task_id: str
    status: str
    current_step: str
    progress_percentage: float
    steps_completed: List[str] = field(default_factory=list)
    steps_failed: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "current_step": self.current_step,
            "progress_percentage": self.progress_percentage,
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

@dataclass
class APIResponse:
    """Réponse API standardisée"""
    success: bool
    data: Optional[Any] = None
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Conversion en dictionnaire"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def success_response(cls, data: Any, message: str = "Success") -> 'APIResponse':
        """Création d'une réponse de succès"""
        return cls(success=True, data=data, message=message)
    
    @classmethod
    def error_response(cls, message: str, errors: List[str] = None) -> 'APIResponse':
        """Création d'une réponse d'erreur"""
        return cls(success=False, message=message, errors=errors or [])

# Fonctions utilitaires pour la conversion

def convert_dict_to_client_data(data: Dict[str, Any]) -> ClientData:
    """Conversion Dict vers ClientData"""
    return ClientData.from_dict(data)

def convert_dict_to_product_data(data: Dict[str, Any]) -> ProductData:
    """Conversion Dict vers ProductData"""
    return ProductData.from_dict(data)

def convert_dict_to_quote_data(data: Dict[str, Any]) -> QuoteData:
    """Conversion Dict vers QuoteData"""
    return QuoteData.from_dict(data)

def convert_legacy_client_response(legacy_response: Dict[str, Any]) -> ClientData:
    """Conversion des anciennes réponses client vers ClientData"""
    if "data" in legacy_response and isinstance(legacy_response["data"], dict):
        client_data = legacy_response["data"]
        return ClientData(
            name=client_data.get("Name", ""),
            email=client_data.get("Email"),
            phone=client_data.get("Phone"),
            address=client_data.get("BillingStreet"),
            city=client_data.get("BillingCity"),
            postal_code=client_data.get("BillingPostalCode"),
            country=client_data.get("BillingCountry", "FR"),
            salesforce_id=client_data.get("Id"),
            sap_code=client_data.get("CardCode"),
            source=SystemSource.SALESFORCE if client_data.get("Id") else SystemSource.SAP
        )
    return ClientData(name="Unknown")

def convert_legacy_product_response(legacy_response: Dict[str, Any]) -> ProductData:
    """Conversion des anciennes réponses produit vers ProductData"""
    return ProductData(
        code=legacy_response.get("ItemCode", ""),
        name=legacy_response.get("ItemName", ""),
        price=float(legacy_response.get("UnitPrice", 0)),
        stock=int(legacy_response.get("QuantityOnStock", 0)),
        available=legacy_response.get("InStock", False),
        sap_id=legacy_response.get("ItemCode")
    )

# Validation des modèles

class ModelValidator:
    """Validateur pour les modèles de données"""
    
    @staticmethod
    def validate_client_data(client: ClientData) -> ValidationResult:
        """Validation d'un ClientData"""
        result = ValidationResult(is_valid=True)
        
        if not client.name or len(client.name.strip()) < 2:
            result.add_error("Le nom du client est obligatoire (min 2 caractères)")
        
        if not client.email and not client.phone:
            result.add_error("Au moins un moyen de contact est requis (email ou téléphone)")
        
        if client.email and "@" not in client.email:
            result.add_error("Format d'email invalide")
        
        if client.country and len(client.country) != 2:
            result.add_warning("Le code pays devrait faire 2 caractères")
        
        return result
    
    @staticmethod
    def validate_product_data(product: ProductData) -> ValidationResult:
        """Validation d'un ProductData"""
        result = ValidationResult(is_valid=True)
        
        if not product.code or len(product.code.strip()) < 1:
            result.add_error("Le code produit est obligatoire")
        
        if not product.name or len(product.name.strip()) < 2:
            result.add_error("Le nom du produit est obligatoire")
        
        if product.price < 0:
            result.add_error("Le prix ne peut pas être négatif")
        
        if product.quantity < 1:
            result.add_error("La quantité doit être au moins 1")
        
        if product.stock < 0:
            result.add_warning("Stock négatif détecté")
        
        if not product.is_stock_sufficient():
            result.add_warning(f"Stock insuffisant: {product.stock} disponible, {product.quantity} demandé")
        
        return result
    
    @staticmethod
    def validate_quote_data(quote: QuoteData) -> ValidationResult:
        """Validation d'un QuoteData"""
        result = ValidationResult(is_valid=True)
        
        # Validation client
        client_validation = ModelValidator.validate_client_data(quote.client)
        result.errors.extend(client_validation.errors)
        result.warnings.extend(client_validation.warnings)
        
        # Validation produits
        if not quote.products:
            result.add_error("Au moins un produit est requis")
        
        for product in quote.products:
            product_validation = ModelValidator.validate_product_data(product)
            result.errors.extend(product_validation.errors)
            result.warnings.extend(product_validation.warnings)
        
        # Validation montant
        calculated_total = sum(product.calculate_total() for product in quote.products)
        if abs(quote.total_amount - calculated_total) > 0.01:
            result.add_warning("Le montant total ne correspond pas à la somme des lignes")
        
        return result