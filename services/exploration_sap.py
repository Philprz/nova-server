# exploration_sap.py
import os
import json
from datetime import datetime
from typing import Optional
import httpx
from dotenv import load_dotenv
from mcp import tool

load_dotenv()

SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
SAP_USER = os.getenv("SAP_USER")
SAP_CLIENT_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD")
SAP_CLIENT = os.getenv("SAP_CLIENT")

CACHE_FILE = "metadata_sap.json"
sap_session = {"cookies": None, "expires": None}

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def login_sap():
    url = SAP_BASE_URL + "/Login"
    payload = {
        "UserName": SAP_USER,
        "Password": SAP_CLIENT_PASSWORD,
        "CompanyDB": SAP_CLIENT
    }
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        sap_session["cookies"] = response.cookies
        sap_session["expires"] = datetime.utcnow().timestamp() + 60 * 20

async def call_sap(endpoint: str, method="GET", payload: Optional[dict] = None):
    if not sap_session["cookies"] or datetime.utcnow().timestamp() > sap_session["expires"]:
        await login_sap()

    async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False) as client:
        url = SAP_BASE_URL + endpoint
        response = await client.request(method, url, json=payload or {})
        response.raise_for_status()
        return response.json()

async def fetch_sap_metadata():
    # Endpoint exemple : /ServiceLayer/$metadata si OData activé, sinon liste manuelle
    try:
        endpoints = await call_sap("/$metadata")
        # Cette réponse est souvent XML, mais ici on suppose JSON simplié pour exemple
        schema = {"endpoints": endpoints, "update_time": datetime.utcnow().isoformat()}
        save_cache(schema)
        return schema
    except Exception:
        # Fallback manuel si /$metadata indisponible
        schema = {
            "endpoints": [
                "/Items", "/BusinessPartners", "/Orders", "/Invoices"
            ],
            "update_time": datetime.utcnow().isoformat(),
            "note": "Mise à jour automatique échouée, fallback manuel."
        }
        save_cache(schema)
        return schema

@tool(name="sap.inspect", description="Liste les endpoints SAP depuis le cache.")
def inspect_sap() -> dict:
    return load_cache()

@tool(name="sap.refresh_metadata", description="Force la mise à jour des endpoints SAP.")
async def refresh_sap_metadata() -> dict:
    try:
        schema = await fetch_sap_metadata()
        return {"status": "ok", "endpoints": schema.get("endpoints", [])}
    except Exception as e:
        return {"error": str(e)}
