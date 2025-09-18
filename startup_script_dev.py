#!/usr/bin/env python3
# start_nova_fixed.py - Script de démarrage NOVA avec corrections

import os
import sys
import subprocess
import logging
import time
from datetime import datetime
import asyncio
from dotenv import load_dotenv
load_dotenv()

# Configuration de l'encodage pour Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('startup.log', encoding='utf-8'),
        logging.StreamHandler()
        ]
    )

logger = logging.getLogger(__name__)

def clear_terminal():
    """Nettoie le terminal selon le système d'exploitation"""
    if sys.platform == "win32":
        os.system('cls')
    else:
        os.system('clear')

async def initialize_server():
    """Initialise le serveur de manière asynchrone"""
    try:
        # Importer le websocket_manager global qui est déjà créé
        from services.websocket_manager import websocket_manager

        # Autres initialisations asynchrones si nécessaire...

        logger.info("Serveur initialisé avec succès")
        return True

    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du serveur: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        return False
    
def print_banner():
    """Affichage de la bannière NOVA"""
    banner = """
        ╔══════════════════════════════════════════════════════╗
        ║                                                      ║
        ║   ███╗   ██╗ ██████╗ ██╗   ██╗ █████╗                ║
        ║   ████╗  ██║██╔═══██╗██║   ██║██╔══██╗               ║
        ║   ██╔██╗ ██║██║   ██║██║   ██║███████║               ║
        ║   ██║╚██╗██║██║   ██║╚██╗ ██╔╝██╔══██║               ║
        ║   ██║ ╚████║╚██████╔╝ ╚████╔╝ ██║  ██║               ║
        ║   ╚═╝  ╚═══╝ ╚═════╝   ╚═══╝  ╚═╝  ╚═╝               ║
        ║                                                      ║
        ║   Assistant IA - SAP - Salesforce                    ║
        ║   v2.1.0 CORRIGE - IT Spirit - 2025                  ║
        ║                                                      ║
        ╚══════════════════════════════════════════════════════╝
    """
    print(banner)

def check_python_version():
    """Vérifie la version de Python"""
    if sys.version_info < (3, 8):
        logger.error(f"Python 3.8+ requis. Version actuelle: {sys.version}")
        return False

    # Plus besoin d'afficher la version ici car elle sera dans le résumé
    return True

def check_environment():
    """Vérifie l'environnement Python et les dépendances"""
    # Plus de message "Vérification de l'environnement..." car déjà affiché dans run_pre_flight_checks

    # Vérification du fichier .env
    if not os.path.exists('.env'):
        logger.error("Fichier .env manquant!")
        logger.info("Créez le fichier .env à partir de .env.template")
        return False

    # Création des dossiers requis
    required_dirs = ['logs', 'cache', 'static']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            logger.info(f"Dossier {dir_name} créé")

    # Vérification des modules critiques
    critical_modules = ['fastapi', 'uvicorn', 'anthropic', 'httpx']
    missing_modules = []
    
    for module in critical_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        logger.error(f"Modules manquants: {', '.join(missing_modules)}")
        logger.info("Installez avec: pip install -r requirements.txt")
        return False
        
    return True

def start_mcp_services():
    """Démarre les services MCP (Model Context Protocol)"""
    logger.info("Démarrage des services MCP...")
    
    # Vérifier l'environnement Salesforce
    if not all([os.getenv('SALESFORCE_USERNAME'), os.getenv('SALESFORCE_PASSWORD'), os.getenv('SALESFORCE_SECURITY_TOKEN')]):
        logger.warning("Configuration Salesforce MCP manquante - Service désactivé")
        return
        
    # Ici on pourrait démarrer les services MCP si nécessaire
    # Pour l'instant, on suppose qu'ils sont lancés séparément
    logger.info("Services MCP prêts")

def start_claude_desktop():
    """Démarre Claude Desktop si disponible"""
    if sys.platform == "win32":
        claude_path = os.path.expandvars(r"%LOCALAPPDATA%\Programs\claude\Claude.exe")
        if os.path.exists(claude_path):
            try:
                subprocess.Popen([claude_path], shell=True)
                logger.info("Claude Desktop lancé")
            except Exception as e:
                logger.warning(f"Impossible de lancer Claude Desktop: {e}")
        else:
            logger.debug("Claude Desktop non installé")

def test_api_health():
    """Teste la santé de l'API"""
    import httpx
    try:
        with httpx.Client() as client:
            response = client.get("http://localhost:8110/health", timeout=5.0)
            if response.status_code == 200:
                return True
    except:
        pass
    return False

def run_pre_flight_checks():
    """Effectue toutes les vérifications préliminaires avec résumé compact"""
    logger.info("=== VÉRIFICATIONS PRÉLIMINAIRES ===")
    
    # Récupération des informations système
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    system_info = f"{sys.platform.upper()} | Python {python_version}"
    
    # Liste des vérifications à effectuer
    checks = [
        ("Python", check_python_version),
        ("Environnement", check_environment),
    ]
    
    check_status = []
    
    # Effectuer chaque vérification
    for check_name, check_func in checks:
        logger.info(f"Vérification: {check_name}...")
        if check_func():
            check_status.append(f"✓ {check_name}")
        else:
            logger.error(f"✗ Échec: {check_name}")
            return False

    # Afficher le résumé des vérifications réussies
    logger.info("Vérifications réussies: " + " | ".join(check_status))
    return True

def start_nova_server():
    """Démarre le serveur NOVA"""
    logger.info("=== DÉMARRAGE DU SERVEUR NOVA ===")

    try:
        # Correction: Vérifier l'existence de main.py avant l'import
        if not os.path.exists("main.py"):
            logger.error("Fichier main.py manquant!")
            return False

        # CORRECTION: Import conditionnel pour éviter les erreurs d'import circulaire
        try:
            from main import app  # Import de l'app FastAPI
        except NameError as ne:
            if 'WebSocket' in str(ne):
                logger.error("Erreur d'import WebSocket - Correction requise dans les annotations de type")
                return False
            else:
                raise ne

        import uvicorn

        host = os.getenv("APP_HOST", "0.0.0.0")
        port = int(os.getenv("APP_PORT", "8110"))
        log_level = os.getenv("LOG_LEVEL", "warning")
        reload = os.getenv("UVICORN_RELOAD", "true").lower() in ("1", "true", "yes")

        logger.info(f"NOVA démarré → http://{host}:{port} | Docs: /docs | Interface: /interface/itspirit | Santé: /health")

        try:
            uvicorn.run(
                app,
                host=host,
                port=port,
                reload=reload,
                log_level=log_level,
                workers=int(os.getenv("UVICORN_WORKERS", "1")),
            )
        except OSError as e:
            # Cas typique Windows : WinError 10013 (permissions / firewall / port réservé)
            if getattr(e, "winerror", None) == 10013:
                logger.error("WinError 10013: accès refusé au bind du port.")
                logger.error(f"Tentez : netsh advfirewall firewall add rule name=\"NOVA DEV {port}\" dir=in action=allow protocol=TCP localport={port}")
                logger.error("Ou lancez en 127.0.0.1, ou choisissez un autre port (ex: 8110→8111).")
            raise

    except ImportError as e:
        logger.error(f"Erreur d'import - Vérifiez que main.py existe et contient l'app FastAPI: {e}")
        logger.error("Détails: Le fichier main.py doit contenir une variable 'app' de type FastAPI")
        return False
    except KeyboardInterrupt:
        logger.info("Arrêt du serveur demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur lors du démarrage du serveur: {e}")
        logger.error(f"Type d'erreur: {type(e).__name__}")
        return False
    
    return True
    
def main():
    """Fonction principale"""
    try:
        # Bannière
        print_banner()
        
        # Vérifications préliminaires
        if not run_pre_flight_checks():
            logger.error("Échec des vérifications préliminaires")
            sys.exit(1)
            
        # Démarrage des services MCP
        start_mcp_services()
        
        # Démarrage de Claude Desktop
        start_claude_desktop()    
        
        # Nettoyage du terminal avant de démarrer le serveur si tout est OK
        time.sleep(2)  # Pause pour permettre de lire les derniers messages
        clear_terminal()
                
        # Démarrage du serveur
        logger.info("Démarrage du serveur NOVA...")
        success = start_nova_server()
        
        if not success:
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Erreur critique: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()