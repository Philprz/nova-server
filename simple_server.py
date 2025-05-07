# simple_server.py
from mcp.server.fastmcp import FastMCP

# Créer l'instance MCP
mcp = FastMCP("nova_middleware")

@mcp.tool()
async def ping() -> str:
    """Simple test de connectivité"""
    return "pong! Le serveur NOVA est connecté."

@mcp.tool()
async def hello(name: str) -> str:
    """Salue l'utilisateur par son nom"""
    return f"Bonjour {name} ! Le serveur NOVA est prêt à vous aider."

# Point d'entrée principal
if __name__ == "__main__":
    print("Démarrage du serveur NOVA (MCP)...")
    mcp.run(transport="stdio")