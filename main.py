
import uvicorn
import logging
import os
import sys
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from routes.routes_intelligent_assistant import router as assistant_router
from routes.routes_clients import router as clients_router  
from routes.routes_devis import router as devis_router
from routes.routes_progress import router as progress_router
from routes.routes_devis import router as quote_router
from routes.routes_clients import router as client_router


if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"    
# Configuration du logger pour éviter les erreurs d'emojis
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nova.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Variables globales
HEALTH_CHECK_RESULTS = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionnaire de cycle de vie de l'application"""
    global HEALTH_CHECK_RESULTS
    
    try:
        # 1. VÉRIFICATION DE SANTÉ AU DÉMARRAGE
        logger.info("=" * 50)
        logger.info("DEMARRAGE DE NOVA - Assistant IA pour Devis")
        logger.info("=" * 50)
        
        # Tests de santé
        from services.health_checker import HealthChecker
        health_checker = HealthChecker()
        
        logger.info("Execution des tests de sante...")
        await asyncio.sleep(2)  # <-- ⚠️ Ajout critique
        HEALTH_CHECK_RESULTS = await health_checker.run_full_health_check()
        
        # Affichage des résultats
        if HEALTH_CHECK_RESULTS["summary"]["success_rate"] < 50:
            logger.error("SYSTEME CRITIQUE NON OPERATIONNEL")
            logger.error("Impossible de demarrer NOVA avec des erreurs critiques")
        
        # Affichage des recommandations sans emojis
        logger.info("RECOMMANDATIONS:")
        for rec in HEALTH_CHECK_RESULTS["recommendations"]:
            # Suppression des emojis pour éviter les erreurs d'encodage
            clean_rec = rec.replace("🔧", "[FIX]").replace("🛠️", "[TOOL]")
            logger.info(f"   {clean_rec}")
        
        logger.info("=" * 50)
        
        # Démarrage en mode dégradé mais fonctionnel
        logger.warning("DEMARRAGE EN MODE DEGRADE")
        
        # 2. CHARGEMENT DES MODULES
        logger.info("Chargement des modules...")
        
        # Import du ModuleLoader
        from services.module_loader import ModuleLoader, ModuleConfig
        # Configuration simplifiée - seulement modules optionnels non critiques
        modules_config = {
            'sync': ModuleConfig('routes.routes_sync', '/sync', ['Synchronisation'], required=False),
            'products': ModuleConfig('routes.routes_products', '/products', ['Produits'], required=False)
        }

        # CORRECTION: ModuleLoader ne prend aucun argument
        loader = ModuleLoader()
        app.state.module_loader = loader
        
        # Configuration des modules disponibles
        app.include_router(assistant_router, prefix="/api/assistant", tags=["IA Assistant"])
        app.include_router(clients_router, prefix="/api/clients", tags=["Clients"])
        app.include_router(devis_router, prefix="/api/devis", tags=["Devis"])
        app.include_router(progress_router, prefix="/progress", tags=["Suivi tâches"])
        app.include_router(quote_router, prefix="/api/assistant", tags=["Quote"])
        app.include_router(client_router, prefix="/api/assistant", tags=["Client"])
        # Route pour servir l'interface IT Spirit
        @app.get('/interface/itspirit', response_class=HTMLResponse)
        async def itspirit_interface():
            """Sert l'interface IT Spirit personnalisée"""
            try:
                with open('templates/nova_interface_final.html', 'r', encoding='utf-8') as f: 
                    return HTMLResponse(content=f.read())
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Interface IT Spirit non trouvée")
        
        logger.info("Modules charges: 6/6")
        # Routes principales déjà incluses directement
        logger.info("Routes principales configurées")                
        # 3. FINALISATION DU DÉMARRAGE
        logger.info("=" * 60)
        logger.info("NOVA DEMARRE AVEC SUCCES")
        logger.info("   Interface: http://localhost:8000/api/assistant/interface")
        logger.info("   Sante: http://localhost:8000/health")
        logger.info("   Documentation: http://localhost:8000/docs")
        logger.info("=" * 60)
        
        # Le serveur est maintenant prêt
        yield
    
    except Exception as e:
        logger.error(f"Erreur critique au demarrage: {str(e)}")
        logger.error(f"Details: {type(e).__name__}")
        
        # En cas d'erreur, on continue le démarrage en mode minimal
        logger.warning("Demarrage en mode minimal...")
        yield
    
    # Nettoyage à l'arrêt
    finally:
        logger.info("Arret du systeme NOVA")

# Création de l'application avec le gestionnaire de cycle de vie
app = FastAPI(
    title="NOVA - Assistant IA pour Devis",
    description="Integration Claude + SAP + Salesforce pour generation automatique de devis",
    version="2.1.0",
    lifespan=lifespan
)

# Configuration des fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ====
# ENDPOINTS DE SANTÉ ET DIAGNOSTIC
# ====

@app.get("/health")
async def health():
    """Endpoint de santé avec résultats des vérifications de démarrage"""
    global HEALTH_CHECK_RESULTS
    
    try:
        # Vérification basique en temps réel
        basic_health = {
            "service": "NOVA Server",
            "status": "active",
            "timestamp": datetime.now().isoformat(),
            "uptime_info": "Service operationnel"
        }
        
        # Ajout des résultats détaillés si disponibles
        if HEALTH_CHECK_RESULTS:
            return {
                **basic_health,
                "system_status": HEALTH_CHECK_RESULTS["nova_system_status"],
                "startup_tests": {
                    "success_rate": HEALTH_CHECK_RESULTS["summary"]["success_rate"],
                    "successful_tests": HEALTH_CHECK_RESULTS["summary"]["successful"],
                    "total_tests": HEALTH_CHECK_RESULTS["summary"]["total_tests"],
                    "recommendations": HEALTH_CHECK_RESULTS["recommendations"]
                },
                "detailed_results": HEALTH_CHECK_RESULTS["detailed_results"],
                "last_check": HEALTH_CHECK_RESULTS["timestamp"]
            }
        else:
            return basic_health
    
    except Exception as e:
        logger.error(f"Erreur lors du health check: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "service": "NOVA Server", 
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "message": "Service partiellement disponible"
            }
        )

@app.get("/diagnostic/connections")
async def diagnostic_connections():
    """Endpoint de diagnostic détaillé des connexions"""
    if not HEALTH_CHECK_RESULTS:
        raise HTTPException(status_code=503, detail="Tests de demarrage non disponibles")
    
    # Extraction des résultats de connexion
    connection_tests = {}
    for test_name, result in HEALTH_CHECK_RESULTS["detailed_results"].items():
        if any(keyword in test_name for keyword in ["connection", "api", "database"]):
            connection_tests[test_name] = result
    
    return {
        "connection_status": connection_tests,
        "timestamp": HEALTH_CHECK_RESULTS["timestamp"]
    }

@app.get("/diagnostic/data-retrieval") 
async def diagnostic_data_retrieval():
    """Endpoint de diagnostic de la récupération de données"""
    if not HEALTH_CHECK_RESULTS:
        raise HTTPException(status_code=503, detail="Tests de démarrage non disponibles")
    
    # Extraction des résultats de récupération de données
    data_tests = {}
    for test_name, result in HEALTH_CHECK_RESULTS["detailed_results"].items():
        if "data_retrieval" in test_name:
            data_tests[test_name] = result
    
    return {
        "data_retrieval_status": data_tests,
        "summary": {
            "total_sources": len(data_tests),
            "operational_sources": sum(1 for r in data_tests.values() if r["status"] == "success")
        },
        "last_check": HEALTH_CHECK_RESULTS["timestamp"]
    }

@app.post("/diagnostic/recheck")
async def recheck_system():
    """Force une nouvelle vérification complète du système"""
    global HEALTH_CHECK_RESULTS
    
    try:
        logger.info("🔄 Relancement des vérifications de santé...")
        health_checker = NovaHealthChecker()
        HEALTH_CHECK_RESULTS = await health_checker.run_full_health_check()
        
        return {
            "message": "Vérification complète terminée",
            "system_status": HEALTH_CHECK_RESULTS["nova_system_status"],
            "success_rate": HEALTH_CHECK_RESULTS["summary"]["success_rate"],
            "timestamp": HEALTH_CHECK_RESULTS["timestamp"]
        }
    
    except Exception as e:
        logger.error(f"Erreur lors de la revérification: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Échec de la revérification: {str(e)}")

# Endpoint de base
@app.get("/")
async def root():
    """Endpoint racine avec informations de base"""
    return {
        "service": "NOVA - Assistant IA pour Devis",
        "version": "2.1.0",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "documentation": "/docs",
            "assistant": "/api/assistant/interface"
        }
    }

if __name__ == "__main__":
    # Configuration spécifique pour Windows
    if sys.platform == "win32":
        # Configuration pour éviter les problèmes d'encodage
        os.environ["PYTHONIOENCODING"] = "utf-8"
    
    # CORRECTION: Ne pas lancer uvicorn ici car startup_script.py s'en charge
    # Démarrage du serveur - COMMENTÉ pour éviter le conflit
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    
    print("NOVA FastAPI app initialisée - Prête pour startup_script.py")