# diagnostic_nova.py
"""
Script de diagnostic NOVA - Identifie les problèmes de configuration
"""

import os
import sys
import socket
import json
from datetime import datetime

def check_environment():
    """Vérification environnement de base"""
    print("=== DIAGNOSTIC ENVIRONNEMENT ===")
    
    # Python version
    print(f"✓ Python: {sys.version}")
    
    # Variables d'environnement critiques
    required_vars = [
        "ANTHROPIC_API_KEY",
        "SAP_HOST", 
        "SAP_USER",
        "SALESFORCE_LOGIN_URL",
        "SALESFORCE_USERNAME"
    ]
    
    for var in required_vars:
        status = "✓" if os.getenv(var) else "✗"
        print(f"{status} {var}: {'Configuré' if os.getenv(var) else 'MANQUANT'}")

def check_ports():
    """Vérification des ports de service"""
    print("\n=== DIAGNOSTIC PORTS ===")
    
    ports = {
        "FastAPI": 8000,
        "SAP MCP": 3001,
        "Salesforce MCP": 3002,
        "PostgreSQL": 5432
    }
    
    for service, port in ports.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', port))
            status = "✓ OUVERT" if result == 0 else "✗ FERMÉ"
            print(f"{status} {service}: port {port}")
            sock.close()
        except Exception as e:
            print(f"✗ {service}: Erreur {e}")

def check_modules():
    """Vérification des modules Python"""
    print("\n=== DIAGNOSTIC MODULES ===")
    
    required_modules = [
        "fastapi",
        "uvicorn", 
        "psycopg2",
        "requests",
        "anthropic",
        "python-dotenv"
    ]
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ {module}: Disponible")
        except ImportError:
            print(f"✗ {module}: MANQUANT")

def check_files():
    """Vérification des fichiers critiques"""
    print("\n=== DIAGNOSTIC FICHIERS ===")
    
    critical_files = [
        "main.py",
        "config/database_config.py",
        "services/mcp_connector.py",
        "routes/routes_intelligent_assistant.py",
        "templates/nova_interface_final.html"
    ]
    
    for file in critical_files:
        status = "✓" if os.path.exists(file) else "✗"
        print(f"{status} {file}: {'Présent' if os.path.exists(file) else 'MANQUANT'}")

def generate_report():
    """Génération du rapport de diagnostic"""
    print("\n=== RAPPORT DIAGNOSTIC ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("Status: Diagnostic terminé")
    print("\nActions recommandées:")
    print("1. Corriger l'endpoint /health dans main.py")
    print("2. Vérifier les variables d'environnement manquantes")
    print("3. Redémarrer les services arrêtés")
    print("4. Tester l'interface après corrections")

if __name__ == "__main__":
    print("🔍 DIAGNOSTIC NOVA - Début")
    check_environment()
    check_ports()
    check_modules()
    check_files()
    generate_report()
    print("\n🔍 DIAGNOSTIC NOVA - Terminé")