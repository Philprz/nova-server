# exploration_salesforce.py
import os
import json
from datetime import datetime
from simple_salesforce import Salesforce
from dotenv import load_dotenv
from mcp import tool

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

@tool(name="salesforce.inspect", description="Liste les objets et champs Salesforce depuis le cache.")
def inspect_salesforce(object_name: str = None) -> dict:
    cache = load_cache()
    if object_name:
        return cache.get(object_name, {"error": "Objet non trouvé"})
    return {"objects": list(cache.keys())}

@tool(name="salesforce.refresh_metadata", description="Force la mise à jour des métadonnées Salesforce.")
def refresh_salesforce_metadata() -> dict:
    try:
        updated = fetch_metadata()
        return {"status": "ok", "updated": list(updated.keys())}
    except Exception as e:
        return {"error": str(e)}
