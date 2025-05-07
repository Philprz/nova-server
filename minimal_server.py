# minimal_server.py
from mcp.server.fastmcp import FastMCP

# Créer une instance MCP simple
mcp = FastMCP("minimal_test")

@mcp.tool()
def echo(text: str) -> str:
    """Renvoie simplement le texte fourni."""
    return text

if __name__ == "__main__":
    print("Démarrage du serveur minimal...")
    mcp.run(transport="stdio")