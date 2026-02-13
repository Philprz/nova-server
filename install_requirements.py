#!/usr/bin/env python3
# install_missing_modules.py - Installation automatique des modules manquants

import subprocess
import sys
import os
import logging
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('installation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Liste des modules requis avec leurs versions recommandées
REQUIRED_MODULES = {
    # Serveur web et API
    'fastapi': 'fastapi==0.104.1',
    'uvicorn': 'uvicorn[standard]==0.24.0',
    'httpx': 'httpx==0.25.2',
    
    # LLM et IA
    'anthropic': 'anthropic==0.7.8',
    'openai': 'openai==1.3.7',
    
    # Intégrations externes
    'simple-salesforce': 'simple-salesforce==1.12.4',
    'requests': 'requests==2.31.0',
    
    # Utilitaires
    'python-dotenv': 'python-dotenv==1.0.0',
    'pydantic': 'pydantic==2.5.0',
    'aiofiles': 'aiofiles==23.2.1',
    'python-multipart': 'python-multipart==0.0.6',
    
    # Logging et monitoring
    'structlog': 'structlog==23.2.0'
}

# Modules optionnels (non critiques)
OPTIONAL_MODULES = {
    'psycopg2-binary': 'psycopg2-binary==2.9.9',  # PostgreSQL
    'sqlalchemy': 'sqlalchemy==2.0.23',  # ORM
    'pytest': 'pytest==7.4.3',  # Tests
    'pytest-asyncio': 'pytest-asyncio==0.21.1'  # Tests async
}

def check_python_version():
    """Vérifie la version de Python"""
    if sys.version_info < (3, 8):
        logger.error(f"Python 3.8+ requis. Version actuelle: {sys.version}")
        return False
    
    logger.info(f"Version Python: {sys.version}")
    return True

def is_module_installed(module_name):
    """Vérifie si un module est installé"""
    try:
        __import__(module_name.replace('-', '_'))
        return True
    except ImportError:
        return False

def install_module(package_spec):
    """Installe un module via pip"""
    try:
        logger.info(f"Installation de {package_spec}...")
        
        cmd = [sys.executable, '-m', 'pip', 'install', package_spec]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max par module
        )
        
        if result.returncode == 0:
            logger.info(f"[OK] {package_spec} installé avec succès")
            return True
        else:
            logger.error(f"[ERROR] Échec installation {package_spec}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"[TIMEOUT] Installation de {package_spec} expirée")
        return False
    except Exception as e:
        logger.error(f"[EXCEPTION] Erreur lors de l'installation de {package_spec}: {e}")
        return False

def upgrade_pip():
    """Met à jour pip vers la dernière version"""
    try:
        logger.info("Mise à jour de pip...")
        cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip']
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            logger.info("[OK] pip mis à jour")
            return True
        else:
            logger.warning(f"[WARNING] Échec mise à jour pip: {result.stderr}")
            return False
            
    except Exception as e:
        logger.warning(f"[WARNING] Erreur mise à jour pip: {e}")
        return False

def create_virtual_env():
    """Crée un environnement virtuel si nécessaire"""
    venv_path = os.path.join(os.getcwd(), 'venv')
    
    if os.path.exists(venv_path):
        logger.info("Environnement virtuel détecté")
        return True
    
    try:
        logger.info("Création de l'environnement virtuel...")
        cmd = [sys.executable, '-m', 'venv', 'venv']
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            logger.info("[OK] Environnement virtuel créé")
            logger.info("IMPORTANT: Activez l'environnement virtuel:")
            
            if os.name == 'nt':  # Windows
                logger.info("  venv\\Scripts\\activate")
            else:  # Unix/Linux/macOS
                logger.info("  source venv/bin/activate")
            
            return True
        else:
            logger.error(f"[ERROR] Échec création venv: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"[ERROR] Erreur création environnement virtuel: {e}")
        return False

def generate_requirements_txt():
    """Génère un fichier requirements.txt"""
    requirements_content = []
    
    # Modules requis
    requirements_content.append("# Modules requis pour NOVA")
    for module, spec in REQUIRED_MODULES.items():
        requirements_content.append(spec)
    
    requirements_content.append("\n# Modules optionnels")
    for module, spec in OPTIONAL_MODULES.items():
        requirements_content.append(f"# {spec}")
    
    try:
        with open('requirements.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(requirements_content))
        
        logger.info("[OK] Fichier requirements.txt généré")
        return True
        
    except Exception as e:
        logger.error(f"[ERROR] Erreur génération requirements.txt: {e}")
        return False

def check_and_install_modules():
    """Vérifie et installe les modules manquants"""
    missing_modules = []
    installed_modules = []
    failed_modules = []
    
    # Vérification des modules requis
    logger.info("=== VÉRIFICATION DES MODULES REQUIS ===")
    
    for module_name, package_spec in REQUIRED_MODULES.items():
        base_module = module_name.split('==')[0] if '==' in module_name else module_name
        
        if is_module_installed(base_module):
            logger.info(f"[OK] {base_module} déjà installé")
            installed_modules.append(base_module)
        else:
            logger.warning(f"[MISSING] {base_module} manquant")
            missing_modules.append((module_name, package_spec))
    
    # Installation des modules manquants
    if missing_modules:
        logger.info("=== INSTALLATION DES MODULES MANQUANTS ===")
        
        for module_name, package_spec in missing_modules:
            if install_module(package_spec):
                installed_modules.append(module_name)
            else:
                failed_modules.append(module_name)
    
    # Rapport final
    logger.info("=== RAPPORT D'INSTALLATION ===")
    logger.info(f"Modules installés: {len(installed_modules)}")
    logger.info(f"Modules échoués: {len(failed_modules)}")
    
    if failed_modules:
        logger.error(f"Modules ayant échoué: {', '.join(failed_modules)}")
        return False
    
    logger.info("Tous les modules requis sont installés!")
    return True

def install_optional_modules():
    """Installe les modules optionnels"""
    logger.info("=== INSTALLATION DES MODULES OPTIONNELS ===")
    
    optional_success = []
    optional_failed = []
    
    for module_name, package_spec in OPTIONAL_MODULES.items():
        base_module = module_name.split('==')[0] if '==' in module_name else module_name
        
        if not is_module_installed(base_module):
            logger.info(f"Installation optionnelle: {module_name}")
            if install_module(package_spec):
                optional_success.append(module_name)
            else:
                optional_failed.append(module_name)
                logger.warning(f"[WARNING] Module optionnel {module_name} non installé")
        else:
            logger.info(f"[OK] Module optionnel {base_module} déjà présent")
            optional_success.append(module_name)
    
    logger.info(f"Modules optionnels installés: {len(optional_success)}")
    if optional_failed:
        logger.warning(f"Modules optionnels échoués: {len(optional_failed)}")

def main():
    """Fonction principale"""
    logger.info("=" * 60)
    logger.info("INSTALLATION AUTOMATIQUE DES DÉPENDANCES NOVA")
    logger.info("=" * 60)
    
    # 1. Vérification de Python
    if not check_python_version():
        sys.exit(1)
    
    # 2. Mise à jour de pip
    upgrade_pip()
    
    # 3. Génération du requirements.txt
    generate_requirements_txt()
    
    # 4. Installation des modules requis
    if not check_and_install_modules():
        logger.error("Installation critique échouée!")
        sys.exit(1)
    
    # 5. Installation des modules optionnels
    install_optional_modules()
    
    # 6. Vérification finale
    logger.info("=" * 60)
    logger.info("INSTALLATION TERMINÉE")
    logger.info("=" * 60)
    logger.info("Prochaines étapes:")
    logger.info("1. Configurez le fichier .env")
    logger.info("2. Lancez: python main.py")
    logger.info("3. Accédez à: http://localhost:8001/docs")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Installation interrompue par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        sys.exit(1)