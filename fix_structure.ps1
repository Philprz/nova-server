# fix_structure.ps1
# Vérifier si le dossier services existe
if (-not (Test-Path "services")) {
    Write-Host "Création du dossier services..." -ForegroundColor Yellow
    New-Item -Path "services" -ItemType Directory
}

# Vérifier les fichiers d'exploration
$explorationFiles = @(
    "services/exploration_salesforce.py",
    "services/exploration_sap.py"
)

foreach ($file in $explorationFiles) {
    if (-not (Test-Path $file)) {
        Write-Host "Création du fichier $file..." -ForegroundColor Yellow
        
        # Déterminer quel contenu écrire
        if ($file -eq "services/exploration_salesforce.py") {
            $content = @"
# exploration_salesforce.py
import os
import json
from datetime import datetime
from simple_salesforce import Salesforce
from dotenv import load_dotenv
from mcp_app import mcp

load_dotenv()

CACHE_FILE = "metadata_salesforce.json"

sf = Salesforce(
    username=os.getenv("SALESFORCE_USERNAME"),
    password=os.getenv("SALESFORCE_PASSWORD"),
    security_token=os.getenv("SALESFORCE_SECURITY_TOKEN"),
    domain=os.getenv("SALESFORCE_DOMAIN", "login")
)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def fetch_metadata():
    try:
        objects = sf.describe()["sobjects"]
        metadata = {}
        for obj in objects:
            name = obj["name"]
            fields = sf.__getattr__(name).describe()["fields"]
            metadata[name] = {
                "fields": [
                    {"name": f["name"], "type": f["type"], "label": f["label"]}
                    for f in fields
                ],
                "label": obj["label"],
                "update_time": datetime.utcnow().isoformat()
            }
        save_cache(metadata)
        return metadata
    except Exception as e:
        print(f"Erreur lors de la récupération des métadonnées Salesforce: {e}")
        # Retourner un cache vide ou partiel si disponible
        return load_cache() or {}

@mcp.tool(name="salesforce.inspect", description="Liste les objets et champs Salesforce depuis le cache.")
def inspect_salesforce(object_name: str = None) -> dict:
    """Liste les objets Salesforce et leurs champs."""
    cache = load_cache()
    if object_name:
        return cache.get(object_name, {"error": "Objet non trouvé"})
    return {"objects": list(cache.keys())}

@mcp.tool(name="salesforce.refresh_metadata", description="Force la mise à jour des métadonnées Salesforce.")
def refresh_salesforce_metadata() -> dict:
    """Force la mise à jour du cache des métadonnées Salesforce."""
    try:
        updated = fetch_metadata()
        return {"status": "ok", "updated": list(updated.keys())}
    except Exception as e:
        return {"error": str(e)}
"@
        } else {
            $content = @"
# exploration_sap.py
import os
import json
from datetime import datetime
from typing import Optional
import httpx
from dotenv import load_dotenv
from mcp_app import mcp

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
    # Endpoints exemple - fallback si metadata n'est pas disponible
    try:
        # Cette approche est simplifiée - ajustez selon votre structure SAP
        schema = {
            "endpoints": [
                "/Items", "/BusinessPartners", "/Orders", "/Invoices"
            ],
            "update_time": datetime.utcnow().isoformat()
        }
        save_cache(schema)
        return schema
    except Exception as e:
        print(f"Erreur lors de la récupération des métadonnées SAP: {e}")
        # Retourner un cache existant ou un fallback
        return load_cache() or {
            "endpoints": ["/Items"],
            "update_time": datetime.utcnow().isoformat(),
            "note": "Fallback - échec de mise à jour."
        }

@mcp.tool(name="sap.inspect", description="Liste les endpoints SAP depuis le cache.")
def inspect_sap() -> dict:
    """Liste les endpoints SAP disponibles depuis le cache."""
    return load_cache()

@mcp.tool(name="sap.refresh_metadata", description="Force la mise à jour des endpoints SAP.")
async def refresh_sap_metadata() -> dict:
    """Force la mise à jour du cache des endpoints SAP."""
    try:
        schema = await fetch_sap_metadata()
        return {"status": "ok", "endpoints": schema.get("endpoints", [])}
    except Exception as e:
        return {"error": str(e)}
"@
        }
        
        # Créer le fichier et y écrire le contenu
        New-Item -Path $file -ItemType File -Force | Out-Null
        $content | Out-File -FilePath $file -Encoding utf8
    }
}

# Créer le fichier __init__.py dans le dossier services s'il n'existe pas
if (-not (Test-Path "services/__init__.py")) {
    Write-Host "Création du fichier services/__init__.py..." -ForegroundColor Yellow
    New-Item -Path "services/__init__.py" -ItemType File -Force | Out-Null
}

Write-Host "Structure des dossiers et fichiers corrigée!" -ForegroundColor Green