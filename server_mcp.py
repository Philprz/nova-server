# server_mcp.py
from mcp_app import mcp

# Import des outils métier
from tools import salesforce_query, sap_read

# Import des outils d'exploration
from services.exploration_salesforce import inspect_salesforce, refresh_salesforce_metadata
from services.exploration_sap import inspect_sap, refresh_sap_metadata

@mcp.tool()
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong! NOVA Middleware est opérationnel"

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP NOVA Middleware...")
    mcp.run(transport="stdio")