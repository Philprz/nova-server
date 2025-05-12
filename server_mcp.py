# simple_mcp.py
from mcp_app import mcp
import os
from dotenv import load_dotenv

load_dotenv()

@mcp.tool(name="ping")
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong! NOVA Middleware est opérationnel"

@mcp.tool(name="echo")
async def echo(message: str) -> str:
    """Renvoie le message reçu"""
    return f"Vous avez dit: {message}"

@mcp.tool(name="env_check")
async def env_check() -> dict:
    """Vérifie que les variables d'environnement essentielles sont définies"""
    return {
        "salesforce_configured": bool(os.getenv("SALESFORCE_USERNAME")),
        "sap_configured": bool(os.getenv("SAP_USER")),
        "db_configured": bool(os.getenv("DATABASE_URL"))
    }

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP NOVA Middleware (version simple)...")
    mcp.run(transport="stdio")