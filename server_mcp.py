# server_mcp.py corrigé
import os
from dotenv import load_dotenv
from mcp_app import mcp

# Charger .env
load_dotenv()

# Import des outils
# Note: On n'importe pas directement salesforce_query et sap_read 
# car ils sont déjà définis dans tools.py et importés via server.yaml
import tools  # Ceci permet de s'assurer que les outils sont enregistrés

# Import des modules d'exploration
try:
    from services.exploration_salesforce import inspect_salesforce, refresh_salesforce_metadata
    from services.exploration_sap import inspect_sap, refresh_sap_metadata
except ImportError:
    print("Attention: Modules d'exploration non disponibles")

# Test simple pour vérifier le bon fonctionnement
@mcp.tool()
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong"

# 🚀 Démarrer directement
if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP Nova Middleware...")
    mcp.run(transport="stdio")