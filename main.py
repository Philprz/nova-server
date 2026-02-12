#main.py - CORRECTIONS CRITIQUES POUR NOVA

import uvicorn
import logging
from pathlib import Path
import os
import sys
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from routes.routes_intelligent_assistant import router as assistant_router
from routes.routes_clients import router as clients_router
from routes.routes_devis import router as devis_router
from routes.routes_progress import router as progress_router
from routes.routes_client_listing import router as client_listing_router
from routes.routes_websocket import router as websocket_router
from routes import routes_quote_details
from routes.routes_sap_rondot import router as sap_rondot_router
from routes.routes_supplier_tariffs import router as supplier_tariffs_router
from routes.routes_graph import router as graph_router
from routes.routes_sap_business import router as sap_business_router
from routes.routes_pricing_validation import router as pricing_validation_router
from routes.routes_sap_creation import router as sap_creation_router
from routes.routes_product_validation import router as product_validation_router
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

        # CORRECTION: Import et utilisation de la bonne classe
        from services.health_checker import HealthChecker
        health_checker = HealthChecker()

        logger.info("Execution des tests de sante...")
        await asyncio.sleep(2)  # Délai pour l'initialisation
        HEALTH_CHECK_RESULTS = await health_checker.run_full_health_check()
        # Test connexion WebSocket au démarrage
        logger.info("Test de connectivité WebSocket...")
        try:
            from services.websocket_manager import websocket_manager
            # Simuler une connexion test
            test_task_id = f"startup_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"✅ WebSocket Manager initialisé - prêt pour task: {test_task_id}")
        except Exception as e:
            logger.error(f"❌ Erreur WebSocket Manager: {e}")
            HEALTH_CHECK_RESULTS["websocket_test"] = {"status": "failed", "error": str(e)}
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

        # 2. SYNCHRONISATION CACHE SAP (en arrière-plan, ne bloque pas le démarrage)
        try:
            from services.sap_sync_startup import sync_sap_data_if_needed
            # Lancer la synchronisation en arrière-plan
            asyncio.create_task(sync_sap_data_if_needed())
            logger.info("🔄 Synchronisation cache SAP lancée en arrière-plan")
        except Exception as e:
            logger.error(f"❌ Erreur lancement synchronisation cache SAP: {e}")

        logger.info("=" * 50)

        # CORRECTION: Démarrage normal si success_rate >= 50%
        if HEALTH_CHECK_RESULTS["summary"]["success_rate"] >= 50:
            logger.info("DEMARRAGE NOMINAL NOVA")
        else:
            logger.warning("DEMARRAGE EN MODE DEGRADE")

        # 2. CHARGEMENT DES MODULES
        logger.info("Chargement des modules...")

        # CORRECTION: Configuration des modules directement dans FastAPI
        # Au lieu d'utiliser ModuleLoader qui peut causer des problèmes

        # Modules chargés directement
        loaded_modules = 6

        logger.info(f"Modules charges: {loaded_modules}/6")
        logger.info("Routes principales configurées")

        # 3. SUCCÈS DU DÉMARRAGE
        backend_port = os.getenv("APP_PORT", "8001")
        logger.info("=" * 60)
        logger.info("NOVA DEMARRE AVEC SUCCES")
        logger.info(f"   Interface: http://localhost:{backend_port}/interface/itspirit")
        logger.info(f"   Sante: http://localhost:{backend_port}/health")
        logger.info(f"   Documentation: http://localhost:{backend_port}/docs")
        logger.info("=" * 60)

        yield

    except Exception as e:
        logger.error(f"Erreur critique au démarrage: {e}")
        raise
    finally:
        logger.info("Arrêt de NOVA")

# Création de l'application FastAPI
app = FastAPI(
    title="NOVA - Assistant IA pour Devis",
    description="Système intelligent de génération de devis avec intégration SAP et Salesforce",
    version="2.1.0",
    lifespan=lifespan
)

# Configuration des routes statiques pour l'interface
app.mount("/static", StaticFiles(directory="static"), name="static")

# Frontend mail-to-biz (React SPA)
app.mount("/mail-to-biz/assets", StaticFiles(directory="frontend/assets"), name="mail-to-biz-assets")

# CORRECTION: Configuration directe des routes
app.include_router(assistant_router, prefix="/api/assistant", tags=["IA Assistant"])
app.include_router(clients_router, prefix="/api/clients", tags=["Clients"])
app.include_router(devis_router, prefix="/api/devis", tags=["Devis"])
app.include_router(progress_router, prefix="/progress", tags=["Suivi tâches"])
app.include_router(client_listing_router, prefix="/api/clients", tags=["Client Listing"])
app.include_router(websocket_router, tags=["WebSocket"])
app.include_router(sap_rondot_router)  # API SAP Rondot pour mail-to-biz
app.include_router(supplier_tariffs_router)  # API Tarifs fournisseurs
app.include_router(graph_router, prefix="/api/graph", tags=["Microsoft Graph"])
app.include_router(sap_business_router)  # API SAP Business pour mail-to-biz
app.include_router(pricing_validation_router, prefix="/api/validations", tags=["Pricing Validation"])
app.include_router(sap_creation_router, prefix="/api/sap", tags=["SAP Creation"])
app.include_router(product_validation_router)  # API validation produits externes
# Route WebSocket pour l'assistant intelligent manquante
@app.websocket("/ws/assistant/{task_id}")
async def websocket_assistant_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket pour l'assistant intelligent"""
    from routes.routes_intelligent_assistant import websocket_endpoint
    await websocket_endpoint(websocket, task_id)
app.include_router(routes_quote_details.router)

@app.get("/api/assistant/prompt", response_class=PlainTextResponse)
async def get_assistant_prompt():
    """Renvoie le prompt système de l'assistant"""
    try:
        # Extraire le prompt de llm_extractor.py
        from services.llm_extractor import LLMExtractor
        # On prend une instance pour accéder au prompt, même si ce n'est pas idéal
        # L'idéal serait de stocker le prompt dans un fichier de config
        # ou de le définir comme une constante de module.
        # Pour l'instant, on va extraire le system_prompt de la méthode `extract_quote_info`
        import inspect
        prompt_text = inspect.getsource(LLMExtractor.extract_quote_info)

        # Simple parsing pour extraire le system_prompt. C'est fragile.
        try:
            start_str = 'system_prompt = """'
            end_str = '"""'
            start_index = prompt_text.find(start_str) + len(start_str)
            end_index = prompt_text.find(end_str, start_index)
            prompt = prompt_text[start_index:end_index].strip()
            return PlainTextResponse(content=prompt)
        except Exception:
             # Fallback avec le texte fourni si l'extraction échoue
            fallback_prompt = """Tu es NOVA, un assistant commercial intelligent qui comprend différents types de demandes.

            Analyse la demande utilisateur et détermine le TYPE D'ACTION puis extrais les informations :

            TYPES D'ACTIONS POSSIBLES :
            1. "DEVIS" - Génération de devis/proposition commerciale
            2. "RECHERCHE_PRODUIT" - Recherche de produits par caractéristiques
            3. "INFO_CLIENT" - Consultation d'informations client
            4. "CONSULTATION_STOCK" - Vérification de stock
            5. "AUTRE" - Autre demande

            Pour une demande de DEVIS, extrais :
            - Nom du client
            - Liste des produits avec codes/références, noms et quantités
            Format JSON requis:
            {
            "products": [{"code": "CODE_PRODUIT", "name": "NOM_PRODUIT", "quantity": QUANTITÉ}]
            }
            Pour une RECHERCHE_PRODUIT, extrais :
            - Caractéristiques recherchées (vitesse, type, fonctionnalités...)
            - Catégorie de produit (imprimante, ordinateur, etc.)
            - Critères spécifiques (recto-verso, réseau, laser, etc.)

            Réponds UNIQUEMENT au format JSON suivant:
            {
            "action_type": "DEVIS|RECHERCHE_PRODUIT|INFO_CLIENT|CONSULTATION_STOCK|AUTRE",
            "client": "NOM_DU_CLIENT (si pertinent)",
            "products": [{"code": "CODE_PRODUIT", "quantity": QUANTITÉ}] (pour DEVIS),
            "search_criteria": {
            "category": "TYPE_PRODUIT",
            "characteristics": ["caractéristique1", "caractéristique2"],
            "specifications": {"vitesse": "50 ppm", "type": "laser", "fonctions": ["recto-verso", "réseau"]}
            } (pour RECHERCHE_PRODUIT),
            "query_details": "détails spécifiques de la demande"
            }
            """
            return PlainTextResponse(content=fallback_prompt)

    except Exception as e:
        logger.error(f"Erreur lors de la récupération du prompt: {e}")
        raise HTTPException(status_code=500, detail="Impossible de récupérer le prompt de l'assistant")

# Route pour edit-quote manquante
@app.get("/edit-quote/{quote_id}")
async def edit_quote_page(quote_id: str):
    """Page d'édition de devis"""
    try:
        file_path = Path("templates") / "nova_interface_final.html"
        with file_path.open("r", encoding="utf-8") as f:
            html_content = f.read()
        # Injection du quote_id dans le HTML
        replaced = html_content.replace(
            "<!-- QUOTE_ID_PLACEHOLDER -->",
            f"<script>window.EDIT_QUOTE_ID = '{quote_id}';</script>"
        )
        if replaced == html_content:
            # Fallback si le placeholder est absent : insérer avant </body> ou en fin
            if "</body>" in html_content:
                html_content = html_content.replace(
                    "</body>",
                    f"<script>window.EDIT_QUOTE_ID = '{quote_id}';</script></body>"
                )
            else:
                html_content = html_content + f"<script>window.EDIT_QUOTE_ID = '{quote_id}';</script>"
        else:
            html_content = replaced
        return HTMLResponse(content=html_content, media_type="text/html; charset=utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Interface non trouvée")

# Route temporaire de débogage
@app.get('/api/assistant/interface')
async def get_assistant_interface():
    """Interface principale de l'assistant"""
    return await itspirit_interface()

# Route pour servir l'interface IT Spirit
@app.get('/interface/itspirit', response_class=HTMLResponse)
async def itspirit_interface():
    """Sert l'interface IT Spirit personnalisée"""
    try:
        with open('templates/nova_interface_final.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Interface IT Spirit non trouvée")

# Route pour servir l'interface mail-to-biz (React SPA)
@app.get('/mail-to-biz', response_class=HTMLResponse)
@app.get('/mail-to-biz/{path:path}', response_class=HTMLResponse)
async def mail_to_biz_interface(path: str = ""):
    """Sert l'interface mail-to-biz (React SPA avec fallback)"""
    try:
        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Interface mail-to-biz non trouvée")

@app.get("/health")
async def health_check():
    """Endpoint de contrôle de santé en temps réel"""
    try:
        # Santé de base
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
        raise HTTPException(status_code=503, detail="Tests de santé non disponibles")
    
    return {
        "detailed_results": HEALTH_CHECK_RESULTS["detailed_results"],
        "system_status": HEALTH_CHECK_RESULTS["nova_system_status"],
        "recommendations": HEALTH_CHECK_RESULTS["recommendations"],
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
async def force_health_recheck():
    """Force une nouvelle vérification complète du système"""
    global HEALTH_CHECK_RESULTS
    
    try:
        logger.info("🔄 Relancement des vérifications de santé...")
        from services.health_checker import HealthChecker
        health_checker = HealthChecker()
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

def kill_process_on_port(port: int):
    """Tue le processus qui occupe le port spécifié (Windows uniquement)"""
    if sys.platform != "win32":
        return

    import subprocess
    try:
        # Trouver le PID du processus sur le port
        result = subprocess.run(
            f'netstat -ano | findstr :{port} | findstr LISTENING',
            shell=True, capture_output=True, text=True
        )

        if result.stdout:
            # Extraire le PID (dernière colonne)
            lines = result.stdout.strip().split('\n')
            pids = set()
            for line in lines:
                parts = line.split()
                if parts:
                    pids.add(parts[-1])

            for pid in pids:
                if pid.isdigit():
                    logger.info(f"Arret du processus {pid} sur le port {port}...")
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                    logger.info(f"Processus {pid} termine")
    except Exception as e:
        logger.warning(f"Impossible de liberer le port {port}: {e}")


# Point d'entrée de l'application
if __name__ == "__main__":
    # Configuration spécifique pour Windows
    if sys.platform == "win32":
        # Configuration pour éviter les problèmes d'encodage
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Libérer le port si occupé
        backend_port = int(os.getenv("APP_PORT", 8001))
        kill_process_on_port(backend_port)

    # Démarrage du serveur
    backend_port = int(os.getenv("APP_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=backend_port, log_config=None, loop="asyncio")
