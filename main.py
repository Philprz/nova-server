import os
import logging
import time
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from services.module_loader import ModuleLoader, ModuleConfig
security = HTTPBasic()
# Configuration logging selon charte IT SPIRIT
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nova_server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)



def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "nova2025":
        raise HTTPException(status_code=401)
    return credentials.username
# Configuration des modules avec préfixes distincts
MODULES_CONFIG = {
    'sync': ModuleConfig('routes.routes_sync', '/sync', ['Synchronisation']),
    'products': ModuleConfig('routes.routes_products', '/products', ['Produits']),
    'devis': ModuleConfig('routes.routes_devis', '/devis', ['Devis']),
    'assistant': ModuleConfig('routes.routes_intelligent_assistant', '/api/assistant', ['Assistant Intelligent']),
    'clients': ModuleConfig('routes.routes_clients', '/clients', ['Clients']),
    'companies': ModuleConfig('routes.routes_company_search', '/companies', ['Recherche d\'entreprises'])  # NOUVEAU
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

# ✅ AJOUT : Route de compatibilité unifiée
@app.post("/generate_quote")
async def generate_quote_unified(request: dict):
    """
    🎯 Route unifiée pour éviter les conflits
    Redirige vers le bon endpoint selon le contexte
    """
    try:
        # Vérifier le format de la requête
        prompt = request.get("prompt", "").strip()
        draft_mode = request.get("draft_mode", False)

        if not prompt:
            return {"success": False, "error": "Prompt manquant"}

        # Utiliser directement le service chat
        from routes.routes_intelligent_assistant import ChatMessage, chat_with_nova

        # Créer la requête formatée
        message_data = ChatMessage(message=prompt)

        # Exécuter la génération
        result = await chat_with_nova(message_data)

        # Convertir le résultat en dict pour la réponse
        if hasattr(result, 'dict'):
            return result.dict()
        else:
            return result

    except Exception as e:
        print(f"❌ Erreur route unifiée: {str(e)}")
        return {
            "success": False,
            "error": f"Erreur serveur: {str(e)}"
        }
# NOUVEAU : Route d'intégration pour l'enrichissement client
@app.post("/enrich_client_with_company_data")
async def enrich_client_with_company_data(request: dict):
    """
    🔍 Enrichit les données client avec l'agent de recherche d'entreprises
    Intégration directe avec le workflow NOVA
    """
    try:
        from services.company_search_service import company_search_service
        
        client_data = request.get('client_data', {})
        if not client_data:
            return {
                'success': False,
                'error': 'client_data requis'
            }
        
        # Enrichissement via l'agent
        enriched_data = await company_search_service.enrich_client_data(client_data)
        
        return {
            'success': True,
            'original_data': client_data,
            'enriched_data': enriched_data,
            'enrichment_applied': 'enriched_data' in enriched_data
        }
        
    except Exception as e:
        logger.error(f"Erreur enrichissement client: {e}")
        return {
            'success': False,
            'error': str(e)
        }

# NOUVEAU : Route de validation SIREN intégrée
@app.post("/validate_company_siren")
async def validate_company_siren(request: dict):
    """
    ✅ Valide un SIREN d'entreprise
    Intégration directe avec le workflow NOVA
    """
    try:
        from services.company_search_service import company_search_service
        
        siren = request.get('siren')
        if not siren:
            return {
                'valid': False,
                'error': 'SIREN requis'
            }
        
        # Validation via l'agent
        validation_result = await company_search_service.validate_siren(siren)
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Erreur validation SIREN: {e}")
        return {
            'valid': False,
            'error': str(e)
        }

# NOUVEAU : Route de recherche rapide pour suggestions
@app.get("/quick_company_search/{query}")
async def quick_company_search(query: str):
    """
    🔍 Recherche rapide d'entreprise pour suggestions
    Intégration directe avec le workflow NOVA
    """
    try:
        from services.company_search_service import company_search_service
        
        # Recherche rapide
        search_result = await company_search_service.search_company(
            query=query,
            max_results=3
        )
        
        if search_result['success'] and search_result['companies']:
            return {
                'found': True,
                'companies': search_result['companies'],
                'count': len(search_result['companies'])
            }
        else:
            # Suggestions si pas de résultats
            suggestions = await company_search_service.get_suggestions(query)
            return {
                'found': False,
                'suggestions': suggestions
            }
        
    except Exception as e:
        logger.error(f"Erreur recherche rapide: {e}")
        return {
            'found': False,
            'error': str(e)
        }
# ✅ AJOUT : Route de diagnostic
@app.get("/diagnostic")
async def diagnostic():
    """
    🔍 Endpoint de diagnostic pour tester la connectivité
    """
    try:
        # Test des modules chargés
        loaded_modules = loader.get_loaded_modules()

        # Test des endpoints disponibles
        endpoints = []
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                endpoints.append(f"{list(route.methods)[0]} {route.path}")

        return {
            "status": "OK",
            "timestamp": str(datetime.now()),
            "loaded_modules": loaded_modules,
            "endpoints": endpoints,
            "health": "Server running"
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e)
        }

# ✅ AJOUT : Interface de diagnostic
@app.get("/diagnostic/interface", response_class=HTMLResponse)
async def diagnostic_interface():
    """
    🔍 Interface de diagnostic HTML
    """
    # Rediriger vers l'interface de diagnostic statique
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/diagnostic.html")

# ✅ AJOUT : Middleware de logging des requêtes
@app.middleware("http")
async def log_requests(request, call_next):
    """
    📝 Middleware pour logger toutes les requêtes
    """
    start_time = time.time()

    # Logger la requête entrante
    print(f"🔄 {request.method} {request.url}")

    # Traiter la requête
    response = await call_next(request)

    # Logger la réponse
    process_time = time.time() - start_time
    print(f"✅ {request.method} {request.url} - {response.status_code} - {process_time:.2f}s")

    return response

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
