# main.py - VERSION CORRIGÉE AVEC SYNCHRONISATION
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from routes.routes_quote_details import router as quote_details_router
from routes.routes_progress import router as progress_router
from routes import routes_suggestions
from typing import List, Dict

OPTIONAL_MODULES = {
    'sync': 'routes.routes_sync',
    'products': 'routes.routes_products',
    'claude': 'routes.routes_claude',
    'salesforce':'routes.routes_salesforce',
    'sap':'routes.routes_sap',
    'devis':'routes.routes_devis',
    'assistant':'routes.routes_intelligent_assistant',
    'clients':'routes.routes_clients'
}

def load_optional_modules():
    loaded = {}
    for name, module_path in OPTIONAL_MODULES.items():
        try:
            loaded[name] = importlib.import_module(module_path)
        except ImportError as e:
            logger.warning(f"Module {name} non disponible: {e}")
    return loaded

        
# Créer l'application FastAPI
app = FastAPI(
    title="NOVA Middleware",
    description="Middleware d'intégration LLM - SAP - Salesforce",
    version="1.0.0"
)
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["178.33.233.120", "localhost", "127.0.0.1"]
)
# Monter le dossier static pour servir les fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    print("⚠️ Dossier static non trouvé")

# Inclusion des routers disponibles
if claude_available:
    app.include_router(claude_router, tags=["Claude"])
    print("✅ Routes Claude chargées")

if salesforce_available:
    app.include_router(salesforce_router, tags=["Salesforce"])
    print("✅ Routes Salesforce chargées")

if sap_available:
    app.include_router(sap_router, tags=["SAP"])
    print("✅ Routes SAP chargées")

if devis_available:
    app.include_router(devis_router, tags=["Devis"])
    print("✅ Routes Devis chargées")

if clients_available:
    app.include_router(clients_router, prefix="/clients", tags=["Clients"])
    print("✅ Routes Clients chargées")

if sync_available:
    app.include_router(sync_router, prefix="/sync", tags=["Synchronisation"])
    print("✅ Routes Synchronisation chargées")

if products_available:
    app.include_router(products_router, prefix="/products", tags=["Produits"])
    print("✅ Routes Produits chargées")

# Intégration de l'assistant intelligent
if intelligent_assistant_available:
    from routes.routes_intelligent_assistant import router as assistant_router
    app.include_router(assistant_router, prefix="/api/assistant", tags=["Assistant Intelligent"])
    print("✅ Assistant Intelligent intégré avec préfixe /api/assistant")

app.include_router(quote_details_router, tags=["Quote Details"])
print("✅ Routes Devis chargées")
app.include_router(progress_router, prefix="/progress", tags=["progress"])
print("✅ Routes Progression chargées")
app.include_router(devis_router, tags=["Devis Generated"])
app.include_router(clients_router, prefix="/clients", tags=["Clients Generated"])
app.include_router(routes_suggestions.router)   

@app.get("/")
def root():
    if intelligent_assistant_available:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/api/assistant/interface")
    else:
        return {
            "message": "NOVA Middleware actif",
            "version": "1.0.0",
            "status": "operational",
            "services": {
                "claude": claude_available,
                "salesforce": salesforce_available,
                "sap": sap_available,
                "devis": devis_available,
                "clients": clients_available,
                "sync": sync_available,
                "products": products_available,
                "assistant": intelligent_assistant_available
            }
        }

@app.get("/health", tags=["Health"])
def health_check():
    """Contrôle de santé détaillé"""
    return {
        "status": "healthy",
        "timestamp": "2025-06-04T16:00:00Z",
        "services": {
            "claude_routes": "available" if claude_available else "unavailable",
            "salesforce_routes": "available" if salesforce_available else "unavailable", 
            "sap_routes": "available" if sap_available else "unavailable",
            "devis_workflow": "available" if devis_available else "unavailable",
            "clients_management": "available" if clients_available else "unavailable",
            "sync_module": "available" if sync_available else "unavailable"
        }
    }
class ProductProcessor:
    
    def process_products(self, products_info: List[Dict]) -> List[Dict]:
        """
        🔧 TRAITEMENT ROBUSTE DES DONNÉES PRODUIT
        """
        processed_products = []
        
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
                unit_price = float(product.get("unit_price") or product.get("Price", 0))
                line_total = quantity * unit_price
                
                # 🔧 GESTION DU STOCK
                stock_available = product.get("stock", product.get("QuantityOnStock", 0))
                is_available = quantity <= stock_available if stock_available > 0 else False

                product_data = {
                    "code": product_code,
                    "name": product_name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "stock_available": stock_available,
                    "is_available": is_available,
                    "status": "available" if is_available else "insufficient_stock"
                }
                
                processed_products.append(product_data)
            
            else:
                # Produit avec erreur, ajouter dans la liste pour traitement
                processed_products.append({
                    "error": True,
                    "message": product.get("error", "Erreur inconnue"),
                    "original_data": product
                })
        
        return processed_products
if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage de NOVA Middleware...")
    print("📝 Documentation API : http://localhost:8000/docs")
    print("🏥 Contrôle santé : http://localhost:8000/health")
    if os.path.exists("static"):
        print("🎮 Démo devis : http://178.33.233.120:8000/api/assistant/interface")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
