# simple_server.py
from mcp.server.fastmcp import FastMCP

# Instance MCP simplifiée
mcp = FastMCP("nova_middleware")

@mcp.tool()
async def ping() -> str:
    """Test de connectivité du serveur MCP"""
    return "pong! Le serveur NOVA est connecté."

@mcp.tool()
async def salesforce_query(query: str) -> str:
    """Exécute une requête SOQL (simulation)"""
    return f"Simulation de requête Salesforce: {query}"

@mcp.tool()
async def sap_query(endpoint: str) -> str:
    """Exécute une requête SAP (simulation)"""
    return f"Simulation de requête SAP: {endpoint}"

if __name__ == "__main__":
    print("Démarrage du serveur NOVA MCP...")
    mcp.run(transport="stdio")