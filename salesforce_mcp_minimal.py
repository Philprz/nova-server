# salesforce_mcp_minimal.py
from mcp.server.fastmcp import FastMCP
import os
# Créer le dossier logs s'il n'existe pas
os.makedirs("logs", exist_ok=True)
log_file = open("logs/salesforce_debug.log", "w", encoding="utf-8")
import sys
import io

# Configuration de l'encodage pour Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Journalisation dans un fichier
def log(message):
    log_file.write(f"{message}\n")
    log_file.flush()

log("Démarrage du serveur MCP simplifié...")

# Création du serveur MCP
mcp = FastMCP("salesforce_minimal")

@mcp.tool(name="ping")
def ping() -> str:
    """Test simple de disponibilité du serveur MCP"""
    log("Ping reçu!")
    return "pong! Serveur MCP minimal fonctionnel"
# Commencez par ajouter une fonctionnalité réelle de Salesforce
@mcp.tool(name="salesforce_query")
def salesforce_query(query: str) -> dict:
    """
    Exécute une requête SOQL sur Salesforce.
    
    Args:
        query: Une requête SOQL valide (ex: "SELECT Id, Name FROM Account LIMIT 5")
        
    Returns:
        Un dictionnaire contenant les résultats ou une erreur
    """
    # Tenter d'importer simple-salesforce
    try:
        from simple_salesforce import Salesforce
        log("simple_salesforce importé avec succès")
    except ImportError:
        log("Module simple-salesforce non trouvé. Tentative d'installation...")
        try:
            import subprocess
            import sys
            log("Module simple-salesforce non trouvé. Tentative d'installation...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "simple-salesforce"])
            log("Installation terminée, nouvelle tentative d'import...")
            from simple_salesforce import Salesforce
            log("Module simple-salesforce installé et importé avec succès")
        except Exception as e:
            log(f"Erreur lors de l'installation de simple-salesforce : {str(e)}")
            return {"error": f"Impossible d'installer simple-salesforce: {str(e)}"}
    except Exception as e:
        log(f"Erreur inattendue lors de l'import ou de l'installation : {str(e)}")
        raise
    try:
        # Journaliser la requête
        log(f"Requête SOQL: {query}")
        
        # Importer Salesforce ici pour éviter les problèmes au démarrage
        from simple_salesforce import Salesforce
        from dotenv import load_dotenv
        
        # Charger les credentials
        load_dotenv()
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        # Se connecter à Salesforce
        sf = Salesforce(
            username=username, 
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Exécuter la requête
        result = sf.query(query)
        
        # Retourner un résultat simplifié
        return {
            "totalSize": result.get("totalSize", 0),
            "records": result.get("records", []),
            "done": result.get("done", True)
        }
    except Exception as e:
        log(f"Erreur lors de l'exécution de la requête: {str(e)}")
        return {"error": str(e)}
if __name__ == "__main__":
    log("Lancement du serveur MCP...")
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        log(f"ERREUR: {str(e)}")
        import traceback
        log(traceback.format_exc())