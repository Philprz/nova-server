# main.py - VERSION MINIMALISTE AVEC MODULE LOADER
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from services.module_loader import ModuleLoader, ModuleConfig

# Configuration des modules optionnels
MODULES_CONFIG = {
    'sync': ModuleConfig('routes.routes_sync', '/sync', ['Synchronisation']),
    'products': ModuleConfig('routes.routes_products', '/products', ['Produits']),
    'devis': ModuleConfig('routes.routes_devis', tags=['Devis']),
    'assistant': ModuleConfig('routes.routes_intelligent_assistant', '/api/assistant', ['Assistant Intelligent']),
    'clients': ModuleConfig('routes.routes_clients', '/clients', ['Clients'])
}

# Création de l'application
app = FastAPI(
    title="NOVA Middleware",
    description="Middleware d'intégration LLM - SAP - Salesforce",
    version="1.0.0"
)

# Middleware de sécurité
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["178.33.233.120", "localhost", "127.0.0.1"]
)

# Fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Chargement automatique des modules optionnels
loader = ModuleLoader()
loader.load_modules(MODULES_CONFIG)
loader.register_to_fastapi(app)

# Routes obligatoires (sans try/except car toujours présentes)
from routes.routes_quote_details import router as quote_details_router
from routes.routes_progress import router as progress_router  
from routes import routes_suggestions

app.include_router(quote_details_router, tags=["Quote Details"])
app.include_router(progress_router, prefix="/progress", tags=["Progress"])
app.include_router(routes_suggestions.router)

@app.get("/")
def root():
    """Point d'entrée avec redirection intelligente"""
    if 'assistant' in loader.get_loaded_modules():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/api/assistant/interface")
    
    return {
        "message": "NOVA Middleware actif",
        "version": "1.0.0",
        "status": "operational", 
        "services": loader.get_status()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)