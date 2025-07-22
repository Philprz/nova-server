#!/usr/bin/env python3
# start_nova_fixed.py - Script de démarrage NOVA avec corrections

import os
import sys
import subprocess
import logging
from datetime import datetime
import asyncio
from dotenv import load_dotenv
load_dotenv()
# Configuration de l'encodage pour Windows
if sys.platform == "win32":
    # Correction : La redéfinition manuelle de sys.stdout/stderr entre en conflit
    # avec la gestion des I/O de uvicorn, causant l'erreur "I/O operation on closed file".
    # La définition de PYTHONIOENCODING et l'utilisation de `chcp 65001` dans le .bat
    # sont des méthodes plus sûres et suffisantes.
    # import io
    # sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    # sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('startup.log', encoding='utf-8'),
        # Correction: Utiliser explicitement sys.stdout pour le handler de la console.
        # Le StreamHandler() par défaut utilise sys.stderr, qui peut causer des problèmes
        # d'encodage sur Windows. sys.stdout a été configuré pour l'UTF-8 au début du script.
        logging.StreamHandler()
        ]
    )

logger = logging.getLogger(__name__)

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
    
    logger.info(f"Version Python: {sys.version}")
    return True

def check_environment():
    """Vérifie la configuration de l'environnement"""
    logger.info("Vérification de l'environnement...")
    
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
        logger.info("Exécutez: python install_missing_modules.py")
        return False
    
    logger.info("Environnement vérifié avec succès")
    return True

def check_configuration():
    """Vérifie la configuration dans .env"""
    logger.info("Vérification de la configuration...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    # Variables critiques
    critical_vars = [
        'ANTHROPIC_API_KEY',
        'SALESFORCE_USERNAME', 
        'SAP_REST_BASE_URL'
    ]
    
    missing_vars = []
    for var in critical_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"Variables de configuration manquantes: {', '.join(missing_vars)}")
        logger.warning("Le système démarrera en mode dégradé")
    else:
        logger.info("Configuration complète détectée")
    
    return True

def start_mcp_services():
    """Démarre les services MCP SAP et MCP Salesforce"""
    logger.info("Démarrage des services MCP...")
    
    # Vérifier si les fichiers MCP existent avant de les démarrer
    if os.path.exists("sap_mcp.py"):
        subprocess.Popen(["python", "sap_mcp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Serveur MCP SAP démarré")
    else:
        logger.warning("Fichier sap_mcp.py non trouvé")
    
    if os.path.exists("salesforce_mcp.py"):
        subprocess.Popen(["python", "salesforce_mcp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Serveur MCP Salesforce démarré")
    else:
        logger.warning("Fichier salesforce_mcp.py non trouvé")
    
def start_claude_desktop():
    """Démarre Claude Desktop"""
    # Correction: charger le fichier .env d'abord
    from dotenv import load_dotenv
    load_dotenv()
    
    # Lire le chemin depuis le fichier .env en utilisant la variable corrigée
    claude_desktop_path = os.getenv("CLAUDE_DESKTOP_PATH")
    
    # Si la variable n'est pas définie, on informe et on continue
    if not claude_desktop_path:
        logger.info("Variable CLAUDE_DESKTOP_PATH non définie, démarrage de Claude Desktop ignoré.")
        return

    # Si le chemin existe, on tente de démarrer l'application
    if os.path.exists(claude_desktop_path):
        try:
            subprocess.Popen([claude_desktop_path])
            logger.info(f"Claude Desktop démarré depuis {claude_desktop_path}")
        except Exception as e:
            logger.error(f"Erreur lors du lancement de Claude Desktop: {e}")
    else:
        # Si le chemin n'existe pas, on affiche un avertissement clair
        logger.warning(f"Claude Desktop non trouvé au chemin spécifié : {claude_desktop_path}")
    
def run_pre_flight_checks():
    """Exécute les vérifications avant démarrage"""
    logger.info("=== VÉRIFICATIONS PRÉLIMINAIRES ===")
    
    checks = [
        ("Version Python", check_python_version),
        ("Environnement", check_environment),
        ("Configuration", check_configuration)
    ]
    
    for check_name, check_func in checks:
        logger.info(f"Vérification: {check_name}")
        if not check_func():
            logger.error(f"Échec: {check_name}")
            return False
        logger.info(f"[OK] {check_name}")
    
    logger.info("Toutes les vérifications préliminaires réussies")
    return True

def start_nova_server():
    """Démarre le serveur NOVA"""
    logger.info("=== DÉMARRAGE DU SERVEUR NOVA ===")
    
    try:
        # Correction: Vérifier l'existence de main.py avant l'import
        if not os.path.exists("main.py"):
            logger.error("Fichier main.py manquant!")
            logger.error("Le fichier main.py contenant l'application FastAPI est requis")
            return False
        
        # avant l'import de main.py qui pourrait avoir ses propres configurations
        os.environ["PYTHONIOENCODING"] = "utf-8"
        if sys.platform == "win32":
            # Forcer l'encodage console avant import
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
        
        from main import app  # Correction: Import de l'app FastAPI
        import uvicorn
        logger.info("Lancement de NOVA sur http://localhost:8000")
        logger.info("Documentation: http://localhost:8000/docs")
        logger.info("Interface: http://localhost:8000/api/assistant/interface")
        logger.info("Santé: http://localhost:8000/health")
        
        # Correction: Configuration simplifiée pour éviter les conflits I/O
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=8000,
            log_level="info"
            # Suppression de access_log=True qui peut causer des conflits
        )
        
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