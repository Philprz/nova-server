# main.py - Modification pour intégrer les tests au démarrage

import asyncio
import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Imports existants
from services.module_loader import ModuleLoader
from services.health_checker import NovaHealthChecker  # NOUVEAU

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nova_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variable globale pour stocker les résultats des tests
HEALTH_CHECK_RESULTS = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionnaire de cycle de vie de l'application avec vérifications de santé"""
    global HEALTH_CHECK_RESULTS
    
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE DU SYSTÈME NOVA")
    logger.info("=" * 60)
    
    try:
        # 1. VÉRIFICATIONS DE SANTÉ COMPLÈTES
        logger.info("🏥 Lancement des vérifications de santé système...")
        health_checker = NovaHealthChecker()
        HEALTH_CHECK_RESULTS = await health_checker.run_full_health_check()
        
        # Affichage du rapport de santé
        status = HEALTH_CHECK_RESULTS["nova_system_status"]
        success_rate = HEALTH_CHECK_RESULTS["summary"]["success_rate"]
        
        logger.info("-" * 50)
        logger.info(f"📋 RAPPORT DE SANTÉ NOVA")
        logger.info(f"   Statut global: {status.upper()}")
        logger.info(f"   Taux de succès: {success_rate}%")
        logger.info(f"   Tests réussis: {HEALTH_CHECK_RESULTS['summary']['successful']}")
        logger.info(f"   Erreurs: {HEALTH_CHECK_RESULTS['summary']['errors']}")
        logger.info(f"   Avertissements: {HEALTH_CHECK_RESULTS['summary']['warnings']}")
        logger.info("-" * 50)
        
        # Recommandations si nécessaire
        if HEALTH_CHECK_RESULTS["recommendations"]:
            logger.info("💡 RECOMMANDATIONS:")
            for rec in HEALTH_CHECK_RESULTS["recommendations"]:
                logger.info(f"   {rec}")
            logger.info("-" * 50)
        
        # Arrêt si système critique défaillant
        if status == "unhealthy":
            logger.error("❌ SYSTÈME CRITIQUE NON OPÉRATIONNEL")
            logger.error("   Impossible de démarrer NOVA avec des erreurs critiques")
            # En production, vous pourriez vouloir lever une exception ici
            # raise RuntimeError("Système non opérationnel")
        elif status == "degraded":
            logger.warning("⚠️ SYSTÈME EN MODE DÉGRADÉ")
            logger.warning("   Certaines fonctionnalités peuvent être limitées")
        else:
            logger.info("✅ SYSTÈME NOVA ENTIÈREMENT OPÉRATIONNEL")
        
        # 2. CHARGEMENT DES MODULES (existant)
        logger.info("🔧 Chargement des modules...")
        loader = ModuleLoader(app)
        app.state.module_loader = loader
        await loader.load_all_modules()
        
        # Statistiques modules
        loaded_modules = loader.get_loaded_modules()
        logger.info(f"📦 Modules chargés: {len([m for m in loaded_modules.values() if m.get('loaded')])}")
        
        # 3. FINALISATION DU DÉMARRAGE
        logger.info("=" * 60)
        logger.info("🎉 NOVA DÉMARRÉ AVEC SUCCÈS")
        logger.info("   Interface: http://localhost:8000/api/assistant/interface")
        logger.info("   Santé: http://localhost:8000/health")
        logger.info("   Documentation: http://localhost:8000/docs")
        logger.info("=" * 60)
        
        # Le serveur est maintenant prêt
        yield
        
    except Exception as e:
        logger.error(f"❌ Erreur critique au démarrage: {str(e)}")
        raise
    
    # Nettoyage à l'arrêt
    finally:
        logger.info("🛑 Arrêt du système NOVA")

# Création de l'application avec le gestionnaire de cycle de vie
app = FastAPI(
    title="NOVA - Assistant IA pour Devis",
    description="Intégration Claude + SAP + Salesforce pour génération automatique de devis",
    version="2.1.0",
    lifespan=lifespan
)

# Configuration des fichiers statiques
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# =====================================
# ENDPOINTS DE SANTÉ ET DIAGNOSTIC
# =====================================

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
            "uptime_info": "Service opérationnel"
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
        raise HTTPException(status_code=503, detail="Tests de démarrage non disponibles")
    
    # Extraction des résultats de connexion
    connection_tests = {}
    for test_name, result in HEALTH_CHECK_RESULTS["detailed_results"].items():
        if any(keyword in test_name for keyword in ["connection", "api", "database"]):
            connection_tests[test_name] = result
    
    return {
        "connections_status": connection_tests,
        "summary": {
            "total_connections": len(connection_tests),
            "healthy_connections": sum(1 for r in connection_tests.values() if r["status"] == "success"),
            "degraded_connections": sum(1 for r in connection_tests.values() if r["status"] == "warning")
        },
        "last_check": HEALTH_CHECK_RESULTS["timestamp"]
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

# =====================================
# ENDPOINTS EXISTANTS (inchangés)
# =====================================

@app.get("/")
async def root():
    """Point d'entrée principal avec informations de santé"""
    global HEALTH_CHECK_RESULTS
    
    system_status = "unknown"
    if HEALTH_CHECK_RESULTS:
        system_status = HEALTH_CHECK_RESULTS["nova_system_status"]
    
    return {
        "service": "NOVA Server",
        "version": "2.1.0", 
        "status": "active",
        "system_health": system_status,
        "description": "Intégration LLM Claude avec SAP et Salesforce",
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            "/health - Diagnostic système complet",
            "/diagnostic/connections - État des connexions",
            "/diagnostic/data-retrieval - État récupération données",
            "/api/assistant/interface - Interface utilisateur",
            "/docs - Documentation Swagger"
        ]
    }

@app.get("/interface/v3")
async def get_interface_v3():
    """Sert la nouvelle interface v3"""
    return FileResponse("templates/nova_interface_v3.html")

# Inclure ici les autres endpoints existants...
# (routes des modules, etc.)

if __name__ == "__main__":
    import uvicorn
    
    # Affichage des informations de démarrage
    print("=" * 60)
    print("🚀 DÉMARRAGE DE NOVA SERVER")
    print("   Version: 2.1.0")
    print("   Vérifications de santé: Activées")
    print("   Port: 8000")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)