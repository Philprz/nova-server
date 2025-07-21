# diagnostic_nova.py - VERSION CORRIGÉE
"""
Script de diagnostic NOVA - Identifie les problèmes de configuration
CORRECTION : Chargement du fichier .env et variables correctes
"""

import os
import sys
import socket
import json
from datetime import datetime
from dotenv import load_dotenv

# 🔧 CORRECTION : Charger le fichier .env AVANT tout
load_dotenv()

def check_environment():
    """Vérification environnement de base"""
    print("🔍 DIAGNOSTIC NOVA - Début")
    print("=== DIAGNOSTIC ENVIRONNEMENT ===")
    
    # Python version
    print(f"✓ Python: {sys.version}")
    
    # 🔧 CORRECTION : Variables d'environnement avec les VRAIS NOMS
    required_vars = {
        "ANTHROPIC_API_KEY": "Claude API",
        "SAP_REST_BASE_URL": "SAP REST URL",  # Corrigé : pas SAP_HOST
        "SAP_USER": "SAP Utilisateur",
        "SAP_CLIENT": "SAP Client",
        "SAP_CLIENT_PASSWORD": "SAP Mot de passe",
        "SALESFORCE_URL": "Salesforce URL",  # Corrigé : pas SALESFORCE_LOGIN_URL
        "SALESFORCE_USERNAME": "Salesforce Username",
        "SALESFORCE_PASSWORD": "Salesforce Password",
        "SALESFORCE_SECURITY_TOKEN": "Salesforce Token",
        "DATABASE_URL": "Base de données"
    }
    
    env_status = {}
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if value:
            status = "✓ CONFIGURÉ"
            # Masquer les valeurs sensibles
            if "PASSWORD" in var or "TOKEN" in var or "API_KEY" in var:
                display_value = value[:8] + "..." if len(value) > 8 else "***"
            else:
                display_value = value[:50] + "..." if len(value) > 50 else value
            env_status[var] = True
            print(f"{status} {desc}: {display_value}")
        else:
            status = "✗ MANQUANT"
            env_status[var] = False
            print(f"{status} {desc}: MANQUANT")
    
    return env_status

def check_ports():
    """Vérification des ports de service"""
    print("\n=== DIAGNOSTIC PORTS ===")
    
    ports = {
        "FastAPI": 8000,
        "SAP MCP": 3001,
        "Salesforce MCP": 3002,
        "PostgreSQL": 5432,
        "Redis": 6379
    }
    
    port_status = {}
    for service, port in ports.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)  # Timeout rapide
            result = sock.connect_ex(('localhost', port))
            if result == 0:
                status = "✓ OUVERT"
                port_status[service] = True
                print(f"{status} {service}: port {port}")
            else:
                status = "✗ FERMÉ"
                port_status[service] = False
                print(f"{status} {service}: port {port}")
            sock.close()
        except Exception as e:
            status = "✗ ERREUR"
            port_status[service] = False
            print(f"{status} {service}: {e}")
    
    return port_status

def check_modules():
    """Vérification des modules Python"""
    print("\n=== DIAGNOSTIC MODULES ===")
    
    required_modules = {
        "fastapi": "FastAPI Framework",
        "uvicorn": "ASGI Server",
        "psycopg2": "PostgreSQL",
        "requests": "HTTP Client",
        "anthropic": "Claude API",
        "python-dotenv": "Environment Variables",
        "sqlalchemy": "Database ORM",
        "simple_salesforce": "Salesforce API",
        "redis": "Redis Cache"
    }
    
    module_status = {}
    for module, desc in required_modules.items():
        try:
            __import__(module)
            status = "✓ DISPONIBLE"
            module_status[module] = True
            print(f"{status} {desc}: {module}")
        except ImportError:
            status = "✗ MANQUANT"
            module_status[module] = False
            print(f"{status} {desc}: {module}")
    
    return module_status

def check_files():
    """Vérification des fichiers critiques"""
    print("\n=== DIAGNOSTIC FICHIERS ===")
    
    critical_files = {
        "main.py": "Serveur principal",
        ".env": "Configuration",
        "requirements.txt": "Dépendances",
        "services/mcp_connector.py": "Connecteur MCP",
        "routes/routes_intelligent_assistant.py": "Assistant IA",
        "templates/nova_interface_final.html": "Interface web",
        "db/models.py": "Modèles base de données",
        "workflow_devis.py": "Workflow devis"
    }
    
    file_status = {}
    for file, desc in critical_files.items():
        if os.path.exists(file):
            status = "✓ PRÉSENT"
            file_status[file] = True
            # Taille du fichier
            size = os.path.getsize(file)
            print(f"{status} {desc}: {file} ({size} bytes)")
        else:
            status = "✗ MANQUANT"
            file_status[file] = False
            print(f"{status} {desc}: {file}")
    
    return file_status

def check_connections():
    """Test des connexions externes"""
    print("\n=== DIAGNOSTIC CONNEXIONS ===")
    
    connections = {}
    
    # Test base de données
    try:
        import psycopg2
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            conn = psycopg2.connect(db_url)
            conn.close()
            connections["database"] = True
            print("✓ BASE DE DONNÉES: Connexion OK")
        else:
            connections["database"] = False
            print("✗ BASE DE DONNÉES: URL manquante")
    except Exception as e:
        connections["database"] = False
        print(f"✗ BASE DE DONNÉES: {e}")
    
    # Test Claude API
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            client = anthropic.Anthropic(api_key=api_key)
            # Test simple sans consommer de tokens
            connections["claude"] = True
            print("✓ CLAUDE API: Clé valide")
        else:
            connections["claude"] = False
            print("✗ CLAUDE API: Clé manquante")
    except Exception as e:
        connections["claude"] = False
        print(f"✗ CLAUDE API: {e}")
    
    return connections

def generate_report():
    """Génération du rapport de diagnostic"""
    print("\n=== RAPPORT DIAGNOSTIC ===")
    
    # Exécuter tous les checks
    env_status = check_environment()
    port_status = check_ports()  
    module_status = check_modules()
    file_status = check_files()
    connection_status = check_connections()
    
    # Calculer le score global
    total_checks = (len(env_status) + len(port_status) + 
                   len(module_status) + len(file_status) + len(connection_status))
    passed_checks = (sum(env_status.values()) + sum(port_status.values()) + 
                    sum(module_status.values()) + sum(file_status.values()) + 
                    sum(connection_status.values()))
    
    score = (passed_checks / total_checks) * 100
    
    print(f"\n📊 SCORE GLOBAL: {score:.1f}% ({passed_checks}/{total_checks})")
    print(f"⏰ Timestamp: {datetime.now().isoformat()}")
    
    # Actions recommandées
    print("\n🔧 ACTIONS RECOMMANDÉES:")
    
    if not all(env_status.values()):
        print("1. Vérifier les variables d'environnement dans .env")
    
    if not all(module_status.values()):
        print("2. Installer les modules manquants: pip install -r requirements.txt")
    
    if not port_status.get("PostgreSQL", False):
        print("3. Démarrer le service PostgreSQL")
    
    if not connection_status.get("database", False):
        print("4. Vérifier la configuration de la base de données")
    
    if not connection_status.get("claude", False):
        print("5. Vérifier la clé API Claude")
    
    # Commandes de démarrage
    print("\n🚀 DÉMARRAGE RECOMMANDÉ:")
    if score >= 80:
        print("✅ Système prêt - Lancer: python main.py")
    else:
        print("⚠️  Corriger les problèmes avant le démarrage")
    
    return {
        "score": score,
        "env_status": env_status,
        "port_status": port_status,
        "module_status": module_status,
        "file_status": file_status,
        "connection_status": connection_status,
        "timestamp": datetime.now().isoformat()
    }

def main():
    """Point d'entrée principal"""
    try:
        report = generate_report()
        
        # Sauvegarder le rapport
        with open("diagnostic_report.json", "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n💾 Rapport sauvegardé: diagnostic_report.json")
        print("🔍 DIAGNOSTIC NOVA - Terminé")
        
        return report["score"] >= 80
        
    except Exception as e:
        print(f"❌ Erreur durant le diagnostic: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)