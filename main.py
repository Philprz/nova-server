import os
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBasic
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from services.module_loader import ModuleLoader, ModuleConfig
import dotenv
# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nova_server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Configuration des modules
MODULES_CONFIG = {
    'sync': ModuleConfig('routes.routes_sync', '/sync', ['Synchronisation']),
    'products': ModuleConfig('routes.routes_products', '/products', ['Produits']),
    'devis': ModuleConfig('routes.routes_devis', '/devis', ['Devis']),
    'assistant': ModuleConfig('routes.routes_intelligent_assistant', '/api/assistant', ['Assistant Intelligent']),
    'clients': ModuleConfig('routes.routes_clients', '/clients', ['Clients']),
    'companies': ModuleConfig('routes.routes_company_search', '/companies', ['Recherche d\'entreprises']),
    'progress': ModuleConfig('routes.routes_progress', '/progress', ['Progress']),
    'websocket': ModuleConfig('routes.routes_websocket', '', ['WebSocket'])
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code de démarrage
    logger.info("Démarrage du serveur NOVA...")
    # Vérifier les API keys
    if not os.getenv("INSEE_API_KEY"):
        logger.warning("INSEE_API_KEY non configurée - enrichissement client limité")

    if not os.getenv("PAPPERS_API_KEY"):
        logger.warning("PAPPERS_API_KEY non configurée - enrichissement client limité")

    # Initialiser le service d'enrichissement
    logger.info("Service d'enrichissement initialisé")

    # Nettoyer les anciennes tâches
    from services.progress_tracker import progress_tracker
    cleaned = progress_tracker.cleanup_old_tasks(max_age_hours=24)
    logger.info(f"Nettoyage: {cleaned} tâches anciennes supprimées")

    yield

    # Code d'arrêt
    logger.info("Arrêt du serveur NOVA...")

# Création de l'application FastAPI
app = FastAPI(
    title="NOVA Middleware",
    description="Middleware d'intégration LLM - SAP - Salesforce",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)
# Import WebSocket
from routes.routes_websocket import websocket_manager

# Rendre websocket_manager disponible globalement
app.state.websocket_manager = websocket_manager
# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de sécurité
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["178.33.233.120", "localhost", "127.0.0.1", "*"]
)

# Fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Chargement des modules
loader = ModuleLoader()
loader.load_modules(MODULES_CONFIG)
loader.register_to_fastapi(app)

# =============================================
# ENDPOINTS PRINCIPAUX OBLIGATOIRES
# =============================================
@app.get("/interface/itspirit")
async def interface_itspirit():
    return FileResponse("templates/nova_interface_final.html")
@app.get("/health")
async def health_check():
    """Endpoint de santé du serveur"""
    try:
        # Vérifier les modules chargés
        loaded_modules = loader.get_loaded_modules()
        return {
            "status": "healthy",
            "loaded_modules": loaded_modules,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erreur lors du health check: {str(e)}")
        raise HTTPException
# Route pour la nouvelle interface
@app.get("/interface/v3")
async def get_interface_v3():
    """Sert la nouvelle interface v3"""
    return FileResponse("templates/nova_interface_v3.html")



@app.get("/")
def root():
    """Point d'entrée principal"""
    return {
        "message": "NOVA Middleware actif",
        "version": "1.0.0", 
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "interface_url": "/api/assistant/interface",
        "documentation": "/docs"
    }

@app.get("/health")
async def health_check():
    """Endpoint de santé du serveur"""
    try:
        # Vérifier les modules chargés
        loaded_modules = loader.get_loaded_modules()
        
        # Vérifier les services critiques
        services_status = {
            "database": "unknown",
            "mcp": "unknown", 
            "progress_tracker": "unknown",
            "modules": loaded_modules
        }
        
        # Test simple de la base de données
        try:
            from services.database import get_database_status
            services_status["database"] = get_database_status()
        except:
            services_status["database"] = "error"
            
        # Test du MCP
        try:
            from services.mcp_connector import MCPConnector
            services_status["mcp"] = "ready"
        except:
            services_status["mcp"] = "error"
            
        # Test progress tracker
        try:
            from services.progress_tracker import progress_tracker
            services_status["progress_tracker"] = "active"
        except:
            services_status["progress_tracker"] = "error"
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "services": services_status,
            "uptime": "running"
        }
    except Exception as e:
        logger.error(f"Erreur health check: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/diagnostic")
async def diagnostic():
    """Diagnostic complet du système"""
    try:
        # Modules chargés
        loaded_modules = loader.get_loaded_modules()
        
        # Endpoints disponibles
        endpoints = []
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                methods = list(route.methods) if route.methods else ['GET']
                endpoints.append(f"{methods[0]} {route.path}")
        
        # Statistiques
        stats = {
            "total_endpoints": len(endpoints),
            "loaded_modules": len(loaded_modules),
            "static_files": os.path.exists("static"),
            "log_file": os.path.exists("nova_server.log")
        }
        
        return {
            "status": "OK",
            "timestamp": datetime.now().isoformat(),
            "loaded_modules": loaded_modules,
            "endpoints": sorted(endpoints),
            "statistics": stats,
            "environment": {
                "python_version": os.sys.version,
                "working_directory": os.getcwd(),
                "environment_variables": {
                    "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else "NOT_SET",
                    "ANTHROPIC_API_KEY": "***" if os.getenv("ANTHROPIC_API_KEY") else "NOT_SET"
                }
            }
        }
    except Exception as e:
        logger.error(f"Erreur diagnostic: {e}")
        return {
            "status": "ERROR",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# =============================================
# ENDPOINTS DE COMPATIBILITÉ
# =============================================

@app.post("/generate_quote")
async def generate_quote_unified(request: dict):
    """Route unifiée pour la génération de devis"""
    try:
        prompt = request.get("prompt", "").strip()
        draft_mode = request.get("draft_mode", False)
        
        if not prompt:
            return {"success": False, "error": "Prompt manquant"}
        
        # Rediriger vers le bon endpoint selon disponibilité
        if 'progress' in loader.get_loaded_modules():
            # Mode avec progress tracking
            from routes.routes_progress import generate_quote_legacy
            return await generate_quote_legacy(request, None)
        elif 'assistant' in loader.get_loaded_modules():
            # Mode assistant direct
            from routes.routes_intelligent_assistant import chat_with_nova, ChatMessage
            message_data = ChatMessage(message=prompt)
            result = await chat_with_nova(message_data)
            return result.dict() if hasattr(result, 'dict') else result
        else:
            # Mode fallback
            return {
                "success": False,
                "error": "Aucun module de génération de devis disponible"
            }
    except Exception as e:
        logger.error(f"Erreur generate_quote_unified: {e}")
        return {
            "success": False,
            "error": f"Erreur serveur: {str(e)}"
        }

@app.post("/api/assistant/chat")
async def chat_fallback(request: dict):
    """Endpoint de fallback pour le chat"""
    try:
        if 'assistant' in loader.get_loaded_modules():
            from routes.routes_intelligent_assistant import chat_with_nova, ChatMessage
            message_data = ChatMessage(message=request.get("message", ""))
            result = await chat_with_nova(message_data)
            return result.dict() if hasattr(result, 'dict') else result
        else:
            return {
                "success": False,
                "response": {
                    "type": "error",
                    "message": "Module assistant non disponible"
                }
            }
    except Exception as e:
        logger.error(f"Erreur chat_fallback: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/assistant/interface")
async def assistant_interface():
    """Interface assistant - fallback"""
    try:
        # Essayer de servir l'interface depuis le module assistant
        if 'assistant' in loader.get_loaded_modules():
            from routes.routes_intelligent_assistant import intelligent_interface
            return await intelligent_interface()
        else:
            # Fallback vers l'interface statique
            if os.path.exists("static/nova_interface.html"):
                with open("static/nova_interface.html", "r", encoding="utf-8") as f:
                    return HTMLResponse(content=f.read())
            else:
                return HTMLResponse(content="""
                <!DOCTYPE html>
                <html>
                <head><title>NOVA Interface</title></head>
                <body>
                    <h1>NOVA Interface</h1>
                    <p>Interface temporaire - Module assistant en cours de chargement</p>
                    <p><a href="/docs">Documentation API</a></p>
                    <p><a href="/diagnostic">Diagnostic système</a></p>
                </body>
                </html>
                """)
    except Exception as e:
        logger.error(f"Erreur assistant_interface: {e}")
        return HTMLResponse(content=f"<h1>Erreur</h1><p>{str(e)}</p>")

# =============================================
# ENDPOINTS DE LISTE DES DEVIS BROUILLONS
# =============================================

@app.get("/list_draft_quotes")
async def list_draft_quotes():
    """Liste les devis en brouillon"""
    try:
        # Essayer d'utiliser le service SAP
        from services.mcp_connector import MCPConnector
        
        sap_result = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/Quotations?$filter=DocumentStatus eq 'bost_Open'&$orderby=DocDate desc",
            "method": "GET"
        })
        
        if "error" not in sap_result:
            draft_quotes = sap_result.get('value', [])
            return {
                "success": True,
                "count": len(draft_quotes),
                "draft_quotes": draft_quotes[:10]  # Limiter à 10
            }
        else:
            return {
                "success": True,
                "count": 0,
                "draft_quotes": [],
                "message": "Aucun devis brouillon trouvé"
            }
    except Exception as e:
        logger.error(f"Erreur list_draft_quotes: {e}")
        return {
            "success": False,
            "error": str(e),
            "count": 0,
            "draft_quotes": []
        }

@app.post("/validate_quote")
async def validate_quote(request: dict):
    """Valide un devis brouillon"""
    try:
        doc_entry = request.get("doc_entry")
        if not doc_entry:
            return {"success": False, "error": "doc_entry manquant"}
        
        # Implémenter la validation via SAP
        from services.mcp_connector import MCPConnector
        
        # Changer le statut du devis à "valide"
        sap_result = await MCPConnector.call_sap_mcp("sap_update", {
            "endpoint": f"/Quotations({doc_entry})",
            "method": "PATCH",
            "data": {
                "DocumentStatus": "bost_Close"
            }
        })
        
        if "error" not in sap_result:
            return {
                "success": True,
                "message": f"Devis {doc_entry} validé avec succès"
            }
        else:
            return {
                "success": False,
                "error": sap_result.get("error", "Erreur inconnue")
            }
    except Exception as e:
        logger.error(f"Erreur validate_quote: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# =============================================
# MIDDLEWARE DE LOGGING
# =============================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log toutes les requêtes"""
    start_time = time.time()
    
    # Log de la requête entrante
    logger.info(f"🔄 {request.method} {request.url}")
    
    # Traitement de la requête
    response = await call_next(request)
    
    # Log de la réponse
    process_time = time.time() - start_time
    logger.info(f"✅ {request.method} {request.url} - {response.status_code} - {process_time:.3f}s")
    
    return response

# =============================================
# INCLUSION DES ROUTES OBLIGATOIRES
# =============================================

# Routes toujours présentes
try:
    from routes.routes_quote_details import router as quote_details_router
    app.include_router(quote_details_router, tags=["Quote Details"])
except ImportError:
    logger.warning("Module routes_quote_details non disponible")

try:
    from routes.routes_progress import router as progress_router
    app.include_router(progress_router, prefix="/progress", tags=["Progress"])
except ImportError:
    logger.warning("Module routes_progress non disponible")

try:
    from routes import routes_suggestions
    app.include_router(routes_suggestions.router, tags=["Suggestions"])
except ImportError:
    logger.warning("Module routes_suggestions non disponible")

# =============================================
# GESTION DES ERREURS
# =============================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Gestionnaire d'erreurs HTTP personnalisé"""
    logger.error(f"HTTP {exc.status_code}: {exc.detail} - {request.method} {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url)
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Gestionnaire d'erreurs générales"""
    logger.error(f"Erreur non gérée: {str(exc)} - {request.method} {request.url}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Erreur interne du serveur",
            "details": str(exc),
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url)
        }
    )

# =============================================
# POINT D'ENTRÉE
# =============================================

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Démarrage du serveur NOVA")
    uvicorn.run(app, host="0.0.0.0", port=8000)
