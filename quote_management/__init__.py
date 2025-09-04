# Module de gestion des devis SAP/Salesforce

from .quote_manager import QuoteManager, Quote, QuoteStatus
from .api_routes import router

__version__ = "1.0.0"
__all__ = ["QuoteManager", "Quote", "QuoteStatus", "router"]