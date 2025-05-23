# tools.py corrigé
from mcp_app import mcp
from simple_salesforce import Salesforce
import os
import httpx
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime

# Charger les variables d'environnement
load_dotenv()

# Connexion Salesforce
sf = Salesforce(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    domain=os.getenv("SALESFORCE_DOMAIN", "login")
)

# Gestion session SAP
sap_session = {
    "cookies": None,
    "expires": None
}

SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")

async def login_sap():
    url = SAP_BASE_URL + "/Login"
    auth_payload = {
        "UserName": os.getenv("SAP_USER"),
        "Password": os.getenv("SAP_CLIENT_PASSWORD"),
        "CompanyDB": os.getenv("SAP_CLIENT")
    }
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, json=auth_payload)
        response.raise_for_status()
        sap_session["cookies"] = response.cookies
        sap_session["expires"] = datetime.utcnow().timestamp() + 60 * 20

async def call_sap(endpoint: str, method="GET", payload: Optional[dict] = None):
    if not sap_session["cookies"] or datetime.utcnow().timestamp() > sap_session["expires"]:
        await login_sap()

    async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False) as client:
        url = SAP_BASE_URL + endpoint
        try:
            if method == "GET":
                response = await client.get(url)
            else:
                response = await client.post(url, json=payload or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                await login_sap()
                return await call_sap(endpoint, method, payload)
            raise

# Outils MCP pour Salesforce
@mcp.tool(name="salesforce.query", description="Exécute une requête SOQL sur Salesforce.")
async def salesforce_query(query: str) -> dict:
    """Exécute une requête Salesforce SOQL."""
    try:
        result = sf.query(query)
        return result
    except Exception as e:
        return {"error": str(e)}

# Outils MCP pour SAP
@mcp.tool(name="sap.read", description="Lit des données SAP B1 via API REST.")
async def sap_read(endpoint: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
    """Lecture de données SAP REST (produits, stock, etc.)."""
    try:
        return await call_sap(endpoint, method, payload)
    except Exception as e:
        return {"error": str(e)}