# server_mcp.py - version progressive
from mcp_app import mcp

# Commencez avec un seul import
try:
    from tools import salesforce_query
    # Ajoutez d'autres imports au fur et à mesure que ça fonctionne
except ImportError as e:
    print(f"Warning: Could not import tools: {e}")

@mcp.tool()
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong! NOVA Middleware est opérationnel"

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP NOVA Middleware...")
    mcp.run(transport="stdio")