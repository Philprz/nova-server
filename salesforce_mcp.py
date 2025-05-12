# salesforce_mcp.py
from mcp_app import mcp
import os
from dotenv import load_dotenv
from simple_salesforce import Salesforce

load_dotenv()

# Configuration Salesforce
sf = None
try:
    sf = Salesforce(
        username=os.getenv("SALESFORCE_USERNAME"),
        password=os.getenv("SALESFORCE_PASSWORD"),
        security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
        domain=os.getenv("SALESFORCE_DOMAIN", "login")
    )
    print("✅ Connexion Salesforce établie")
except Exception as e:
    print(f"❌ Erreur Salesforce: {str(e)}")

@mcp.tool(name="ping")
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong! NOVA Middleware est opérationnel"

@mcp.tool(name="salesforce.query")
def salesforce_query(query: str) -> dict:
    """Exécute une requête SOQL sur Salesforce."""
    if not sf:
        return {"error": "Salesforce non configuré"}
    try:
        result = sf.query(query)
        return result
    except Exception as e:
        return {"error": str(e)}

@mcp.tool(name="salesforce.inspect")
def inspect_salesforce(object_name: str = None) -> dict:
    """Liste les objets et champs Salesforce."""
    if not sf:
        return {"error": "Salesforce non configuré"}
    try:
        if object_name:
            # Récupérer les détails d'un objet spécifique
            obj_desc = sf.__getattr__(object_name).describe()
            return {
                "name": obj_desc["name"],
                "fields": [{"name": f["name"], "type": f["type"]} for f in obj_desc["fields"]],
                "label": obj_desc["label"]
            }
        else:
            # Lister tous les objets
            objects = sf.describe()["sobjects"]
            return {"objects": [{"name": obj["name"], "label": obj["label"]} for obj in objects]}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP Salesforce...")
    mcp.run(transport="stdio")