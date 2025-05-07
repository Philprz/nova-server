# server_mcp.py - Version simplifiée pour test
from mcp_app import mcp

@mcp.tool()
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong"

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP Nova Middleware...")
    mcp.run(transport="stdio")