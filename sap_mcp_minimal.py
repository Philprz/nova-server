# sap_mcp_minimal.py
from mcp.server.fastmcp import FastMCP
import os
import sys
import io

# Configuration de l'encodage
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Journalisation
log_file = open("sap_debug.log", "w", encoding="utf-8")
def log(message):
    log_file.write(f"{message}\n")
    log_file.flush()

log("Démarrage du serveur MCP SAP minimal...")

# Création du serveur MCP
mcp = FastMCP("sap_minimal")

@mcp.tool(name="ping")
def ping() -> str:
    """Test simple de disponibilité du serveur MCP SAP"""
    log("Ping SAP reçu!")
    return "pong! Serveur MCP SAP minimal fonctionnel"

if __name__ == "__main__":
    log("Lancement du serveur MCP SAP...")
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        log(f"ERREUR: {str(e)}")
        import traceback
        log(traceback.format_exc())