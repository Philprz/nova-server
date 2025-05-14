from mcp.server.fastmcp import FastMCP

# Création d'une nouvelle instance MCP
test_mcp = FastMCP("test_server")

@test_mcp.tool()
async def simple_ping() -> str:
    """Test simple ping"""
    return "pong from test server"

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP de test...")
    test_mcp.run(transport="stdio")