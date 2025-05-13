from mcp.server.fastmcp import FastMCP
import os
import json
import sys
from datetime import datetime
from dotenv import load_dotenv
import logging

# Configuration du logging avancé
log_file = 'salesforce_mcp.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("salesforce_mcp")

# Démarrage avec informations système
logger.info("=" * 50)
logger.info(f"Démarrage du serveur MCP Salesforce à {datetime.now().isoformat()}")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info("=" * 50)

# Chargement configuration
try:
    load_dotenv()
    
    # Vérification des variables requises
    required_vars = ["SALESFORCE_USERNAME", "SALESFORCE_PASSWORD", "SALESFORCE_SECURITY_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Variables d'environnement manquantes: {', '.join(missing_vars)}")
        logger.error("Le serveur ne peut pas démarrer sans ces variables")
        sys.exit(1)
    
    logger.info(f"Configuration chargée. Username: {os.getenv('SALESFORCE_USERNAME')}")
except Exception as e:
    logger.error(f"Erreur lors du chargement de la configuration: {str(e)}")
    sys.exit(1)

# Initialisation MCP
mcp = FastMCP("salesforce_mcp_robust")

# Connexion Salesforce
sf = None

def init_salesforce():
    """Initialise la connexion Salesforce"""
    global sf
    
    try:
        from simple_salesforce import Salesforce
        
        # Récupérer les informations de connexion
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        logger.info(f"Tentative de connexion à Salesforce avec {username} sur {domain}...")
        
        # Initialiser la connexion
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Tester la connexion
        sf.query("SELECT Id FROM Account LIMIT 1")
        
        logger.info("✅ Connexion Salesforce établie avec succès")
        return True
    except ImportError:
        logger.error("❌ La bibliothèque simple-salesforce n'est pas installée")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur de connexion Salesforce: {str(e)}")
        return False

# Outil simple de ping
@mcp.tool(name="ping")
def ping() -> str:
    """Test simple de disponibilité du serveur MCP"""
    logger.info("Ping reçu!")
    return "pong! Salesforce MCP Robust est opérationnel"

# Outil de requête Salesforce
@mcp.tool(name="salesforce.query")
def salesforce_query(query: str) -> dict:
    """
    Exécute une requête SOQL sur Salesforce.
    
    Args:
        query: Une requête SOQL valide (ex: "SELECT Id, Name FROM Account LIMIT 5")
        
    Returns:
        Un dictionnaire contenant les résultats ou une erreur
    """
    global sf
    
    logger.info(f"Requête SOQL reçue: {query}")
    
    if sf is None:
        logger.warning("Connexion Salesforce non initialisée, tentative d'initialisation...")
        if not init_salesforce():
            logger.error("Échec de l'initialisation Salesforce")
            return {"error": "Impossible de se connecter à Salesforce"}
    
    try:
        # Exécuter la requête
        start_time = datetime.now()
        result = sf.query(query)
        end_time = datetime.now()
        
        # Construire la réponse
        response = {
            "totalSize": result.get("totalSize", 0),
            "records": result.get("records", []),
            "done": result.get("done", True),
            "query_time_ms": (end_time - start_time).total_seconds() * 1000
        }
        
        logger.info(f"Requête exécutée avec succès - {response['totalSize']} résultats")
        
        # Ajouter nextRecordsUrl si présent
        if "nextRecordsUrl" in result:
            response["nextRecordsUrl"] = result["nextRecordsUrl"]
            
        return response
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de la requête SOQL: {str(e)}")
        return {"error": str(e)}

# Initialiser la connexion au démarrage
logger.info("Initialisation de la connexion Salesforce au démarrage...")
init_salesforce()

if __name__ == "__main__":
    try:
        logger.info("🚀 Démarrage du serveur MCP Salesforce Robust...")
        mcp.run(transport="stdio")
    except Exception as e:
        logger.critical(f"Erreur fatale lors du démarrage du serveur: {str(e)}")